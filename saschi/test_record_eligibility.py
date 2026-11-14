"""Complete record eligibility and normalization across both filter contexts."""
from copy import deepcopy
import contextlib,io,json,unittest
from examples.verify_record_eligibility import GATE
from examples.wave_gate_common import assert_result
from .expression_test_support import ExpressionContract,execute
from .plan import compile_plan
from .runtime import run_plan
from .wave3_test_support import FamilyContract


class RecordEligibilityTests(ExpressionContract,unittest.TestCase):
    gate=GATE;phase='where-composition';rule='DS-122'
    test_thirty_independent_R_complete_finish_catalogs=FamilyContract.test_thirty_complete_R_catalogs_empty_order_metadata_and_nonmutation

    def test_frozen_program_has_both_distinct_filter_times_and_all_fields(self):
        result=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual([r['rid'] for r in result['datasets']['source_filtered']['rows']],[1,3,4,5,6,7,8])
        self.assertEqual([r['rid'] for r in result['datasets']['eligible']['rows']],[1,3,5,6,7])
        self.assertEqual(list(result['datasets']['eligible']['schema'])[-5:],['canon','identifier','bad','score','status'])
        self.assertEqual(result['datasets']['eligible']['schema']['status'],{'type':'character','length':200})
        self.assertEqual(result['datasets']['eligible']['rows'][3]['canon'],'""'.ljust(16))
        self.assertEqual(result['datasets']['eligible']['rows'][3]['identifier'],'-""'.ljust(200))

    def test_unchanged_program_excludes_a_body_fault_before_execution(self):
        inputs=json.loads(GATE.inputs.read_text());good=deepcopy(inputs['raw']['rows'][0]);bad=deepcopy(good)
        bad.update(rid=999,flag=0,a=None,b=1000001)
        inputs['raw']['rows']=[good,bad];before=deepcopy(inputs)
        wanted=GATE.witness(inputs);observed=execute(GATE.source.read_text(),inputs)
        assert_result(observed,wanted);self.assertEqual(inputs,before)
        self.assertEqual(len(observed['datasets']['source_filtered']['rows']),1)
        self.assertEqual(len(observed['datasets']['eligible']['rows']),1)

    def test_late_second_step_fault_cannot_publish_the_first_complete_dataset(self):
        inputs=json.loads(GATE.inputs.read_text());good=deepcopy(inputs['raw']['rows'][0]);bad=deepcopy(good);bad.update(rid=999,a=1000001)
        inputs['raw']['rows']=[good,bad]
        self.atomic_cli(GATE.source.read_text(),inputs,'numeric')

    def test_bad_or_mixed_markers_in_either_step_refuse_without_input_mutation(self):
        original=self.original();inputs=json.loads(GATE.inputs.read_text());saved=deepcopy(inputs)
        for index in range(2):
            for mutation in ('remove','wrong','duplicate'):
                p=deepcopy(original);ops=p['steps'][index]['operations']
                if mutation=='remove':ops.pop(0)
                elif mutation=='wrong':ops[0]['args']['profile']='function-consumers-v2'
                else:ops.append(deepcopy(ops[0]))
                with self.subTest(index=index,mutation=mutation),self.assertRaises(ValueError):run_plan(p,inputs)
                self.assertEqual(inputs,saved)


if __name__=='__main__':unittest.main()
