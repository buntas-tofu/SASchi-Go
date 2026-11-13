"""DS-107 supplied integer epoch seconds and separate component domains."""
from copy import deepcopy
import contextlib,io,json,os
from pathlib import Path
import subprocess,sys,tempfile,unittest
from unittest import mock
from examples.verify_datetime_components import GATE,REFUSALS,MIN_DAY,MAX_DAY,MIN_STAMP,MAX_STAMP
from sas_semantics import sas_qtr,sas_dhms,sas_datepart,sas_timepart,sas_hour,sas_minute,sas_second
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .rules import route_function
from .test_do_counted import execute,job_with_inputs
ROOT=Path(__file__).resolve().parent.parent
UNARY=('qtr','datepart','timepart','hour','minute','second')

def catalog(rows,spec='number'):
    return {'raw':{'schema':{'x':spec},'rows':[{'x':v} for v in rows]}}

class DatetimeComponentTests(unittest.TestCase):
    def test_independent_original_all_components_and_logical_date9(self):
        GATE.qualify(REFUSALS)
        result,stdout=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(line+'\n' for line in result['log']))

    def test_negative_epoch_has_previous_civil_date_and_positive_clock(self):
        self.assertEqual(sas_dhms(-1,23,59,59),-1)
        self.assertEqual((sas_datepart(-1),sas_timepart(-1),sas_hour(-1),sas_minute(-1),sas_second(-1)),(-1,86399,23,59,59))
        self.assertEqual((sas_datepart(-86400),sas_timepart(-86400)),(-1,0))
        self.assertEqual((sas_datepart(-86401),sas_timepart(-86401)),(-2,86399))

    def test_civil_decomposition_roundtrips_integer_seconds(self):
        for value in [MIN_STAMP,-86401,-86400,-1,0,1,86399,86400,MAX_STAMP]:
            self.assertEqual(sas_dhms(sas_datepart(value),sas_hour(value),sas_minute(value),sas_second(value)),value)

    def test_leap_day_and_quarter_transitions(self):
        self.assertEqual([sas_qtr(day) for day in [-1,0,59,90,91,182,274]],[4,1,1,1,2,3,4])
        self.assertEqual(sas_dhms(59,12,34,56),5142896)
        self.assertEqual(sas_datepart(5142896),59)
        self.assertEqual(sas_qtr(MIN_DAY),1);self.assertEqual(sas_qtr(MAX_DAY),4)

    def test_whole_domain_extremes_and_wide_source_literal(self):
        self.assertEqual(sas_dhms(MIN_DAY,0,0,0),MIN_STAMP)
        self.assertEqual(sas_dhms(MAX_DAY,23,59,59),MAX_STAMP)
        result,_=execute(f'data d;a=datepart({MAX_STAMP});b=timepart({MAX_STAMP});run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'a':float(MAX_DAY),'b':86399.}])
        for name in ('datepart','timepart','hour','minute','second'):
            function={'datepart':sas_datepart,'timepart':sas_timepart,'hour':sas_hour,'minute':sas_minute,'second':sas_second}[name]
            for value in [MIN_STAMP-1,MAX_STAMP+1,10**400]:
                with self.subTest(name=name,value=value),self.assertRaises(ValueError):function(value)

    def test_component_input_normalization_is_separate_from_time_extraction(self):
        self.assertEqual((sas_hour(90000),sas_minute(65),sas_second(65)),(1,1,5))
        for args in [(0,24,0,0),(0,0,60,0),(0,0,0,60),(0,-1,0,0),(0,0,0,.5)]:
            with self.subTest(args=args),self.assertRaises(ValueError):sas_dhms(*args)

    def test_missing_propagates_only_after_every_argument_validates(self):
        for function in (sas_qtr,sas_datepart,sas_timepart,sas_hour,sas_minute,sas_second):self.assertIsNone(function(None))
        self.assertIsNone(sas_dhms(None,0,0,0));self.assertIsNone(sas_dhms(0,None,0,0))
        for args in [(None,24,0,0),(0,None,60,0),(None,0,0,True)]:
            with self.assertRaises(ValueError):sas_dhms(*args)

    def test_bad_literals_are_eager_even_if_not_reached(self):
        for rhs in ['qtr(.5)','dhms(.,24,0,0)','datepart(.A)',"hour('1')",'minute(1.5)','second(1e309)']:
            with self.subTest(rhs=rhs):self.assertEqual(build_job('data d;if 0 then x='+rhs+';run;').code,2)

    def test_empty_numeric_descriptor_and_dynamic_laziness(self):
        for name in UNARY:
            source=f'data d;set raw;if 0 then a={name}(x);run;'
            self.assertEqual(job_with_inputs(source,catalog([],{'type':'character','length':4})).code,1)
            self.assertEqual(execute(source,catalog([]))[0]['datasets']['d']['rows'],[])
            result,_=execute(source,catalog([0,.5]))
            self.assertEqual([r['a'] for r in result['datasets']['d']['rows']],[None,None])

    def test_actual_cli_and_emitted_late_bad_values_are_atomic(self):
        calls={name:name+'(x)' for name in UNARY};calls['dhms']='dhms(0,x,0,0)'
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            for name,rhs in calls.items():
                values=[0,24] if name=='dhms' else [0,.5]
                inputs=catalog(values);inp=folder/(name+'.json');inp.write_text(json.dumps(inputs))
                source=folder/(name+'.sas');source.write_text("data d;set raw;a="+rhs+";output;put 'made';run;");out=folder/('cli-'+name)
                self.assertEqual(job_with_inputs(source.read_text(),catalog(values[:1])).code,0)
                run=subprocess.run([sys.executable,'-B','-m','saschi','run',str(source),'--inputs',str(inp),'--output',str(out)],capture_output=True,text=True,cwd=ROOT,timeout=60)
                self.assertEqual(run.returncode,1,run.stdout+run.stderr)
                receipt=json.loads((out/'receipt.json').read_text());self.assertFalse(receipt['accepted']);self.assertEqual(receipt['tickets'],[])
                self.assertFalse((out/'result.json').exists());self.assertFalse((out/'observed.json').exists())
                stream=io.StringIO()
                with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source.read_text()).code,{'inputs':inputs})
                self.assertEqual(stream.getvalue(),'')

    def test_oracle_is_independent_of_process_timezone(self):
        for zone in ['America/New_York','Asia/Tokyo']:
            with mock.patch.dict(os.environ,{'TZ':zone}):self.assertEqual(GATE.program_witness(),json.loads(GATE.expected.read_text()))

    def test_metadata_order_and_caller_nonmutation(self):
        spec={'type':'number','label':'Supplied','format':'DATETIME20.','length':8};inputs=catalog([-1,0],spec);before=deepcopy(inputs)
        plan=compile_plan('data d;set raw;a=datepart(x);b=timepart(x);run;').to_dict();saved=deepcopy(plan);result=run_plan(plan,inputs)
        self.assertEqual(result['datasets']['d']['schema'],{'x':spec,'a':'number','b':'number'})
        self.assertEqual((inputs,plan),(before,saved));self.assertEqual(run_plan(plan,inputs),result)

    def test_provenance_old_array_names_and_cpp(self):
        for name,rhs in [(name,name+'(0)') for name in UNARY]+[('dhms','dhms(0,0,0,0)')]:
            source='data d;x='+rhs+';run;';plan=compile_plan(source)
            self.assertFalse(plan.blocked,plan.tickets);self.assertIn(('datetime-components','DS-107',1),plan.matched)
            self.assertEqual(route_function(source)[1],'DS-107');self.assertEqual(build_job(source,target='cpp').code,2)
            result,_=execute(f'data d;array {name} a b;a=1;b=2;x={name}[2];run;')
            self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'b':2.,'x':2.}])

    def test_malformed_portable_and_unqualified_consumers(self):
        original=compile_plan('data d;x=datepart(0);run;').to_dict()
        for args in (None,{},(),[],[{}],[{'kind':'number','value':True}]):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']['value']['args']=args
            with self.subTest(args=args),self.assertRaises(ValueError):run_plan(plan)
        for source in ['data d;x=datepart(dhms(0,0,0,0));run;','data d;if qtr(0)=1 then x=1;run;',
                       'data d;set raw;where hour(x);run;','data d;retain n 0;x=hour(0);run;']:
            with self.subTest(source=source):self.assertIn(build_job(source).code,(1,2))

if __name__=='__main__':unittest.main()
