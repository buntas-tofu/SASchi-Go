"""Complete calendar, rank, squares and zero-fuzz reconciliation."""
from copy import deepcopy
import json,os,subprocess,sys,unittest
from examples.verify_quarterly_reconciliation import GATE
from examples.wave_gate_common import assert_result
from .wave3_test_support import FamilyContract,ROOT
from .test_do_counted import execute
from .job import build_job

class QuarterlyReconciliationTests(unittest.TestCase):
    atomic_cli=FamilyContract.atomic_cli

    def test_complete_original_hand_R_runtime_and_emission(self):
        GATE.qualify([]);inputs=json.loads(GATE.inputs.read_text());saved=deepcopy(inputs)
        result,stdout=execute(GATE.source.read_text(),inputs)
        assert_result(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(s+'\n' for s in result['log']));self.assertEqual(inputs,saved)

    def test_all_42_columns_and_discriminating_rows(self):
        result,_=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()));table=result['datasets']['quarters'];rows=table['rows']
        self.assertEqual(len(table['schema']),42)
        self.assertEqual((rows[1]['stamp'],rows[1]['clock']),(-1.,86399.))
        self.assertEqual((rows[2]['year'],rows[2]['month'],rows[2]['day']),(2000.,2.,29.))
        self.assertIsNone(rows[2]['centered']);self.assertEqual(rows[3]['centered'],0.)
        self.assertEqual((rows[5]['centered'],rows[5]['uncentered']),(2.,2999994000005.))
        self.assertEqual((rows[7]['centered'],rows[7]['uncentered']),(2/3,2999998000001.))
        self.assertEqual([rows[i]['rounded'] for i in range(5)],[2.,-4.,.5,4.,.5])
        self.assertEqual(rows[6]['shown'],'        .');self.assertIsNone(rows[6]['chosen'])

    def test_empty_input_preserves_every_descriptor(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=[]
        result,_=execute(GATE.source.read_text(),inputs);assert_result(result,GATE.witness(inputs))
        self.assertEqual(result['log'],[])

    def test_late_invalid_ordinal_is_atomic(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=inputs['raw']['rows'][:2];inputs['raw']['rows'][1]['ordinal']=2023366
        self.atomic_cli(GATE.source.read_text(),inputs,'ordinal')

    def test_late_unselected_invalid_rank_is_atomic(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=inputs['raw']['rows'][:2];inputs['raw']['rows'][1].update(flag=1,k=0)
        self.atomic_cli(GATE.source.read_text(),inputs,'rank')

    def test_hash_seed_emission_and_cpp_refusal(self):
        script='from pathlib import Path;import sys;from saschi.emit_py import translate;print(translate(Path(sys.argv[1]).read_text()).code)'
        codes=[]
        for seed in ['23','91']:
            run=subprocess.run([sys.executable,'-B','-c',script,str(GATE.source)],capture_output=True,text=True,cwd=ROOT,env={**os.environ,'PYTHONHASHSEED':seed},timeout=60)
            self.assertEqual(run.returncode,0,run.stderr);codes.append(run.stdout)
        self.assertEqual(codes[0],codes[1]);self.assertEqual(build_job(GATE.source.read_text(),target='cpp').code,2)

if __name__=='__main__':unittest.main()
