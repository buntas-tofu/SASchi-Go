"""Complete quoted-record classification across accepted bounded families."""
from copy import deepcopy
import json,os,subprocess,sys,unittest
from examples.verify_quoted_record_classification import GATE
from examples.wave_gate_common import assert_result
from .wave3_test_support import FamilyContract,ROOT
from .test_do_counted import execute
from .emit_py import translate
from .job import build_job

class QuotedRecordClassificationTests(unittest.TestCase):
    atomic_cli=FamilyContract.atomic_cli

    def test_complete_original_hand_R_runtime_and_emission(self):
        GATE.qualify([]);inputs=json.loads(GATE.inputs.read_text());saved=deepcopy(inputs)
        result,stdout=execute(GATE.source.read_text(),inputs)
        assert_result(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(s+'\n' for s in result['log']));self.assertEqual(inputs,saved)

    def test_stored_padding_blank_records_and_duplicate_lookup(self):
        result,_=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        rows=result['datasets']['records']['rows']
        self.assertEqual([r['look'] for r in rows],[1.,2.,None,0.,0.,0.])
        self.assertEqual([r['rank'] for r in rows],[2.,1.,None,0.,1.,2.])
        self.assertEqual(rows[2]['identifier'],'-'.ljust(200));self.assertEqual(rows[2]['blank'],1.)
        self.assertEqual(rows[4]['decision'],'OK'.ljust(200));self.assertEqual(rows[4]['cleaned'],'Ab'.ljust(200))
        self.assertEqual(rows[1]['badpos'],2.)

    def test_empty_input_preserves_complete_descriptor_order(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=[]
        wanted=GATE.witness(inputs);result,_=execute(GATE.source.read_text(),inputs);assert_result(result,wanted)
        self.assertEqual(result['log'],[]);self.assertEqual(len(result['datasets']['records']['schema']),26)

    def test_late_invalid_choice_is_atomic(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=inputs['raw']['rows'][:2];inputs['raw']['rows'][1]['index']=0
        self.atomic_cli(GATE.source.read_text(),inputs,'index')

    def test_late_unselected_rank_is_atomic(self):
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
