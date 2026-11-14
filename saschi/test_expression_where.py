"""WHERE validates original descriptors and filters before body execution."""
from copy import deepcopy
import unittest
from examples.verify_expression_where import GATE
from .expression_test_support import ExpressionContract,execute
from .expression_test_support import assert_new_expression
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import job_with_inputs


def catalog(rows):return {'raw':{'label':'WHERE timing','schema':{'a':'number','b':'number','flag':'number','k':'number','code':{'type':'character','length':4}},'rows':rows}}


def row(a=3,b=1,flag=1,k=1,code='A'):return {'a':a,'b':b,'flag':flag,'k':k,'code':code}


class WhereExpressionTests(ExpressionContract,unittest.TestCase):
    gate=GATE;phase='where-composition';rule='DS-122'

    def test_CATX_temporary_bridges_and_builders_match_hand_and_independent_R(self):
        inner=GATE.r_cases([('catx',[' ','a','b'])])[0]
        wanted=GATE.r_cases([('length',[inner]),('catx',[' ',inner,'c'])])
        self.assertEqual(wanted,[3.,'a b c'])
        sources=("data d;x=length(catx(' ','a','b'));run;","data d;x=catx(' ',catx(' ','a','b'),'c');run;")
        for source,value in zip(sources,(3.,'a b c'.ljust(200))):
            assert_new_expression(self,source,[value])
            self.assertEqual(build_job(source).result,execute(source))
            scope={};exec(translate(source).code,scope)
            self.assertEqual(scope['result'],execute(source))
        for source in ("data d;if length(catx(' ','a','b')) then x=1;run;","data d;if length(catx(' ','a','b'))=3 then x=1;run;"):
            assert_new_expression(self,source,[1.])
        old=compile_plan("data d;x=catx(' ','a','b');run;").to_dict()
        old['steps'][0]['operations'].insert(0,{'kind':'function_profile','line':1,'args':{'profile':'function-expressions-v1'}})
        with self.assertRaises(ValueError):run_plan(old)

    def test_excluded_dynamic_body_fault_is_not_evaluated_or_printed(self):
        source='data d;set raw;where k>=1 and not missing(a);chosen=largest(k,a,b);put chosen;run;'
        inputs=catalog([row(k=0),row(a=4)])
        result=execute(source,inputs);self.assertEqual(result['log'],['4 '])
        self.assertEqual([r['a'] for r in result['datasets']['d']['rows']],[4])
        self.assertEqual(result['datasets']['d']['label'],'WHERE timing')

    def test_where_reads_original_values_even_after_a_textual_assignment(self):
        source='data d;set raw;a=0;where abs(a)>2;after=abs(a-b);put after;run;'
        inputs=catalog([row(a=1),row(a=3)])
        result=execute(source,inputs);self.assertEqual(len(result['datasets']['d']['rows']),1)
        self.assertEqual(result['datasets']['d']['rows'][0]['a'],0)
        self.assertEqual(result['log'],['1 '])

    def test_where_and_later_subset_keep_both_filter_times_and_prior_logs(self):
        source='data d;set raw;where k>=1;before=abs(a-b);put before;if flag and before>1;after=largest(k,a,b);put after;run;'
        inputs=catalog([row(k=0),row(a=2,flag=0),row(a=4)])
        result=execute(source,inputs);self.assertEqual(result['log'],['1 ','3 ','4 '])
        self.assertEqual([r['a'] for r in result['datasets']['d']['rows']],[4])

    def test_computed_only_names_automatic_state_and_character_truth_refuse_on_empty(self):
        inputs=catalog([])
        for source in ('data d;set raw;score=abs(a);where score>0;run;',"data d;set raw;where upcase(code);run;",'data d;set raw;probe=abs(a-b);where code;run;','data d;set raw;where _n_>1;run;','data d;set raw;probe=abs(a-b);where 1000001;run;'):
            self.assertIn(job_with_inputs(source,inputs).code,(1,2),source)
        source="data d;set raw;where lengthn(strip(code))>0;later=largest(0,a,b);run;"
        self.assertIn(job_with_inputs(source,inputs).code,(1,2))

    def test_whole_catalog_shape_validates_before_excluded_rows_and_tables(self):
        source='data d;set raw;where k>=1;chosen=abs(a-b);run;'
        for inputs in (catalog([dict(row(k=0),extra=1)]),catalog([row(k=0,code=1)]),catalog([row(k=0,a=float('nan'))])):
            with self.assertRaises(ValueError):execute(source,inputs)
        inputs=catalog([row()]);inputs['unused']={'schema':{'x':'number'},'rows':[{'x':float('inf')}]}
        with self.assertRaises(ValueError):execute(source,inputs)

    def test_where_predicate_dynamic_fault_is_atomic_after_a_successful_prefix(self):
        source='data d;set raw;where largest(k,a,b)>0;after=abs(a-b);put after;run;'
        self.atomic_cli(source,catalog([row(k=1),row(k=0)]),'rank')

    def test_unqualified_where_joins_and_operators_remain_held(self):
        for source in ('data d;where abs(a)>0;run;','data d;set raw;where abs(a)>0;where flag;run;','data d;set raw other;where abs(a)>0;run;','data d;set raw;where abs(a)>0;output;run;','data d;set raw;where abs(a)<>0;run;'):
            self.assertTrue(compile_plan(source).blocked,source)

    def test_portable_where_uses_original_schema_and_exact_expression_shapes(self):
        original=self.original();inputs=catalog([])
        for condition in ({'kind':'variable','value':'score'},{'kind':'variable','value':'code'},{'kind':'number','value':1000001},{'kind':'expr_boolean','op':'xor','left':{'kind':'number','value':1},'right':{'kind':'number','value':0}},{'kind':'call','name':'catx'},{'kind':'call','name':'catx','args':[None]},{'kind':'call','name':'catx','args':None}):
            p=deepcopy(original);p['steps'][0]['where']=condition
            with self.assertRaises(ValueError):run_plan(p,inputs)


if __name__=='__main__':unittest.main()
