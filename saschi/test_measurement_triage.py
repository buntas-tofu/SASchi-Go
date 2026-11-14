"""Complete measurement triage with missing summaries, rank and eager selectors."""
from copy import deepcopy
import json,unittest
from examples.verify_measurement_triage import GATE
from examples.wave_gate_common import assert_result
from .expression_test_support import ExpressionContract,execute
from .runtime import run_plan
from .wave3_test_support import FamilyContract


class MeasurementTriageTests(ExpressionContract,unittest.TestCase):
    gate=GATE;phase='where-composition';rule='DS-122'
    test_thirty_independent_R_complete_finish_catalogs=FamilyContract.test_thirty_complete_R_catalogs_empty_order_metadata_and_nonmutation

    def test_frozen_program_retains_missing_rank_ties_rounding_and_row_order(self):
        result=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual([r['rid'] for r in result['datasets']['ranked']['rows']],[1,2,3,4,5,6,7,8])
        self.assertEqual([r['rid'] for r in result['datasets']['triage']['rows']],[1,3,4,5,6,7,8])
        self.assertEqual(list(result['datasets']['triage']['schema'])[-5:],['delta','total','rounded','pick','alert'])
        self.assertEqual(result['log'],['3 ','-2 ','5 ','2 ','1 ','7 ','6 '])
        self.assertEqual(result['datasets']['ranked']['rows'][1]['chosen'],None)

    def test_unchanged_where_rank_guard_prevents_an_excluded_invalid_call(self):
        inputs=json.loads(GATE.inputs.read_text());good=deepcopy(inputs['raw']['rows'][0]);excluded=deepcopy(good);excluded.update(rid=999,k=0,a=1000001)
        inputs['raw']['rows']=[good,excluded];before=deepcopy(inputs)
        observed=execute(GATE.source.read_text(),inputs);assert_result(observed,GATE.witness(inputs))
        self.assertEqual(len(observed['datasets']['ranked']['rows']),1);self.assertEqual(inputs,before)

    def test_late_second_step_intermediate_fault_withholds_all_program_output(self):
        inputs=json.loads(GATE.inputs.read_text());good=deepcopy(inputs['raw']['rows'][0]);bad=deepcopy(good);bad.update(rid=999,a=1000000,b=-1,c=0,k=1)
        inputs['raw']['rows']=[good,bad]
        self.atomic_cli(GATE.source.read_text(),inputs,'numeric')

    def test_unselected_numeric_choice_eagerness_stays_distinct_from_statement_guard(self):
        source='data d;set raw;pick=ifn(flag,abs(a),largest(k,a,b));put pick;run;'
        inputs={'raw':{'schema':{'a':'number','b':'number','k':'number','flag':'number'},'rows':[{'a':3,'b':1,'k':1,'flag':1},{'a':3,'b':1,'k':0,'flag':1}]}}
        self.atomic_cli(source,inputs,'rank')
        guard='data d;set raw;if flag then pick=abs(a);else pick=largest(k,a,b);put pick;run;'
        self.assertEqual(execute(guard,inputs)['log'],['3 ','3 '])

    def test_program_caps_and_malformed_later_step_refuse_atomically(self):
        original=self.original();inputs=json.loads(GATE.inputs.read_text());before=deepcopy(inputs)
        p=deepcopy(original);p['steps'][1]['operations'][2]['args']['value']['extra']=1
        with self.assertRaises(ValueError):run_plan(p,inputs)
        self.assertEqual(inputs,before)
        p=deepcopy(original);p['steps']=p['steps']*9
        with self.assertRaises(ValueError):run_plan(p,inputs)


if __name__=='__main__':unittest.main()
