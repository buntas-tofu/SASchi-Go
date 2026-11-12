"""DS-101 date bounds,discrete intervals and whole-calendar source execution."""
from copy import deepcopy
from datetime import date
import json
import unittest

from examples.verify_calendar_intervals import GATE,REFUSALS
from sas_semantics import sas_year,sas_source_intck,sas_source_intnx
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .rules import route_function
from .test_do_counted import execute,job_with_inputs


def day(year,month,day):
    return (date(year,month,day)-date(1960,1,1)).days


class CalendarIntervalTests(unittest.TestCase):
    def test_original_complete_independent_calendar_and_records(self):
        GATE.qualify(REFUSALS)
        result,stdout=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(line+'\n' for line in result['log']))

    def test_epoch_and_leap_components(self):
        result,_=execute('data d;y=year(0);m=month(0);d=day(0);leap=day(59);run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'y':1960.,'m':1.,'d':1.,'leap':29.}])

    def test_discrete_boundaries_are_not_elapsed_periods(self):
        result,_=execute("data d;a=intck('MONTH',30,31);b=intck('MONTH',31,30);c=intck('YEAR',0,365);d=intck('DAY',31,30,'DISCRETE');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'b':-1.,'c':0.,'d':-1.}])

    def test_default_beginning_end_and_same_clip(self):
        result,_=execute("data d;a=intnx('MONTH',30,1);b=intnx('MONTH',30,1,'E');c=intnx('MONTH',30,1,'S');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':31.,'b':59.,'c':59.}])

    def test_quarter_month_offset_and_year_anniversary(self):
        self.assertEqual(sas_source_intnx('QTR',day(1960,2,29),1,'S'),day(1960,5,29))
        self.assertEqual(sas_source_intnx('YEAR',59,1,'S'),day(1961,2,28))
        self.assertEqual(sas_source_intnx('MONTH',0,1,'SAMEDAY'),31)

    def test_date_domain_endpoints_and_result_overflow(self):
        minimum,maximum=day(1753,1,1),day(3999,12,31)
        self.assertEqual((sas_year(minimum),sas_year(maximum)),(1753,3999))
        self.assertEqual(sas_source_intck('YEAR',minimum,maximum),2246)
        self.assertEqual(sas_source_intnx('YEAR',minimum,2246,'END'),maximum)
        for start,increment in ((minimum,-1),(maximum,1)):
            with self.assertRaises(ValueError):sas_source_intnx('DAY',start,increment)

    def test_missing_propagates_after_every_argument_validates(self):
        result,_=execute("data d;a=year(.);b=intck('DAY',.,0);c=intnx('MONTH',.,1);d=intnx('MONTH',0,.);run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':None,'b':None,'c':None,'d':None}])
        with self.assertRaises(ValueError):sas_source_intnx('MONTH',None,10001)
        with self.assertRaises(ValueError):sas_source_intck('DAY',None,0,'C')

    def test_invalid_static_dates_and_result_checks_cover_skipped_paths(self):
        for rhs in ('year(1.5)','year(.A)',"month('0')",f'year({day(1753,1,1)-1})',
                    f"intnx('DAY',{day(3999,12,31)},1)","intnx('YEAR',0,10001)"):
            with self.subTest(rhs=rhs):self.assertEqual(build_job('data d;if 0 then x='+rhs+';run;').code,2)

    def test_empty_input_statically_checks_numeric_descriptors(self):
        inputs={'raw':{'schema':{'d':{'type':'character','length':9}},'rows':[]}}
        self.assertEqual(job_with_inputs('data d;set raw;if 0 then y=year(d);run;',inputs).code,1)
        result,_=execute('data d;set raw;if 0 then y=year(d);run;',{'raw':{'schema':{'d':'number'},'rows':[]}})
        self.assertEqual(result['datasets']['d'],{'schema':{'d':'number','y':'number'},'rows':[]})

    def test_dynamic_invalid_values_are_lazy_and_late_failure_is_atomic(self):
        inputs={'raw':{'schema':{'d':'number'},'rows':[{'d':0},{'d':1.5}]}}
        job=job_with_inputs("data d;set raw;y=year(d);output;put 'row';run;",inputs)
        self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])
        result,_=execute('data d;set raw;if 0 then y=year(d);run;',inputs)
        self.assertEqual([row['y'] for row in result['datasets']['d']['rows']],[None,None])

    def test_dynamic_out_of_domain_result_is_atomic(self):
        inputs={'raw':{'schema':{'d':'number','n':'number'},'rows':[{'d':0,'n':1},{'d':day(3999,12,31),'n':1}]}}
        job=job_with_inputs("data d;set raw;x=intnx('DAY',d,n);output;put 'row';run;",inputs)
        self.assertEqual(job.code,1);self.assertIsNone(job.result)

    def test_portable_control_numeric_shape_and_version_checks(self):
        original=compile_plan("data d;x=intnx('MONTH',0,1,'S');run;").to_dict()
        for mutation in ('interval','increment','date','variable','unicode','extra','version'):
            plan=deepcopy(original);call=plan['steps'][0]['operations'][0]['args']['value']
            if mutation=='interval':call['args'][0]['value']='WEEK'
            elif mutation=='increment':call['args'][2]['value']=True
            elif mutation=='date':call['args'][1]['value']=10**400
            elif mutation=='variable':call['args'][0]={'kind':'variable','value':'interval'}
            elif mutation=='unicode':call['args'][3]['value']='ſAME'
            elif mutation=='extra':call['extra']=False
            else:plan['version']=2.0
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):run_plan(plan)

    def test_unqualified_intervals_methods_and_temporary_consumers_refuse(self):
        for rhs in ("intck('MONTH',0,31,'C')","intnx('WEEK',0,1)","intnx('MONTH2',0,1)",
                    "intnx('MONTH',0,1,'M')","intnx('DTMONTH',0,1)",'year(mdy(1,1,2000))','sum(year(0),1)'):
            self.assertIn(build_job('data d;x='+rhs+';run;').code,(1,2))
        with self.assertRaises(ValueError):sas_source_intnx('MONTH',0,1,'ſAME')

    def test_inherited_date_metadata_survives_and_components_are_fresh(self):
        spec={'type':'number','format':'DATE9.','label':'Original'}
        result,_=execute('data d;set raw;y=year(d);run;',{'raw':{'schema':{'d':spec},'rows':[{'d':0}]}})
        self.assertEqual(result['datasets']['d']['schema'],{'d':spec,'y':'number'})

    def test_array_names_and_prior_profile_boundaries_remain(self):
        for name in ('year','month','day','intck','intnx'):
            result,_=execute(f'data d;array {name} a b;a=1;b=2;x={name}[2];run;')
            self.assertEqual(result['datasets']['d']['rows'][0]['x'],2.)
        for source in ('data d;retain n 0;x=year(n);run;','data d;array z a;x=year(a);run;','data d;set raw;where year(a);run;'):
            self.assertIn(build_job(source).code,(1,2))
        self.assertEqual(build_job('data _null_;x=year(0);run;',target='cpp').code,2)

    def test_stored_summaries_and_date9_output_compose(self):
        result,_=execute("data d;a=coalesce(.,0);b=intnx('MONTH',a,1,'S');c=year(b);s=put(b,date9.);put s;run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':0.,'b':31.,'c':1960.,'s':'01FEB1960'}])
        self.assertEqual(result['log'],['01FEB1960 '])

    def test_new_source_route_preserves_reference_rule_on_record(self):
        for name in ('year','month','day','intck','intnx'):
            self.assertEqual(route_function(f'x={name}(d);')[1],'DS-101')


if __name__=='__main__':unittest.main()
