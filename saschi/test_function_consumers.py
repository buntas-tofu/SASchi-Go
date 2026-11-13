"""DS-108 independently frozen typed normalization, identifiers and IF consumers."""
from copy import deepcopy
import contextlib,hashlib,io,json,os
from pathlib import Path
import subprocess,sys,tempfile,unittest
from examples.verify_function_consumers import GATE
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import execute,job_with_inputs
ROOT=Path(__file__).resolve().parent.parent
PROFILE='function-consumers-v1'

def literal(value):
    if value is None:return '.'
    if type(value) is str:return "'"+value.replace("'","''")+"'"
    if type(value) is dict:return '.'+value['missing']
    return repr(value)

def catalog(values,spec=None):
    return {'raw':{'schema':{'a':spec or {'type':'character','length':8}},'rows':[{'a':value} for value in values]}}

def source_case(case):
    name,args=case['name'],case['args']
    if name.startswith('chain:'):
        expression=literal(args[0])
        for fn in reversed(name.split(':')[1].split(',')):expression=fn+'('+expression+')'
        return 'data d;x='+expression+';run;'
    if name.startswith('pred:'):
        _,fn,op=name.split(':');expression=fn+'('+','.join(map(literal,args[:-1]))+')'
        return 'data d;x=0;if '+expression+' '+op+' '+literal(args[-1])+' then x=1;run;'
    expression=name+'('+','.join(map(literal,args[1:-1]))+')'
    return 'data d;x=cats('+literal(args[0])+','+expression+','+literal(args[-1])+');run;'

class FunctionConsumerTests(unittest.TestCase):
    def test_independent_whole_original_and_every_cell(self):
        GATE.qualify([])
        result,stdout=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(line+'\n' for line in result['log']))

    def test_supplemental_r_kernels_replay_frozen_outputs(self):
        import csv,shutil
        from examples.wave_gate_common import encode,decode
        file=ROOT/'examples/function_consumer_kernel_pins.json'
        self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),'c43b450a32f6d2ef5a52e6e5015183588c51db03d17c71425e156d11075d87b2')
        pins=json.loads(file.read_text())
        with tempfile.TemporaryDirectory() as directory:
            for name,key in [('function_consumer_cases.R','normalization_and_predicates'),('function_identifier_cases.R','identifiers')]:
                oracle=ROOT/'examples'/name
                self.assertEqual(hashlib.sha256(oracle.read_bytes()).hexdigest(),pins['witness_sha256'][name])
                path=Path(directory)/'cases.csv'
                with path.open('w',newline='') as stream:
                    writer=csv.writer(stream);writer.writerow(['name','args'])
                    writer.writerows((case['name'],'|'.join(map(encode,case['args']))) for case in pins[key])
                run=subprocess.run([os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript',str(oracle),str(path)],capture_output=True,text=True,check=True,timeout=60)
                self.assertEqual(list(map(decode,run.stdout.splitlines())),[case['expected'] for case in pins[key]])

    def test_all_qualified_chains_predicates_and_identifier_kernels(self):
        pins=json.loads((ROOT/'examples/function_consumer_kernel_pins.json').read_text())
        self.assertEqual(len(pins['normalization_and_predicates']),1162)
        self.assertEqual(len(pins['identifiers']),235)
        for case in pins['normalization_and_predicates']+pins['identifiers']:
            source=source_case(case)
            with self.subTest(case=case):
                plan=compile_plan(source);self.assertFalse(plan.blocked,plan.tickets)
                self.assertEqual(run_plan(plan.to_dict())['datasets']['d']['rows'],[{'x':case['expected']}])

    def test_empty_temporaries_are_contextual_not_global_helper_changes(self):
        from sas_semantics import sas_upcase,sas_lowcase,sas_trim,sas_strip
        for function in (sas_upcase,sas_lowcase,sas_trim,sas_strip):
            with self.assertRaises(ValueError):function('')
        result,_=execute("data d;a=upcase(strip('   '));b=compbl(trimn('   '));c=cats(upcase('   '),'-',trimn('   '));run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'   ','b':'   ','c':'-'.ljust(200)}])

    def test_new_width_and_existing_destination_storage(self):
        result,_=execute("data d;length a $2;length b $2;a=upcase(strip(' abc '));b=cats(substrn('ab',1,2));run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'AB','b':'ab'}])
        self.assertEqual(result['datasets']['d']['schema'],{'a':{'type':'character','length':2},'b':{'type':'character','length':2}})
        self.assertEqual(build_job("data d;length x $1;x=cats(upcase('ab'));run;").code,1)

    def test_existing_parenthesized_primitives_keep_direct_profiles(self):
        source="data d;a=upcase((' x '));b=compbl((' a  b '));c=cats(('a'),('b'));run;"
        plan=compile_plan(source);self.assertFalse(plan.blocked,plan.tickets)
        self.assertFalse(any(op.kind=='function_profile' for op in plan.steps[0].operations))
        result=run_plan(plan.to_dict())
        self.assertEqual(result['datasets']['d']['rows'],[{'a':' X ','b':' a b  ','c':'ab'.ljust(200)}])
        self.assertEqual(build_job("data d;a=trim(('x'));run;").code,2)

    def test_selected_if_functions_and_comparison_aliases(self):
        for call in ["missing(.)","missing(.A)","missing(' ')","verify('12 ','0123456789 ')","anyalpha('a')","anydigit('1')","anyalnum('A')","anyspace(' ')","notdigit('a')"]:
            source='data d;x=0;if '+call+' ge 0 then x=1;else x=2;run;'
            result,_=execute(source);self.assertEqual(result['datasets']['d']['rows'],[{'x':1.}])

    def test_held_call_pairs_and_predicate_shapes(self):
        bad=["x=right(strip(' ab '))","x=reverse(upcase('ab'))","x=cat(upcase('ab'))","x=catt(trimn('ab '))","x=upcase(compbl(strip(trimn(' ab '))))","x=cats(upcase(strip('ab')))","x=substrn(upcase('ab'),1,1)","x=median(abs(1),2)","if anydigit('1') then x=1","if 0=missing(.) then x=1","if anydigit('1')=0 and x=1 then x=1","if anydigit('1')=. then x=1","if missing(.)=-1 then x=1","if missing(.)=32768 then x=1","if indexc('x','x')=1 then x=1"]
        for text in bad:
            with self.subTest(text=text):self.assertIn(build_job('data d;'+text+';run;').code,(1,2))

    def test_profile_is_selected_only_for_actual_consumer(self):
        direct=compile_plan("data d;x=upcase('ab');run;").to_dict()
        self.assertFalse(any(op['kind']=='function_profile' for op in direct['steps'][0]['operations']))
        plan=compile_plan("data d;x=upcase(strip(' ab '));run;")
        self.assertFalse(plan.blocked,plan.tickets);self.assertIn(('function-consumers','DS-108',1),plan.matched)
        self.assertEqual(plan.to_dict()['steps'][0]['operations'][0]['args'],{'profile':PROFILE})
        self.assertEqual(build_job("data d;x=upcase(strip(' ab '));run;",target='cpp').code,2)

    def test_old_profile_validators_stay_strict_without_marker(self):
        from .function_wave import validate_step as wave_validate
        from .trim_strip import validate_step as trim_validate
        plan=compile_plan("data d;x=upcase(strip(' ab '));run;").to_dict();step=plan['steps'][0]
        step['operations']=step['operations'][1:]
        with self.assertRaises(ValueError):wave_validate(step)
        with self.assertRaises(ValueError):trim_validate(step)
        with self.assertRaises(ValueError):run_plan(plan)
        plan=compile_plan("data d;x=lowcase(upcase('a'));run;").to_dict();step=plan['steps'][0]
        step['operations']=step['operations'][1:]
        with self.assertRaises(ValueError):wave_validate(step)
        with self.assertRaises(ValueError):run_plan(plan)

    def test_marker_shape_uniqueness_position_and_genuine_payload(self):
        original=compile_plan("data d;x=upcase(strip(' ab '));run;").to_dict()
        for args in ({},{'profile':'other'},{'profile':PROFILE,'extra':1},None):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']=args
            with self.subTest(args=args),self.assertRaises(ValueError):run_plan(plan)
        for mutation in ('duplicate','move','no-consumer','version','kind','cycle'):
            plan=deepcopy(original);step=plan['steps'][0];ops=step['operations']
            if mutation=='duplicate':ops.insert(0,deepcopy(ops[0]))
            elif mutation=='move':ops.append(ops.pop(0))
            elif mutation=='no-consumer':ops[1]['args']['value']={'kind':'character','value':'x'}
            elif mutation=='version':plan['version']=1
            elif mutation=='kind':step['kind']='merge'
            else:ops[1]['args']['value']['args'][0]=ops[1]['args']['value']
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):run_plan(plan)

    def test_malformed_consumer_call_fields_and_marker_lines_refuse(self):
        original=compile_plan("data d;x=upcase(strip(' ab '));run;").to_dict()
        for field,value in [('name',[]),('name','other'),('args',()),('args',[{'kind':'number','value':True}]),('extra',1)]:
            plan=deepcopy(original);plan['steps'][0]['operations'][1]['args']['value'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):run_plan(plan)
        for line in (False,0,'1'):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['line']=line
            with self.subTest(line=line),self.assertRaises(ValueError):run_plan(plan)

    def test_profile_retains_where_by_retain_array_and_specialized_boundaries(self):
        forms=["data d;set raw;where a='x';x=upcase(strip(a));run;","data d;set raw;by a;x=upcase(strip(a));run;","data d;retain n 0;x=upcase(strip('x'));run;","data d;array vals a b;x=upcase(strip('x'));run;","data d;y=sqrt(4);x=upcase(strip('x'));run;","data d;do i=1 to 2;x=upcase(strip('x'));end;run;","data a;y=sqrt(4);run;data d;x=upcase(strip('x'));run;"]
        for source in forms:
            with self.subTest(source=source):self.assertIn(job_with_inputs(source,catalog(['x'])).code,(1,2))

    def test_static_literals_and_empty_descriptors_validate_eagerly(self):
        for text in ["if 0 then x=cats(substrn('ab',.5,2))","if 0 then x=upcase(strip(1))","if anydigit('x',.5)=0 then x=1","if verify('x',1)=0 then x=1"]:
            self.assertEqual(build_job('data d;'+text+';run;').code,2)
        for source in ['data d;set raw;if 0 then x=upcase(strip(a));run;',"data d;set raw;if anydigit(a)=0 then x=1;run;"]:
            self.assertEqual(job_with_inputs(source,catalog([],spec='number')).code,1)
            self.assertEqual(execute(source,catalog([]))[0]['datasets']['d']['rows'],[])

    def test_reached_only_dynamic_values_and_row_reset(self):
        inputs=catalog([' ab ','é'])
        result,_=execute('data d;set raw;if 0 then x=upcase(strip(a));run;',inputs)
        self.assertEqual([r['x'] for r in result['datasets']['d']['rows']],[' '*8,' '*8])
        inputs=catalog(['abc','123',''])
        result,_=execute("data d;set raw;if anyalpha(a)>0 then flag=1;run;",inputs)
        self.assertEqual([r['flag'] for r in result['datasets']['d']['rows']],[1.,None,None])

    def test_else_if_does_not_evaluate_an_unreached_dynamic_predicate(self):
        inputs=catalog(['é'])
        result,_=execute("data d;set raw;if 1 then x=1;else if anydigit(a)=0 then x=2;run;",inputs)
        self.assertEqual([r['x'] for r in result['datasets']['d']['rows']],[1.])
        self.assertEqual(job_with_inputs("data d;set raw;if 0 then x=1;else if anydigit(a)=0 then x=2;run;",inputs).code,1)

    def test_late_errors_are_atomic_in_runtime_emitted_and_actual_cli(self):
        calls=["x=upcase(strip(a))","x=cats(substrn(a,1,3))","if anydigit(a)=0 then x=1"]
        inputs=catalog(['ab','é'])
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);data=folder/'inputs.json';data.write_text(json.dumps(inputs))
            for index,call in enumerate(calls):
                source="data d;set raw;"+call+";output;put 'made';run;"
                self.assertEqual(job_with_inputs(source,catalog(['ab'])).code,0)
                job=job_with_inputs(source,inputs);self.assertEqual(job.code,1);self.assertIsNone(job.result)
                stream=io.StringIO()
                with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{'inputs':inputs})
                self.assertEqual(stream.getvalue(),'')
                src=folder/(str(index)+'.sas');src.write_text(source);out=folder/('cli-'+str(index))
                run=subprocess.run([sys.executable,'-B','-m','saschi','run',str(src),'--inputs',str(data),'--output',str(out)],capture_output=True,text=True,cwd=ROOT,timeout=60)
                self.assertEqual(run.returncode,1,run.stdout+run.stderr)
                receipt=json.loads((out/'receipt.json').read_text());self.assertFalse(receipt['accepted']);self.assertEqual(receipt['tickets'],[])
                self.assertFalse((out/'result.json').exists());self.assertFalse((out/'observed.json').exists())

    def test_descriptor_order_metadata_and_input_plan_immutability(self):
        inputs=catalog([' ab '],spec={'type':'character','length':8,'label':'Original','format':'$CHAR8.'});saved=deepcopy(inputs)
        plan=compile_plan('data d;set raw;x=upcase(strip(a));if missing(a)=0 then present=1;run;').to_dict();before=deepcopy(plan)
        result=run_plan(plan,inputs)
        self.assertEqual(list(result['datasets']['d']['schema']),['a','x','present'])
        self.assertEqual(result['datasets']['d']['schema']['a'],inputs['raw']['schema']['a'])
        self.assertEqual((inputs,plan),(saved,before));self.assertEqual(run_plan(plan,inputs),result)

    def test_deterministic_emission_across_hash_seeds(self):
        source=GATE.source.read_text();codes=[]
        script='from saschi.emit_py import translate;import sys;sys.stdout.write(translate(sys.stdin.read()).code)'
        for seed in ('1','42','321'):
            run=subprocess.run([sys.executable,'-B','-c',script],input=source,capture_output=True,text=True,cwd=ROOT,env={**os.environ,'PYTHONHASHSEED':seed},timeout=60)
            self.assertEqual(run.returncode,0,run.stderr);codes.append(run.stdout)
        self.assertEqual(codes,[codes[0]]*3)

if __name__=='__main__':unittest.main()
