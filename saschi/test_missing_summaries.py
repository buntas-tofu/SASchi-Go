"""DS-099 missing classification, typed summaries and complete row state."""
from copy import deepcopy
import json
import unittest

from examples.verify_missing_summaries import GATE,REFUSALS
from sas_semantics import sas_n,sas_coalesce,sas_coalescec,sas_row_mean
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .rules import route_function
from .test_do_counted import execute,job_with_inputs


class MissingSummaryTests(unittest.TestCase):
    def test_complete_independent_original_and_emitted_records(self):
        GATE.qualify(REFUSALS)
        result,stdout=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(line+'\n' for line in result['log']))

    def test_empty_blank_period_and_tagged_values_remain_distinct(self):
        result,_=execute("data d;a=missing('');b=missing(' ');c=missing('.');d=missing(._);e=missing(.Z);f=missing(0);g=cmiss('',.,.A,0,'.');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'b':1.,'c':0.,'d':1.,'e':1.,'f':0.,'g':3.}])

    def test_counts_preserve_numeric_type_and_all_missing_results(self):
        result,_=execute("data d;a=n(.,.A,0,2);b=nmiss(.,.Z,0);c=coalesce(.,.);d=mean(.,.);run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':2.,'b':2.,'c':None,'d':None}])

    def test_row_mean_exact_sum_and_binary64_quotient(self):
        result,_=execute("data d;a=mean(2147483647,2147483647,-2147483647);b=mean(1,.,2);run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':2147483647/3,'b':1.5}])
        self.assertEqual(sas_row_mean(*([2147483647]*32)),2147483647)

    def test_coalescec200_new_width_and_declared_truncation(self):
        result,_=execute("data d;length short $2;a=coalescec('','  ',' X ');b=coalescec('',' ');short=coalescec('long');run;")
        table=result['datasets']['d']
        self.assertEqual(table['schema'],{'short':{'type':'character','length':2},'a':{'type':'character','length':200},'b':{'type':'character','length':200}})
        self.assertEqual(table['rows'],[{'short':'lo','a':' X '+' '*197,'b':' '*200}])

    def test_eager_validation_after_nonmissing_choice(self):
        for function,args in [(sas_coalesce,[1,'2']),(sas_coalescec,['A','é']),(sas_coalesce,[1,{'missing':'A'}])]:
            with self.subTest(args=args),self.assertRaises(ValueError):function(*args)
        self.assertEqual(sas_coalescec('A','x'*201),'A')

    def test_argument_count32_and33(self):
        self.assertEqual(sas_n(*([None]*31+[0])),1)
        self.assertEqual(build_job('data d;x=n('+','.join(['0']*32)+');run;').code,0)
        self.assertIn(build_job('data d;x=n('+','.join(['0']*33)+');run;').code,(1,2))

    def test_classification_keeps_tiny_finite_numbers(self):
        self.assertEqual(sas_n(5e-324),1)
        self.assertEqual(sas_coalesce(None,5e-324),5e-324)

    def test_empty_and_skipped_descriptor_checks(self):
        for name,rhs in [('a','n(text)'),('a','coalescec(value)'),('a','mean(text)')]:
            inputs={'raw':{'schema':{'text':{'type':'character','length':4},'value':'number'},'rows':[]}}
            self.assertEqual(job_with_inputs(f'data d;set raw;if 0 then {name}={rhs};run;',inputs).code,1)
        result,_=execute('data d;set raw;if 0 then a=coalescec(text);run;',{'raw':{'schema':{'text':{'type':'character','length':4}},'rows':[]}})
        self.assertEqual(result['datasets']['d']['schema']['a'],{'type':'character','length':200})

    def test_dynamic_invalid_later_argument_fails_atomically(self):
        inputs={'raw':{'schema':{'a':'number','b':'number'},'rows':[{'a':1,'b':2},{'a':1,'b':{'missing':'A'}}]}}
        job=job_with_inputs("data d;set raw;x=coalesce(a,b);output;put 'row';run;",inputs)
        self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])

    def test_late_fractional_mean_is_atomic_and_skipped_value_is_lazy(self):
        inputs={'raw':{'schema':{'a':'number'},'rows':[{'a':1},{'a':1.5}]}}
        job=job_with_inputs("data d;set raw;x=mean(a);output;put 'row';run;",inputs)
        self.assertEqual(job.code,1);self.assertIsNone(job.result)
        result,_=execute('data d;set raw;if 0 then x=mean(a);run;',inputs)
        self.assertEqual([row['x'] for row in result['datasets']['d']['rows']],[None,None])

    def test_literal_overflow_validates_even_when_skipped(self):
        self.assertEqual(build_job("data d;if 0 then x=coalescec('"+'X'*201+"');run;").code,2)
        inputs={'raw':{'schema':{'text':{'type':'character','length':201}},'rows':[{'text':' '},{'text':'X'*201}]}}
        job=job_with_inputs("data d;set raw;x=coalescec(text);output;put 'row';run;",inputs)
        self.assertEqual(job.code,1);self.assertIsNone(job.result)

    def test_portable_tags_shapes_and_versions_are_strict(self):
        original=compile_plan('data d;x=missing(.A);run;').to_dict()
        for value in (None,1,True,{'missing':'?'},{'missing':'A','extra':1}):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']['value']['args'][0]['value']=value
            with self.subTest(value=value),self.assertRaises(ValueError):run_plan(plan)
        plan=deepcopy(original);plan['version']=2.0
        with self.assertRaises(ValueError):run_plan(plan)

    def test_oversized_integer_operands_have_controlled_refusals(self):
        from sas_semantics import sas_scan,sas_find
        for source,index in [("data d;x=n(1);run;",0),("data d;x=scan('a',1,' ');run;",1),("data d;x=find('a','a',1);run;",2)]:
            plan=compile_plan(source).to_dict()
            plan['steps'][0]['operations'][0]['args']['value']['args'][index]['value']=10**400
            with self.subTest(source=source),self.assertRaises(ValueError):run_plan(plan)
        for function,args in [(sas_coalesce,[10**400]),(sas_scan,['a',10**400,' ']),(sas_find,['a','a',10**400])]:
            with self.subTest(function=function.__name__),self.assertRaises(ValueError):function(*args)

    def test_unqualified_conversions_nested_calls_and_call_routine_refuse(self):
        for rhs in ("n('1')","nmiss('')","coalesce(1,.A)","mean(1.5,2)","mean(.A)","missing(upcase('a'))","coalescec(1)"):
            source='data d;x='+rhs+';run;'
            if rhs=="missing(upcase('a'))":
                from .expression_test_support import assert_new_expression
                assert_new_expression(self,source,[0.])
            else:self.assertIn(build_job(source).code,(1,2))
        self.assertEqual(build_job('data d;call missing(a);run;').code,2)

    def test_numeric_array_names_and_other_profiles_preserve_boundaries(self):
        for name in ('missing','n','nmiss','cmiss','coalesce','coalescec','mean'):
            result,_=execute(f'data d;array {name} a b;a=1;b=2;x={name}[2];run;')
            self.assertEqual(result['datasets']['d']['rows'][0]['x'],2.)
        for source in ("data d;retain n 0;x=missing(n);run;","data d;array z a;x=missing(a);run;","data d;set raw;where missing(a);run;"):
            self.assertIn(build_job(source).code,(1,2))
        self.assertEqual(build_job('data _null_;x=n(1);run;',target='cpp').code,2)

    def test_character_groups_compose_through_stored_summary_values(self):
        result,_=execute("data d;a=compress(' a ');b=coalescec(a,'N');c=upcase(b);d=missing(c);run;")
        row=result['datasets']['d']['rows'][0]
        self.assertEqual((row['a'],row['b'],row['c'],row['d']),('a  ','a'+' '*199,'A'+' '*199,0.))

    def test_routes_name_summary_evidence(self):
        for name in ('missing','n','nmiss','cmiss','coalesce','coalescec','mean'):
            self.assertEqual(route_function(f'x={name}(a);')[1],'DS-099')


if __name__=='__main__':unittest.main()
