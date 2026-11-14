"""DS-103 fixed CAT widths, blank handling and buffer-state refusals."""
from copy import deepcopy
import contextlib,io,json
from pathlib import Path
import subprocess,sys,tempfile,unittest
from examples.verify_cat_functions import GATE,REFUSALS
from sas_semantics import sas_cat,sas_cats,sas_catt
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .rules import route_function
from .test_do_counted import execute,job_with_inputs

ROOT=Path(__file__).resolve().parent.parent
NAMES=('cat','cats','catt')

def catalog(values,spec=None):
    return {'raw':{'schema':{'a':spec or {'type':'character','length':4}},'rows':[{'a':v} for v in values]}}

class CatFunctionTests(unittest.TestCase):
    def test_independent_original_and_all_stored_fields(self):
        GATE.qualify(REFUSALS)
        result,stdout=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(x+'\n' for x in result['log']))

    def test_three_distinct_blank_policies(self):
        self.assertEqual(sas_cat(' a ',' b '),' a  b ')
        self.assertEqual(sas_cats(' a ',' b '),'ab')
        self.assertEqual(sas_catt(' a ',' b '),' a b')
        result,_=execute("data d;a=cat(' a ',' b ');b=cats(' a ',' b ');c=catt(' a ',' b ');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':' a  b '.ljust(200),'b':'ab'.ljust(200),'c':' a b'.ljust(200)}])
        self.assertTrue(all(v=={'type':'character','length':200} for v in result['datasets']['d']['schema'].values()))

    def test_default_200_differs_from_operator_width(self):
        result,_=execute("data d;length a $3;a='x';joined=cat(a,'y');op=a||'y';run;")
        table=result['datasets']['d']
        self.assertEqual(table['schema']['joined'],{'type':'character','length':200})
        self.assertEqual(table['schema']['op'],{'type':'character','length':4})
        self.assertEqual(table['rows'][0]['joined'],'x  y'.ljust(200))
        self.assertEqual(table['rows'][0]['op'],'x  y')

    def test_empty_and_all_blank_helpers(self):
        self.assertEqual((sas_cat(''),sas_cats(''),sas_catt('')),('','',''))
        self.assertEqual((sas_cat(' ',' '),sas_cats(' ',' '),sas_catt(' ',' ')),('  ','',''))
        result,_=execute("data d;a=cats(' ',' ');b=catt(' ',' ');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':' '*200,'b':' '*200}])

    def test_maximum_trimmed_input_and_arity_boundaries(self):
        self.assertEqual(sas_cats(' '*32767),'')
        self.assertEqual(sas_catt(' '*32767),'')
        for function in (sas_cat,sas_cats,sas_catt):
            self.assertEqual(function(*(['x']*32)),'x'*32)
            self.assertEqual(function('x'*200),'x'*200)
            for args in ((),tuple(['x']*33),('x'*201,),('ok',None)):
                with self.subTest(function=function.__name__,args=len(args)),self.assertRaises(ValueError):function(*args)

    def test_existing_destination_never_masks_overflow(self):
        result,_=execute("data d;length x $2;x=cats(' a ',' b ');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'x':'ab'}])
        for name in NAMES:
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'destination|buffer'):
                execute(f"data d;length x $2;x={name}('abc');run;")

    def test_eager_bad_literal_and_descriptor_checks(self):
        for rhs in ("cat('')",'cats(1)',"catt('x',.A)","cats('é')","cat('"+'x'*201+"')"):
            self.assertEqual(build_job('data d;if 0 then x='+rhs+';run;').code,2)
        for name in NAMES:
            source=f'data d;set raw;if 0 then x={name}(a);run;'
            self.assertEqual(job_with_inputs(source,catalog([],spec='number')).code,1)
            self.assertEqual(execute(source,catalog([]))[0]['datasets']['d']['rows'],[])

    def test_late_trimmed_overflow_after_valid_first_row(self):
        for name in ('cats','catt'):
            source=f'data d;length x $2;set raw;x={name}(a);put x;output;run;'
            self.assertEqual(job_with_inputs(source,catalog(['a'])).code,0)
            job=job_with_inputs(source,catalog(['a','abcd']))
            self.assertEqual(job.code,1);self.assertIsNone(job.result)
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):
                exec(translate(source).code,{'inputs':catalog(['a','abcd'])})
            self.assertEqual(stream.getvalue(),'')

    def test_actual_cli_late_overflow_and_bad_value_are_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            for name in NAMES:
                source=folder/(name+'.sas');inp=folder/(name+'.json');out=folder/('cli-'+name)
                text=f'data d;set raw;x={name}(a);output;put x;run;' if name=='cat' else f'data d;length x $2;set raw;x={name}(a);output;put x;run;'
                values=['ok','é'] if name=='cat' else ['a','abcd']
                source.write_text(text);inp.write_text(json.dumps(catalog(values)))
                run=subprocess.run([sys.executable,'-B','-m','saschi','run',str(source),'--inputs',str(inp),'--output',str(out)],capture_output=True,text=True,cwd=ROOT,timeout=60)
                self.assertEqual(run.returncode,1,run.stdout+run.stderr)
                receipt=json.loads((out/'receipt.json').read_text());self.assertFalse(receipt['accepted']);self.assertEqual(receipt['tickets'],[])
                self.assertFalse((out/'result.json').exists());self.assertFalse((out/'observed.json').exists())

    def test_metadata_order_caller_nonmutation_and_scratch_reset(self):
        spec={'type':'character','length':4,'label':'Original','format':'$CHAR4.'};inputs=catalog(['a','b'],spec);before=deepcopy(inputs)
        source='data d;set raw;if 0 then old=cats(a);new=catt(a);output;run;'
        plan=compile_plan(source).to_dict();saved=deepcopy(plan);result=run_plan(plan,inputs)
        self.assertEqual(list(result['datasets']['d']['schema']),['a','old','new'])
        self.assertEqual(result['datasets']['d']['schema']['a'],spec)
        self.assertEqual([r['old'] for r in result['datasets']['d']['rows']],[' '*200]*2)
        self.assertEqual((inputs,plan),(before,saved));self.assertEqual(run_plan(plan,inputs),result)

    def test_source_provenance_arrays_and_cpp(self):
        for name in NAMES:
            source=f"data d;x={name}('a');run;";plan=compile_plan(source)
            self.assertFalse(plan.blocked,plan.tickets);self.assertIn(('cat-functions','DS-103',1),plan.matched)
            self.assertEqual(route_function(source)[1],'DS-103')
            self.assertEqual(build_job(source,target='cpp').code,2)
            result,_=execute(f'data d;array {name} a b;a=1;b=2;x={name}[2];run;')
            self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'b':2.,'x':2.}])

    def test_held_consumers_and_ordinary_profile_bounds(self):
        for source in ["data d;x=cat('a');put cat('a');run;","data d;if cats('a')='a' then x=1;run;",
                       'data d;set raw;where cats(a);run;',"data d;retain n 0;x=cat('a');run;",
                       "data d;array q a;x=cats('a');run;","data d;x=cats(sqrt(1));run;"]:
            admitted={"data d;if cats('a')='a' then x=1;run;": 1.0}
            if source in admitted:
                from .expression_test_support import assert_new_expression
                assert_new_expression(self,source,[admitted[source]])
            else:
                with self.subTest(source=source):self.assertIn(build_job(source).code,(1,2))

    def test_malformed_portable_calls(self):
        original=compile_plan("data d;x=cats('a');run;").to_dict()
        for args in (None,{},(),[],[{}],[{'kind':'character','value':'a','extra':1}],[{'kind':'number','value':True}]):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']['value']['args']=args
            with self.subTest(args=args),self.assertRaises(ValueError):run_plan(plan)
        plan=deepcopy(original);plan['version']=1
        with self.assertRaises(ValueError):run_plan(plan)

if __name__=='__main__':unittest.main()
