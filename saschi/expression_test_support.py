"""Shared full-program and transport checks for the approved composition stages."""
from copy import deepcopy
import contextlib,io,json
from examples.wave_gate_common import assert_result
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan


def execute(source,inputs=None):
    plan=compile_plan(source)
    if plan.blocked:raise ValueError(str(plan.tickets))
    return run_plan(plan.to_dict(),inputs)


class ExpressionContract:
    """Concrete suites bind one immutable complete program and its stage rule."""
    def atomic_cli(self,*args):
        from .wave3_test_support import FamilyContract
        return FamilyContract.atomic_cli(self,*args)

    def original(self):return compile_plan(self.gate.source.read_text()).to_dict()

    def test_complete_original_hand_R_runtime_and_nonmutation(self):
        wanted=self.gate.program_witness();inputs=json.loads(self.gate.inputs.read_text());saved=deepcopy(inputs)
        plan=self.original();before=deepcopy(plan)
        assert_result(run_plan(plan,inputs),wanted)
        self.assertEqual((inputs,plan),(saved,before))
        self.assertIn((self.phase,self.rule,1),[tuple(v) for v in plan['matched']])

    def test_emitted_complete_program_is_deterministic_and_atomic(self):
        source=self.gate.source.read_text();code=translate(source).code
        self.assertEqual(code,translate(source).code)
        self.assertEqual(build_job(source,target='cpp').code,2)
        inputs=json.loads(self.gate.inputs.read_text());scope={'inputs':inputs};stream=io.StringIO()
        with contextlib.redirect_stdout(stream):exec(code,scope)
        assert_result(scope['result'],json.loads(self.gate.expected.read_text()))
        self.assertEqual(stream.getvalue(),''.join(line+'\n' for line in scope['result']['log']))

    def test_portable_marker_and_exact_fields_are_independently_checked(self):
        original=self.original();bad=[]
        for value in (1,2.0,True,None):
            p=deepcopy(original);p['version']=value;bad.append(p)
        p=deepcopy(original);p['extra']=1;bad.append(p)
        p=deepcopy(original);p['matched']=[['x','DS-116',True]];bad.append(p)
        p=deepcopy(original);p['steps'][0]['extra']=1;bad.append(p)
        p=deepcopy(original);p['steps'][0]['operations'].append(deepcopy(p['steps'][0]['operations'][0]));bad.append(p)
        p=deepcopy(original);p['steps'][0]['operations'].append(p['steps'][0]['operations'].pop(0));bad.append(p)
        p=deepcopy(original);p['steps'][0]['operations'][0]['args']['extra']=1;bad.append(p)
        p=deepcopy(original);p['steps'][0]['operations'][0]['line']=True;bad.append(p)
        p=deepcopy(original);p['steps'][0]['operations'][1]['args']['extra']=1;bad.append(p)
        p=deepcopy(original);p['steps'][0]['operations'].append(p['steps'][0]['operations']);bad.append(p)
        for index,p in enumerate(bad):
            with self.subTest(index=index),self.assertRaises(ValueError):run_plan(p,json.loads(self.gate.inputs.read_text()))

    def test_empty_catalog_keeps_all_output_descriptors_and_metadata(self):
        inputs=json.loads(self.gate.inputs.read_text());inputs['raw']['rows']=[]
        assert_result(run_plan(self.original(),inputs),self.gate.witness(inputs))

    def test_old_and_current_steps_work_in_both_program_orders(self):
        source=self.gate.source.read_text();prior='data prior;set raw;control=1;run;'
        inputs=json.loads(self.gate.inputs.read_text());wanted=execute(source,inputs);old=execute(prior,inputs)
        for full in (source+prior,prior+source):
            observed=execute(full,inputs)
            for name,table in wanted['datasets'].items():assert_result({'datasets':{name:observed['datasets'][name]},'log':[]},{'datasets':{name:table},'log':[]})
            self.assertEqual(observed['datasets']['prior'],old['datasets']['prior'])
            self.assertEqual(observed['log'],wanted['log'])


def assert_new_expression(case,source,wanted,inputs=None,field='x'):
    """Keep the prior source refusal and a separate marked-profile hand value."""
    from .plan import _compile_before_function_expressions
    case.assertTrue(_compile_before_function_expressions(source).blocked,source)
    plan=compile_plan(source);case.assertFalse(plan.blocked,plan.tickets)
    case.assertEqual(plan.steps[0].operations[0].args,{'profile':'function-expressions-v1'})
    result=run_plan(plan.to_dict(),inputs)
    case.assertEqual([row[field] for row in result['datasets']['d']['rows']],wanted,source)
