"""Bounded mixed actions, immutable snapshots and independent portable admission."""
from copy import deepcopy
import contextlib,io,json,unittest
from examples.verify_stateful_decisions import GATE
from examples.wave_gate_common import assert_result
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .wave3_test_support import FamilyContract


def table(rows=None,schema=None):
    return {'raw':{'schema':schema or {'a':'number'},'rows':[{'a':1}] if rows is None else rows}}


def execute(source,inputs=None):
    plan=compile_plan(source)
    if plan.blocked:raise ValueError(str(plan.tickets))
    return run_plan(plan.to_dict(),inputs)


class StatefulDecisionTests(unittest.TestCase):
    atomic_cli=FamilyContract.atomic_cli

    def original(self):return compile_plan(GATE.source.read_text()).to_dict()

    def test_malformed_portable_call_names_raise_validation_errors(self):
        original=compile_plan('data d;set raw;do;x=abs(a);end;run;').to_dict()
        for name in (None,True,[],{},'unqualified'):
            plan=deepcopy(original);pending=[plan]
            while pending:
                node=pending.pop()
                if type(node) is dict:
                    if node.get('kind')=='call':node['name']=name;break
                    pending.extend(node.values())
                elif type(node) is list:pending.extend(node)
            with self.subTest(name=name),self.assertRaises(ValueError):run_plan(plan,table())

    def test_complete_original_hand_R_runtime_emitted_and_nonmutation(self):
        source=GATE.source.read_text();inputs=json.loads(GATE.inputs.read_text());wanted=GATE.program_witness()
        plan=self.original();saved=deepcopy((inputs,plan));code=translate(source).code
        assert_result(run_plan(plan,inputs),wanted)
        stream=io.StringIO();scope={'inputs':inputs}
        with contextlib.redirect_stdout(stream):exec(code,scope)
        assert_result(scope['result'],wanted)
        self.assertEqual(stream.getvalue(),''.join(s+'\n' for s in wanted['log']))
        self.assertEqual((inputs,plan),saved)
        self.assertEqual(code,translate(source).code)
        self.assertEqual(build_job(source,target='cpp').code,2)
        self.assertIn(('decision-groups-and-output','DS-123',1),[tuple(x) for x in plan['matched']])

    def test_empty_input_retains_complete_metadata_and_future_columns(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=[]
        assert_result(run_plan(self.original(),inputs),GATE.witness(inputs))
        rows=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))['datasets']['decision_rows']['rows']
        self.assertTrue(all(r['tail'] is None for r in rows))
        self.assertEqual([r['difference'] for r in rows if r['rid']==2],[7,7])

    def test_explicit_snapshot_and_implicit_suppression_on_skipped_output(self):
        source='data d;set raw;do;x=abs(a);output;x=99;output;end;run;'
        self.assertEqual([r['x'] for r in execute(source,table())['datasets']['d']['rows']],[1,99])
        source='data d;set raw;do;x=abs(a);if 0 then output;end;run;'
        self.assertEqual(execute(source,table())['datasets']['d']['rows'],[])

    def test_nearest_else_and_nested_groups(self):
        source='data d;set raw;do;x=abs(a);if 1 then if 0 then output;else do;x=7;output;end;end;run;'
        self.assertEqual(execute(source,table())['datasets']['d']['rows'],[{'a':1.,'x':7.}])
        source='data d;set raw;if 0 then do;x=abs(a);output;end;else do;x=8;output;end;run;'
        self.assertEqual(execute(source,table())['datasets']['d']['rows'],[{'a':1.,'x':8.}])

    def test_static_skipped_buffer_fault_and_lazy_dynamic_fault(self):
        bad="data d;length text $1;set raw;if 0 then do;text='AB';output;end;run;"
        self.assertTrue(compile_plan(bad).blocked)
        source="data d;length text $2;set raw;if a then do;text=upcase(strip(code));output;end;run;"
        inputs=table([{'a':0,'code':'abc'}],{'a':'number','code':{'type':'character','length':3}})
        self.assertEqual(execute(source,inputs)['datasets']['d']['rows'],[])
        inputs['raw']['schema']['code']='number';inputs['raw']['rows']=[]
        with self.assertRaises(ValueError):execute(source,inputs)

    def test_late_buffer_fault_after_working_output_and_prior_step_is_atomic(self):
        source="data d;length text $2;set raw;if n(a)=1 then do;text=upcase(strip(code));output;put 'kept';end;run;"
        inputs=table([{'a':1,'code':'ab'},{'a':1,'code':'abc'}],{'a':'number','code':{'type':'character','length':3}})
        self.atomic_cli(source,inputs,'buffer')
        self.atomic_cli("data earlier;x=1;put 'prefix';run;"+source,inputs,'buffer')

    def test_both_orders_with_legacy_and_expression_steps(self):
        current='data d;set raw;do;x=abs(a);output;end;run;'
        old='data prior;set raw;y=1;run;'
        pure='data pure;set raw;y=abs(a-1);run;'
        for other in (old,pure):
            for source in (other+current,current+other):
                result=execute(source,table())
                self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'x':1.}])
                self.assertIn('prior' if other==old else 'pure',result['datasets'])

    def test_exact_program_step_operation_and_expression_fields(self):
        original=self.original();bad=[]
        for version in (1,2.0,True,None):
            p=deepcopy(original);p['version']=version;bad.append(p)
        for key in ('program_extra',):
            p=deepcopy(original);p[key]=1;bad.append(p)
        p=deepcopy(original);p['steps'][0]['extra']=1;bad.append(p)
        p=deepcopy(original);p['steps'][0]['operations'][0]['args']['extra']=1;bad.append(p)
        p=deepcopy(original);p['steps'][0]['operations'][0]['line']=True;bad.append(p)
        p=deepcopy(original);p['matched']=[['x','DS-123',True]];bad.append(p)
        p=deepcopy(original);p['steps'][0]['operations'].append(deepcopy(p['steps'][0]['operations'][0]));bad.append(p)
        p=deepcopy(original);p['steps'][0]['operations'].append(p['steps'][0]['operations'].pop(0));bad.append(p)
        p=deepcopy(original);p['steps'][0]['operations'].pop(0);bad.append(p)
        p=deepcopy(original);p['steps'][0]['operations'][1]['args']['extra']=1;bad.append(p)
        for p in bad:
            with self.subTest(index=bad.index(p)),self.assertRaises(ValueError):run_plan(p,{})

    def test_unnecessary_marker_and_false_types_refuse(self):
        p=compile_plan('data d;set raw;x=1;run;').to_dict()
        p['steps'][0]['operations'].insert(0,{'kind':'stateful_profile','line':1,'args':{'profile':'stateful-expressions-v1'}})
        with self.assertRaises(ValueError):run_plan(p,table())
        p=self.original();p['steps'][0]['nodupkey']=0
        with self.assertRaises(ValueError):run_plan(p,{})

    def test_cycles_and_unmarked_nodes_refuse_before_legacy_walkers(self):
        p=self.original();p['steps'][0]['operations'].append(p)
        with self.assertRaises(ValueError):run_plan(p,{})
        p=self.original();p['steps'][0]['operations'].append(p['steps'][0]['operations'])
        with self.assertRaises(ValueError):run_plan(p,{})
        p=self.original();p['steps'][0]['operations'][0]['args']['profile']='function-expressions-v1'
        with self.assertRaises(ValueError):run_plan(p,{})

    def test_call_depth_and_static_call_site_budget(self):
        source='data d;set raw;do;'+'x=abs(a);'*128+'end;run;'
        self.assertEqual(execute(source,table())['datasets']['d']['rows'][0]['x'],1)
        self.assertTrue(compile_plan(source.replace('end;','x=abs(a);end;')).blocked)
        source="data d;set raw;do;text=upcase(compbl(dequote(strip(code))));end;run;"
        inputs=table([{'code':' "a" '}],{'code':{'type':'character','length':8}})
        self.assertEqual(execute(source,inputs)['datasets']['d']['rows'][0]['text'],'A'.ljust(8))
        self.assertTrue(compile_plan(source.replace('strip(code)','strip(upcase(code))')).blocked)

    def test_exact_static_operation_and_action_depth_bounds(self):
        source='data d;set raw;do;x=abs(a);'+'x=1;'*252+'end;run;'
        self.assertEqual(execute(source,table())['datasets']['d']['rows'][0]['x'],1)
        self.assertTrue(compile_plan(source.replace('end;','x=1;end;')).blocked)
        def nested(n):return 'data d;set raw;'+'do;'*n+'x=abs(a);'+'end;'*n+'run;'
        self.assertEqual(execute(nested(16),table())['datasets']['d']['rows'][0]['x'],1)
        self.assertTrue(compile_plan(nested(17)).blocked)

    def test_source_and_portable_step_provenance_bounds(self):
        source='data d0;set raw;do;x=abs(a);end;run;'+''.join('data d'+str(i)+';x=1;run;' for i in range(1,16))
        self.assertEqual(len(execute(source,table())['datasets']),17)
        self.assertTrue(compile_plan(source+'data d16;x=1;run;').blocked)
        p=self.original();inputs=json.loads(GATE.inputs.read_text());p['matched']=[['x','DS-123',1]]*4096
        run_plan(p,inputs);p['matched'].append(['x','DS-123',1])
        with self.assertRaises(ValueError):run_plan(p,inputs)

    def test_column_discovery_bounds_apply_on_empty_inputs(self):
        def source(n):return 'data d;set raw;do;x0=abs(a);'+''.join('x'+str(i)+'=1;' for i in range(1,n))+'end;run;'
        self.assertEqual(len(execute(source(63),table([]))['datasets']['d']['schema']),64)
        with self.assertRaises(ValueError):execute(source(64),table([]))

    def test_input_output_and_log_caps(self):
        rows=[{'a':1}]*10000
        source='data d;set raw;do;x=abs(a);end;run;'
        self.assertEqual(len(execute(source,table(rows))['datasets']['d']['rows']),10000)
        with self.assertRaises(ValueError):execute(source,table(rows+[{'a':1}]))
        source='data d;set raw;do;x=abs(a);output;output;end;run;'
        self.assertEqual(len(execute(source,table(rows[:5000]))['datasets']['d']['rows']),10000)
        with self.assertRaises(ValueError):execute(source,table(rows[:5001]))
        source="data d;set raw;do;x=abs(a);put 'a';put 'b';end;run;"
        self.assertEqual(len(execute(source,table(rows[:5000]))['log']),10000)
        with self.assertRaises(ValueError):execute(source,table(rows[:5001]))

    def test_exact_scheduled_action_cap(self):
        rows=[{'a':1}]*10000
        source='data d;set raw;do;x=abs(a);'+'x=1;'*96+'end;run;'
        self.assertEqual(len(execute(source,table(rows))['datasets']['d']['rows']),10000)
        with self.assertRaises(ValueError):execute(source.replace('end;','x=1;end;'),table(rows))

    def test_scope_refusals_preserve_later_stage_boundaries(self):
        forms=[
            'data d;retain peak 0;set raw;do;peak=max(peak,a);end;run;',
            'data d;set raw;do;total+abs(a);end;run;',
            'data d;set raw;by a;do;x=abs(a);end;run;',
            'data d;set raw;where a>0;do;x=abs(a);end;run;',
            'data d;set raw;do;x=abs(a);if a>0;end;run;',
            'data d;set raw;do;x=lowcase(strip(code));end;run;',
            'data d;set raw;do;x=abs(a);output other;end;run;',
            'data d;set raw;do i=1 to 2;x=abs(a);end;run;',
            'data d;set raw;do;x=abs(a)*2;end;run;',
            'data d;set raw;do;x=abs(a)/2;end;run;',
            'data d;set raw;do;x=abs(a);call missing(x);end;run;',
            'data d;set raw;do;x=abs(a);array v{1} a;end;run;',
        ]
        for source in forms:
            with self.subTest(source=source):
                if source=='data d;retain peak 0;set raw;do;peak=max(peak,a);end;run;':
                    from .stateful_expressions import validate_step
                    plan=compile_plan(source);self.assertFalse(plan.blocked)
                    with self.assertRaises(ValueError):validate_step(plan.to_dict()['steps'][0],max_stage=1)
                    self.assertEqual(execute(source,table())['datasets']['d']['rows'],[{'peak':1.,'a':1.}])
                elif source=='data d;set raw;do;total+abs(a);end;run;':
                    from .stateful_expressions import validate_step
                    plan=compile_plan(source);self.assertFalse(plan.blocked)
                    with self.assertRaises(ValueError):validate_step(plan.to_dict()['steps'][0],max_stage=1)
                    self.assertEqual(execute(source,table())['datasets']['d']['rows'],[{'a':1.,'total':1.}])
                elif source=='data d;set raw;by a;do;x=abs(a);end;run;':
                    from .stateful_expressions import validate_step
                    plan=compile_plan(source);self.assertFalse(plan.blocked)
                    with self.assertRaises(ValueError):validate_step(plan.to_dict()['steps'][0],max_stage=1)
                    self.assertEqual(execute(source,table())['datasets']['d']['rows'],[{'a':1.,'x':1.}])
                elif source=='data d;set raw;do i=1 to 2;x=abs(a);end;run;':
                    from .plan import _compile_before_stateful_expressions
                    from .stateful_expressions import parse_step
                    from .parser import split_statements
                    old=_compile_before_stateful_expressions(source)
                    self.assertFalse(old.blocked)
                    self.assertEqual(compile_plan(source).to_dict(),old.to_dict())
                    self.assertEqual(execute(source,table())['datasets']['d']['rows'],[{'a':1.,'i':3.,'x':1.}])
                    with self.assertRaises(ValueError):parse_step(split_statements(source),source)
                else:self.assertTrue(compile_plan(source).blocked)
