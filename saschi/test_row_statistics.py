"""DS-106 missing-aware row statistics and independently bounded arithmetic."""
from copy import deepcopy
from decimal import Decimal,localcontext
import contextlib,io,json,math
from pathlib import Path
import subprocess,sys,tempfile,unittest
from examples.verify_row_statistics import GATE,REFUSALS,close
from sas_semantics import sas_median,sas_range,sas_row_var,sas_row_std,sas_std
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .rules import route_function
from .test_do_counted import execute,job_with_inputs
ROOT=Path(__file__).resolve().parent.parent
NAMES=('median','range','var','std')

def catalog(rows,spec='number'):
    return {'raw':{'schema':{'a':spec},'rows':[{'a':x} for x in rows]}}

class RowStatisticTests(unittest.TestCase):
    def test_independent_original_pairwise_r_and_all_outputs(self):
        GATE.qualify(REFUSALS)
        result,stdout=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,'measured\n'*7)

    def test_missing_singleton_and_sample_divisor(self):
        self.assertEqual(sas_median(1,None,3),2)
        self.assertEqual(sas_range(5,None),0)
        self.assertEqual(sas_row_var(1,None,3),2)
        self.assertEqual(sas_row_std(1,None,3),math.sqrt(2))
        for function in (sas_median,sas_range,sas_row_var,sas_row_std):
            self.assertIsNone(function(None,None))
        self.assertIsNone(sas_row_var(5));self.assertIsNone(sas_row_std(5))

    def test_even_median_ties_and_negative_values(self):
        self.assertEqual(sas_median(-2,5,None,10,0),2.5)
        self.assertEqual(sas_range(-2,5,None,10,0),12)
        self.assertEqual(sas_row_var(5,5,5),0)
        self.assertEqual(sas_row_std(5,5,5),0)
        self.assertEqual(sas_median(5,5,1,9),5)

    def test_large_offset_does_not_destroy_small_variance(self):
        self.assertEqual(sas_row_var(1000000,999999,999998),1)
        self.assertEqual(sas_row_std(1000000,999999,999998),1)
        self.assertEqual(sas_row_var(*([0]*31+[1])),.03125)
        with localcontext() as context:
            context.prec=90;wanted=float((Decimal(1)/Decimal(32)).sqrt())
        self.assertEqual(sas_row_std(*([0]*31+[1])),wanted)

    def test_extreme_alternating_sample_has_decimal_reference(self):
        values=[1000000,-1000000]*16
        with localcontext() as context:
            context.prec=90;variance=Decimal(32)*Decimal(10)**12/Decimal(31)
            wanted_var=float(variance);wanted_std=float(variance.sqrt())
        self.assertTrue(close(sas_row_var(*values),wanted_var))
        self.assertTrue(close(sas_row_std(*values),wanted_std))

    def test_r_comparison_bound_does_not_change_exact_cli_policy(self):
        self.assertTrue(close(1+31*sys.float_info.epsilon,1))
        self.assertFalse(close(1+33*sys.float_info.epsilon,1))
        source='data d;x=std(1,2,3);run;'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'expect.json';path.write_text(json.dumps({'d':{'schema':{'x':'number'},'rows':[{'x':math.nextafter(1.,2.)}]}}))
            job=build_job(source,expect=path)
            self.assertEqual(job.code,1);self.assertEqual(job.receipt['comparison'],'failed')

    def test_later_bad_arguments_are_not_hidden_by_missing(self):
        for function in (sas_median,sas_range,sas_row_var,sas_row_std):
            for args in [(None,'1'),(None,True),(None,{'missing':'A'}),(None,.5),(None,1000001),(float('nan'),None)]:
                with self.subTest(function=function.__name__,args=args),self.assertRaises(ValueError):function(*args)

    def test_existing_procedure_helper_scope_is_preserved(self):
        self.assertEqual(sas_std([1,2,3]),1)
        self.assertNotEqual(sas_std([1,2,3],'N'),sas_row_std(1,2,3))
        with self.assertRaises(ValueError):sas_row_std([1,2,3])

    def test_literals_and_empty_descriptors_check_eagerly(self):
        for rhs in ['median(.A)','range(.5)','var(1000001,1)',"std('1',2)",'median()']:
            self.assertEqual(build_job('data d;if 0 then x='+rhs+';run;').code,2)
        source='data d;set raw;if 0 then x=median(a);run;'
        self.assertEqual(job_with_inputs(source,catalog([],{'type':'character','length':4})).code,1)
        self.assertEqual(execute(source,catalog([]))[0]['datasets']['d']['rows'],[])

    def test_dynamic_fractional_input_is_lazy_or_atomic(self):
        for name in NAMES:
            inputs=catalog([1,.5]);source=f"data d;set raw;x={name}(a,1);output;put 'made';run;"
            self.assertEqual(job_with_inputs(source,catalog([1])).code,0)
            job=job_with_inputs(source,inputs);self.assertEqual(job.code,1);self.assertIsNone(job.result)
            result,_=execute(f'data d;set raw;if 0 then x={name}(a,1);run;',inputs)
            self.assertEqual([r['x'] for r in result['datasets']['d']['rows']],[None,None])
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{'inputs':inputs})
            self.assertEqual(stream.getvalue(),'')

    def test_actual_cli_bad_second_row_is_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);inp=folder/'inputs.json';inp.write_text(json.dumps(catalog([1,.5])))
            for name in NAMES:
                src=folder/(name+'.sas');src.write_text(f"data d;set raw;x={name}(a,1);output;put 'made';run;");out=folder/('cli-'+name)
                run=subprocess.run([sys.executable,'-B','-m','saschi','run',str(src),'--inputs',str(inp),'--output',str(out)],capture_output=True,text=True,cwd=ROOT,timeout=60)
                self.assertEqual(run.returncode,1,run.stdout+run.stderr)
                receipt=json.loads((out/'receipt.json').read_text());self.assertFalse(receipt['accepted']);self.assertEqual(receipt['tickets'],[])
                self.assertFalse((out/'result.json').exists());self.assertFalse((out/'observed.json').exists())

    def test_source_provenance_array_names_and_cpp(self):
        for name in NAMES:
            source=f'data d;x={name}(1,2,3);run;';plan=compile_plan(source)
            self.assertFalse(plan.blocked,plan.tickets);self.assertIn(('row-statistics','DS-106',1),plan.matched)
            self.assertEqual(route_function(source)[1],'DS-106');self.assertEqual(build_job(source,target='cpp').code,2)
            result,_=execute(f'data d;array {name} a b;a=1;b=2;x={name}[2];run;')
            self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'b':2.,'x':2.}])

    def test_metadata_order_and_input_immutability(self):
        inputs=catalog([1,2],{'type':'number','label':'Original','length':8});before=deepcopy(inputs)
        plan=compile_plan('data d;set raw;x=median(a,2);v=var(a,2);run;').to_dict();saved=deepcopy(plan);result=run_plan(plan,inputs)
        self.assertEqual(list(result['datasets']['d']['schema']),['a','x','v'])
        self.assertEqual(result['datasets']['d']['schema']['a'],inputs['raw']['schema']['a'])
        self.assertEqual((inputs,plan),(before,saved));self.assertEqual(run_plan(plan,inputs),result)

    def test_portable_and_unqualified_consumers_refuse(self):
        original=compile_plan('data d;x=var(1,2);run;').to_dict()
        for args in (None,{},(),[],[{}],[{'kind':'number','value':True}]):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']['value']['args']=args
            with self.subTest(args=args),self.assertRaises(ValueError):run_plan(plan)
        for source in ['data d;x=std(mean(1,2),3);run;','data d;if median(1,2)=1 then x=1;run;',
                       'data d;retain n 0;x=var(1,2);run;','data d;set raw;where median(a,1);run;']:
            with self.subTest(source=source):self.assertIn(build_job(source).code,(1,2))

if __name__=='__main__':unittest.main()
