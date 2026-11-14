"""Fresh numeric retained state, scratch reset and independent portable validation."""
from copy import deepcopy
import json,unittest
from examples.verify_stateful_retention import GATE
from .expression_test_support import ExpressionContract
from .test_stateful_decisions import execute,table
from .runtime import run_plan
from .plan import compile_plan


class StatefulRetentionTests(ExpressionContract,unittest.TestCase):
    gate=GATE;phase='numeric-retention';rule='DS-124'

    def test_retained_vs_scratch_and_repeated_runs(self):
        inputs=json.loads(GATE.inputs.read_text());plan=self.original()
        first=run_plan(plan,inputs);second=run_plan(plan,inputs)
        self.assertEqual(first,second)
        rows=first['datasets']['retained_rows']['rows']
        self.assertEqual([r['peak'] for r in rows],[2,7,7,7,7,7,7,7])
        self.assertEqual([r['scratch'] for r in rows],[2,7,None,99,4,None,99,0])
        self.assertEqual([r['seen'] for r in rows],[11,12,12,12,13,13,13,14])

    def test_missing_initializer_and_all_skipped_assignment(self):
        source='data d;retain peak .;set raw;if a then do;peak=max(peak,abs(a));end;output;run;'
        inputs=table([{'a':None},{'a':2},{'a':0}])
        self.assertEqual([r['peak'] for r in execute(source,inputs)['datasets']['d']['rows']],[None,2,2])
        inputs=table([{'a':0}])
        self.assertIsNone(execute(source,inputs)['datasets']['d']['rows'][0]['peak'])

    def test_later_top_level_retain_is_declarative_and_preserves_first_use_order(self):
        source='data d;set raw;peak=max(peak,abs(a));retain peak 0;output;run;'
        result=execute(source,table([{'a':-3},{'a':1}]))['datasets']['d']
        self.assertEqual(list(result['schema']),['a','peak'])
        self.assertEqual([r['peak'] for r in result['rows']],[3,3])
        source='data d;set raw;before=peak;peak=max(peak,abs(a));retain peak 4;output;run;'
        result=execute(source,table([{'a':-3},{'a':1}]))['datasets']['d']
        self.assertEqual(list(result['schema']),['a','before','peak'])
        self.assertEqual([r['before'] for r in result['rows']],[4,4])

    def test_retained_input_collision_refuses_even_when_empty(self):
        source='data d;retain peak 0;set raw;peak=max(peak,abs(a));run;'
        inputs=table([],{'a':'number','peak':'number'})
        with self.assertRaisesRegex(ValueError,'collision|input'):execute(source,inputs)
        inputs['raw']['rows']=[{'a':1,'peak':3}]
        with self.assertRaisesRegex(ValueError,'collision|input'):execute(source,inputs)

    def test_retained_assignment_type_is_checked_on_empty_and_skipped_paths(self):
        sources=(
            'data d;set raw;if 0 then total=code;total+abs(a);output;run;',
            'data d;set raw;if 0 then peak=code;retain peak 0;x=abs(a);output;run;',
        )
        schema={'a':'number','code':{'type':'character','length':4}}
        for source in sources:
            for rows in ([],[{'a':1,'code':'x'}]):
                with self.subTest(source=source,rows=rows),self.assertRaisesRegex(ValueError,'retained.*numeric'):
                    execute(source,table(rows,schema))

    def test_static_initializer_assignment_and_duplicate_refusals(self):
        forms=[
            'data d;retain peak 0.5;set raw;peak=max(peak,abs(a));run;',
            'data d;retain peak 1000001;set raw;peak=max(peak,abs(a));run;',
            'data d;retain peak;set raw;peak=max(peak,abs(a));run;',
            "data d;retain peak 'x';set raw;peak=max(peak,abs(a));run;",
            'data d;retain peak abs(1);set raw;peak=max(peak,abs(a));run;',
            'data d;retain peak 0;retain peak 0;set raw;peak=max(peak,abs(a));run;',
            'data d;retain peak 0;set raw;if 0 then peak=0.5;x=max(peak,abs(a));run;',
        ]
        for source in forms:
            with self.subTest(source=source):self.assertTrue(compile_plan(source).blocked)

    def test_reached_fractional_state_fails_but_skipped_value_remains_lazy(self):
        source='data d;retain peak 0;set raw;if flag then peak=max(peak,abs(a));output;run;'
        inputs=table([{'a':0.5,'flag':0}],{'a':'number','flag':'number'})
        self.assertEqual(execute(source,inputs)['datasets']['d']['rows'][0]['peak'],0)
        inputs['raw']['rows'][0]['flag']=1
        with self.assertRaises(ValueError):execute(source,inputs)

    def test_retained_name_limit_and_literal_boundaries(self):
        def source(n):return 'data d;'+''.join('retain x'+str(i)+' 0;' for i in range(n))+'set raw;x0=max(x0,abs(a));output;run;'
        self.assertEqual(execute(source(16),table())['datasets']['d']['rows'][0]['x0'],1)
        self.assertTrue(compile_plan(source(17)).blocked)
        for value in ('1000000','-1000000','.'):
            source='data d;retain peak '+value+';set raw;peak=max(peak,abs(a));output;run;'
            self.assertFalse(compile_plan(source).blocked)

    def test_portable_retention_fields_do_not_authorize_extra_state(self):
        original=self.original();mutations=[]
        for value in ({'kind':'number','value':True},{'kind':'number','value':0.5},{'kind':'number','value':1000001},{'kind':'missing','value':{'missing':'A'}},{'kind':'number','value':0,'extra':1}):
            p=deepcopy(original);p['steps'][0]['retained']['peak']=value;mutations.append(p)
        p=deepcopy(original);p['steps'][0]['retained']['ghost']={'kind':'number','value':0};mutations.append(p)
        p=deepcopy(original);p['steps'][0]['retained'].pop('peak');mutations.append(p)
        for p in mutations:
            with self.subTest(index=mutations.index(p)),self.assertRaises(ValueError):run_plan(p,{})

    def test_late_retained_overflow_is_atomic_after_valid_prefix(self):
        source="data d;retain total 999999;set raw;total=total+abs(a);output;put 'kept';run;"
        self.atomic_cli(source,table([{'a':1},{'a':2}]),'bounded')

    def test_stage1_portable_boundary_and_later_scope_refusals(self):
        from . import stateful_expressions as sx
        p=self.original()
        with self.assertRaises(ValueError):sx.validate_step(p['steps'][0],max_stage=1)
        for source in ('data d;set raw;do;total+abs(a);end;run;','data d;set raw;by a;do;x=abs(a);end;run;'):
            plan=compile_plan(source)
            if source=='data d;set raw;do;total+abs(a);end;run;':
                self.assertFalse(plan.blocked)
                with self.assertRaises(ValueError):sx.validate_step(plan.to_dict()['steps'][0],max_stage=2)
                self.assertEqual(execute(source,table())['datasets']['d']['rows'],[{'a':1.,'total':1.}])
            else:
                self.assertFalse(plan.blocked)
                with self.assertRaises(ValueError):sx.validate_step(plan.to_dict()['steps'][0],max_stage=2)
                self.assertEqual(execute(source,table())['datasets']['d']['rows'],[{'a':1.,'x':1.}])
