"""Subsetting predicates preserve row-local work and final descriptor timing."""
from copy import deepcopy
import unittest
from examples.verify_expression_subset import GATE
from .expression_test_support import ExpressionContract,execute
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import job_with_inputs


def catalog(rows):return {'raw':{'label':'Subset timing','schema':{'a':'number','b':'number','flag':'number','k':'number'},'rows':rows}}


class SubsetExpressionTests(ExpressionContract,unittest.TestCase):
    gate=GATE;phase='subsetting-if';rule='DS-121'

    def test_prior_PUT_survives_a_rejected_row_and_later_work_is_skipped(self):
        source='data d;set raw;before=abs(a-b);put before;if flag and before>0;after=largest(k,a,b);put after;run;'
        inputs=catalog([{'a':3,'b':1,'flag':0,'k':0},{'a':4,'b':1,'flag':1,'k':1}])
        result=execute(source,inputs);table=result['datasets']['d']
        self.assertEqual(result['log'],['2 ','3 ','4 '])
        self.assertEqual(table['rows'],[{'a':4,'b':1,'flag':1,'k':1,'before':3,'after':4}])
        self.assertEqual(list(table['schema']),['a','b','flag','k','before','after'])
        self.assertEqual(table['label'],'Subset timing')
        inputs['raw']['rows']=inputs['raw']['rows'][:1]
        result=execute(source,inputs);self.assertEqual(result['datasets']['d']['rows'],[])
        self.assertIn('after',result['datasets']['d']['schema']);self.assertEqual(result['log'],['2 '])

    def test_predicate_reads_stored_computed_fields_at_its_own_position(self):
        source='data d;set raw;score=sum(abs(a),abs(b));if score>=3;score=0;put score;run;'
        inputs=catalog([{'a':1,'b':1,'flag':0,'k':1},{'a':2,'b':1,'flag':0,'k':1}])
        result=execute(source,inputs);self.assertEqual(len(result['datasets']['d']['rows']),1)
        self.assertEqual(result['datasets']['d']['rows'][0]['a'],2);self.assertEqual(result['log'],['0 '])

    def test_false_missing_and_zero_drop_rows_while_negative_is_true(self):
        source='data d;set raw;if coalesce(flag,.);after=abs(a-b);run;'
        inputs=catalog([{'a':3,'b':1,'flag':v,'k':1} for v in (None,0,-1,1)])
        result=execute(source,inputs);self.assertEqual([r['flag'] for r in result['datasets']['d']['rows']],[-1,1])

    def test_static_empty_skipped_types_and_literals_do_not_evade_validation(self):
        inputs=catalog([])
        for source in ('data d;set raw;if abs(a)>0;if 1;run;',"data d;set raw;if upcase('A');run;",'data d;set raw;probe=abs(a-b);if 1000001;run;','data d;set raw;if abs(a)>0;later=largest(0,a,b);run;'):
            self.assertIn(job_with_inputs(source,inputs).code,(1,2),source)
        no_input='data d;if abs(-1)>0;run;'
        self.assertTrue(compile_plan(no_input).blocked)

    def test_nested_subset_explicit_OUTPUT_and_multiple_inputs_remain_held(self):
        for tail in ('if flag then if abs(a)>0;','if abs(a)>0;output;','set raw other;if abs(a)>0;'):
            self.assertTrue(compile_plan('data d;set raw;'+tail+'run;').blocked,tail)

    def test_late_predicate_fault_withholds_earlier_PUT_records_and_rows(self):
        source='data d;set raw;before=abs(a-b);put before;if largest(k,a,b)>0;after=1;run;'
        inputs=catalog([{'a':3,'b':1,'flag':1,'k':1},{'a':3,'b':1,'flag':1,'k':0}])
        self.atomic_cli(source,inputs,'rank')

    def test_portable_subset_count_placement_and_fields_are_exact(self):
        original=self.original();index=next(i for i,o in enumerate(original['steps'][0]['operations']) if o['kind']=='subset')
        for mode in ('duplicate','extra','character','literal'):
            p=deepcopy(original);op=p['steps'][0]['operations'][index]
            if mode=='duplicate':p['steps'][0]['operations'].append(deepcopy(op))
            elif mode=='extra':op['args']['extra']=1
            elif mode=='character':op['args']['condition']={'kind':'character','value':'A'}
            else:op['args']['condition']={'kind':'number','value':1000001}
            with self.subTest(mode=mode),self.assertRaises(ValueError):run_plan(p,{})


if __name__=='__main__':unittest.main()
