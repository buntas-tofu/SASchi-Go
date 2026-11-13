"""DS-104 ASCII positions, descriptor padding and directional search state."""
from copy import deepcopy
import contextlib,io,json
from pathlib import Path
import subprocess,sys,tempfile,unittest
from examples.verify_character_validation import GATE,REFUSALS
from sas_semantics import sas_verify,sas_anyalpha,sas_anydigit,sas_anyalnum,sas_anyspace,sas_notdigit
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .rules import route_function
from .test_do_counted import execute,job_with_inputs

ROOT=Path(__file__).resolve().parent.parent
ANY=('anyalpha','anydigit','anyalnum','anyspace','notdigit')
NAMES=('verify',)+ANY

def catalog(rows,spec=None,start=False):
    schema={'a':spec or {'type':'character','length':4}}
    if start:schema['start']='number'
    return {'raw':{'schema':schema,'rows':rows}}

class CharacterValidationTests(unittest.TestCase):
    def test_independent_original_keeps_all_six_rows(self):
        GATE.qualify(REFUSALS)
        result,stdout=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(len(result['datasets']['checked']['rows']),6)
        self.assertEqual(stdout,''.join(x+'\n' for x in result['log']))

    def test_results_are_positions_rather_than_booleans(self):
        self.assertEqual([f('9_Z a') for f in (sas_anyalpha,sas_anydigit,sas_anyalnum,sas_anyspace,sas_notdigit)],[3,1,1,4,2])
        self.assertEqual(sas_verify('abcz','a','bc'),4)
        self.assertEqual(sas_verify('abc','a','bc'),0)

    def test_stored_padding_is_significant(self):
        result,_=execute("data d;length a $4;a='12';v=verify(a,'0123456789');n=notdigit(a);s=anyspace(a);run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'12  ','v':3.,'n':3.,'s':3.}])

    def test_empty_helpers_and_all_blank_descriptors(self):
        self.assertEqual(sas_verify('','x'),0)
        self.assertEqual([f('') for f in (sas_anyalpha,sas_anydigit,sas_anyalnum,sas_anyspace,sas_notdigit)],[0]*5)
        self.assertEqual([f('   ') for f in (sas_anyalpha,sas_anydigit,sas_anyalnum,sas_anyspace,sas_notdigit)],[0,0,0,1,1])

    def test_forward_backward_zero_and_missing_start(self):
        self.assertEqual([sas_anydigit('a1b2',s) for s in [1,3,-3,-99,0,5,None]],[2,4,2,4,0,0,2])
        self.assertEqual(sas_notdigit('123   ',-99),6)
        self.assertEqual(sas_anyspace('a b',-99),2)

    def test_dynamic_integral_and_missing_starts(self):
        inputs=catalog([{'a':'a1b2','start':s} for s in [-99,-3,0,1,3,99,None]],start=True)
        result,_=execute('data d;set raw;found=anydigit(a,start);run;',inputs)
        self.assertEqual([r['found'] for r in result['datasets']['d']['rows']],[4.,2.,0.,2.,4.,0.,2.])

    def test_verify_checks_later_excerpts_before_result(self):
        with self.assertRaises(ValueError):sas_verify('abc','abc',1)
        with self.assertRaises(ValueError):sas_anydigit('',.5)
        self.assertEqual(sas_verify(' ','x',' '),0)

    def test_literal_errors_remain_eager_when_skipped(self):
        for rhs in ["anyalpha('')","anydigit('é')",'anyalnum(.)',"anyspace('a',.5)","notdigit('a',.A)","verify('x','x',1)"]:
            with self.subTest(rhs=rhs):self.assertEqual(build_job('data d;if 0 then x='+rhs+';run;').code,2)

    def test_empty_input_still_checks_descriptors(self):
        source='data d;set raw;if 0 then x=anydigit(a);run;'
        self.assertEqual(job_with_inputs(source,catalog([],spec='number')).code,1)
        result,_=execute(source,catalog([]))
        self.assertEqual(result['datasets']['d'],{'schema':{'a':{'type':'character','length':4},'x':'number'},'rows':[]})

    def test_dynamic_invalid_start_is_lazy_or_atomic(self):
        inputs=catalog([{'a':'1','start':1},{'a':'1','start':.5}],start=True)
        result,_=execute('data d;set raw;if 0 then x=anydigit(a,start);run;',inputs)
        self.assertEqual([r['x'] for r in result['datasets']['d']['rows']],[None,None])
        source='data d;set raw;x=anydigit(a,start);put x;output;run;'
        self.assertEqual(job_with_inputs(source,catalog(inputs['raw']['rows'][:1],start=True)).code,0)
        job=job_with_inputs(source,inputs);self.assertEqual(job.code,1);self.assertIsNone(job.result)
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{'inputs':inputs})
        self.assertEqual(stream.getvalue(),'')

    def test_actual_cli_bad_second_row_publishes_no_result(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);data=folder/'inputs.json';data.write_text(json.dumps(catalog([{'a':'1'},{'a':'é'}])))
            for name in NAMES:
                rhs="verify(a,'0123456789 ')" if name=='verify' else name+'(a)'
                source=folder/(name+'.sas');source.write_text('data d;set raw;x='+rhs+';output;put x;run;');out=folder/('cli-'+name)
                self.assertEqual(job_with_inputs(source.read_text(),catalog([{'a':'1'}])).code,0)
                run=subprocess.run([sys.executable,'-B','-m','saschi','run',str(source),'--inputs',str(data),'--output',str(out)],capture_output=True,text=True,cwd=ROOT,timeout=60)
                self.assertEqual(run.returncode,1,run.stdout+run.stderr)
                receipt=json.loads((out/'receipt.json').read_text());self.assertFalse(receipt['accepted']);self.assertEqual(receipt['tickets'],[])
                self.assertFalse((out/'result.json').exists());self.assertFalse((out/'observed.json').exists())

    def test_metadata_order_and_caller_immutability(self):
        spec={'type':'character','length':4,'label':'Original','format':'$CHAR4.'};inputs=catalog([{'a':'a'},{'a':'b'}],spec);before=deepcopy(inputs)
        plan=compile_plan('data d;set raw;x=anyalpha(a);y=notdigit(a);run;').to_dict();saved=deepcopy(plan);result=run_plan(plan,inputs)
        self.assertEqual(result['datasets']['d']['schema'],{'a':spec,'x':'number','y':'number'})
        self.assertEqual((inputs,plan),(before,saved));self.assertEqual(run_plan(plan,inputs),result)

    def test_source_provenance_and_old_array_names(self):
        for name in NAMES:
            rhs="verify('a','a')" if name=='verify' else name+"('a')"
            source='data d;x='+rhs+';run;';plan=compile_plan(source)
            self.assertFalse(plan.blocked,plan.tickets);self.assertIn(('character-validation','DS-104',1),plan.matched)
            self.assertEqual(route_function(source)[1],'DS-104')
            self.assertEqual(build_job(source,target='cpp').code,2)
            result,_=execute(f'data d;array {name} a b;a=1;b=2;x={name}[2];run;')
            self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'b':2.,'x':2.}])

    def test_held_consumers_remain_explicit(self):
        for source in ["data d;if anydigit('1') then x=1;run;",'data d;set raw;where anydigit(a);run;',
                       "data d;retain n 0;x=anydigit('1');run;","data d;array q a;x=anydigit('1');run;",
                       "data d;x=anydigit(cats('1'));run;"]:
            with self.subTest(source=source):self.assertIn(build_job(source).code,(1,2))

    def test_malformed_portable_shapes(self):
        original=compile_plan("data d;x=anydigit('1');run;").to_dict()
        for args in (None,{},(),[],[{}],[{'kind':'character','value':'a','extra':1}],[{'kind':'character','value':'1'},{'kind':'number','value':True}]):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']['value']['args']=args
            with self.subTest(args=args),self.assertRaises(ValueError):run_plan(plan)
        plan=deepcopy(original);plan['version']=1
        with self.assertRaises(ValueError):run_plan(plan)

if __name__=='__main__':unittest.main()
