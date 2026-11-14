"""Implicit retained accumulators and reached expression contributions."""
from copy import deepcopy
import json,unittest
import sas_semantics as sem
from examples.verify_stateful_sums import GATE
from .expression_test_support import ExpressionContract
from .test_stateful_decisions import execute,table
from .plan import compile_plan
from .runtime import run_plan


class StatefulSumTests(ExpressionContract,unittest.TestCase):
    gate=GATE;phase='expression-sum-statements';rule='DS-125'

    def test_implicit_zero_retention_skipped_paths_and_ordinary_addition(self):
        source='data d;set raw;if flag then do;total+abs(a);end;simple=a+1;output;run;'
        inputs=table([{'a':None,'flag':0},{'a':-2,'flag':1},{'a':None,'flag':1},{'a':3,'flag':0}],{'a':'number','flag':'number'})
        rows=execute(source,inputs)['datasets']['d']['rows']
        self.assertEqual([r['total'] for r in rows],[0,2,2,2])
        self.assertEqual([r['simple'] for r in rows],[None,-1,None,4])

    def test_explicit_initializers_override_implicit_zero_even_after_first_use(self):
        source='data d;set raw;before=total;total+abs(a);retain total 5;output;run;'
        result=execute(source,table([{'a':2},{'a':None},{'a':3}]))['datasets']['d']
        self.assertEqual(list(result['schema']),['a','before','total'])
        self.assertEqual([r['before'] for r in result['rows']],[5,7,7])
        self.assertEqual([r['total'] for r in result['rows']],[7,7,10])
        source=source.replace('total 5','total .')
        rows=execute(source,table([{'a':None},{'a':3}]))['datasets']['d']['rows']
        self.assertEqual([r['total'] for r in rows],[0,3])

    def test_multiple_contributions_snapshots_and_assignment_reset(self):
        source='data d;set raw;total+abs(a);output;total+n(a);output;total=0;run;'
        rows=execute(source,table([{'a':-2},{'a':3}]))['datasets']['d']['rows']
        self.assertEqual([r['total'] for r in rows],[2,3,3,4])

    def test_accumulator_input_collision_and_skipped_types_are_eager(self):
        source='data d;set raw;if 0 then do;total+abs(a);end;output;run;'
        with self.assertRaises(ValueError):execute(source,table([],{'a':'number','total':'number'}))
        with self.assertRaises(ValueError):execute(source,table([],{'a':{'type':'character','length':4}}))

    def test_static_contribution_domains_refuse_even_on_skipped_paths(self):
        for value in ('0.5','1000001',"'x'"):
            source='data d;set raw;if 0 then do;total+'+value+';x=abs(a);end;output;run;'
            with self.subTest(value=value):self.assertTrue(compile_plan(source).blocked)

    def test_dynamic_contribution_checks_are_reached_and_overflow_is_atomic(self):
        source='data d;set raw;if flag then do;total+abs(a);end;output;run;'
        inputs=table([{'a':0.5,'flag':0}],{'a':'number','flag':'number'})
        self.assertEqual(execute(source,inputs)['datasets']['d']['rows'][0]['total'],0)
        inputs['raw']['rows'][0]['flag']=1
        with self.assertRaises(ValueError):execute(source,inputs)
        source="data d;retain total 999999;set raw;total+abs(a);output;put 'kept';run;"
        self.atomic_cli(source,table([{'a':1},{'a':1}]),'magnitude')

    def test_accumulator_count_limit_is_shared_with_explicit_state(self):
        def source(n):return 'data d;set raw;'+''.join('x'+str(i)+'+abs(a);' for i in range(n))+'output;run;'
        self.assertEqual(len(execute(source(16),table())['datasets']['d']['schema']),17)
        self.assertTrue(compile_plan(source(17)).blocked)
        source='data d;retain retained 0;set raw;'+''.join('x'+str(i)+'+abs(a);' for i in range(16))+'output;run;'
        self.assertTrue(compile_plan(source).blocked)

    def test_portable_implicit_initializer_and_sum_fields_are_exact(self):
        p=compile_plan('data d;set raw;do;total+abs(a);end;run;').to_dict()
        bad=[]
        for value in ({'kind':'number','value':5},{'kind':'missing','value':None}):
            q=deepcopy(p);q['steps'][0]['retained']['total']=value;bad.append(q)
        q=deepcopy(p);q['steps'][0]['retained'].pop('total');bad.append(q)
        from .stateful_expressions import walk_ops
        for field in ('extra','value'):
            q=deepcopy(p);op=next(o for o in walk_ops(q['steps'][0]['operations']) if o['kind']=='state_sum')
            if field=='extra':op['args']['extra']=1
            else:op['args']['value']={'kind':'number','value':0.5}
            bad.append(q)
        for q in bad:
            with self.subTest(index=bad.index(q)),self.assertRaises(ValueError):run_plan(q,table())

    def test_checked_state_accumulation_boundaries_and_refusals(self):
        self.assertEqual(sem.sas_stateful_expression_accumulate(None,None),0)
        self.assertEqual(sem.sas_stateful_expression_accumulate(-1000000,1000000),0)
        self.assertEqual(sem.sas_stateful_expression_accumulate(999999,1),1000000)
        for left,right in ((1000000,1),(0,0.5),(0,True),(0,float('inf')),(0,{'missing':'A'})):
            with self.subTest(values=(left,right)),self.assertRaises(ValueError):sem.sas_stateful_expression_accumulate(left,right)

    def test_prior_stage_boundaries_and_unordered_by_remain_explicit(self):
        from . import stateful_expressions as sx
        for stage in (1,2):
            with self.subTest(stage=stage),self.assertRaises(ValueError):sx.validate_step(self.original()['steps'][0],max_stage=stage)
        source='data d;set raw;by a;do;total+abs(a);end;run;'
        plan=compile_plan(source);self.assertFalse(plan.blocked)
        with self.assertRaises(ValueError):sx.validate_step(plan.to_dict()['steps'][0],max_stage=3)
        self.assertEqual(execute(source,table())['datasets']['d']['rows'],[{'a':1.,'total':1.}])
