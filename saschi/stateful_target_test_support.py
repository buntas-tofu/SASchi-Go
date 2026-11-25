"""Complete target integration checks with their original named inputs."""
from copy import deepcopy
from pathlib import Path
import contextlib,io,json,subprocess,sys,tempfile
from .emit_py import translate
from examples.wave_gate_common import assert_result
from .expression_test_support import ExpressionContract,execute
from .runtime import run_plan


class StatefulTargetContract(ExpressionContract):
    def test_empty_catalog_keeps_all_output_descriptors_and_metadata(self):
        inputs=json.loads(self.gate.inputs.read_text());name=next(iter(inputs));inputs[name]['rows']=[]
        assert_result(run_plan(self.original(),inputs),self.gate.witness(inputs))

    def test_old_and_current_steps_work_in_both_program_orders(self):
        source=self.gate.source.read_text();inputs=json.loads(self.gate.inputs.read_text());name=next(iter(inputs))
        prior='data prior;set '+name+';control=1;run;';wanted=execute(source,inputs);old=execute(prior,inputs)
        for full in (source+prior,prior+source):
            observed=execute(full,inputs)
            for name,table in wanted['datasets'].items():assert_result({'datasets':{name:observed['datasets'][name]},'log':[]},{'datasets':{name:table},'log':[]})
            self.assertEqual(observed['datasets']['prior'],old['datasets']['prior'])
            self.assertEqual(observed['log'],wanted['log'])

    def atomic_cli(self,source,inputs,error_fragment):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);src=folder/'job.sas';inp=folder/'inputs.json';out=folder/'failed'
            src.write_text(source, newline='');inp.write_text(json.dumps(inputs), newline='');first=deepcopy(inputs)
            for table in first.values():table['rows']=table['rows'][:1]
            prefix_inputs=folder/'prefix.json';prefix_inputs.write_text(json.dumps(first), newline='');prefix_out=folder/'accepted'
            prefix=subprocess.run([sys.executable,'-B','-m','saschi','run',str(src),'--inputs',str(prefix_inputs),'--output',str(prefix_out)],capture_output=True,text=True,cwd=root,timeout=60)
            self.assertEqual(prefix.returncode,0,prefix.stdout+prefix.stderr)
            self.assertTrue(json.loads((prefix_out/'receipt.json').read_text())['accepted'])
            assert_result(json.loads((prefix_out/'result.json').read_text()),execute(source,first))
            failed=subprocess.run([sys.executable,'-B','-m','saschi','run',str(src),'--inputs',str(inp),'--output',str(out)],capture_output=True,text=True,cwd=root,timeout=60)
            self.assertEqual(failed.returncode,1,failed.stdout+failed.stderr)
            receipt=json.loads((out/'receipt.json').read_text());self.assertFalse(receipt['accepted']);self.assertEqual(receipt['tickets'],[])
            self.assertIn(error_fragment,receipt['error'])
            self.assertFalse((out/'result.json').exists());self.assertFalse((out/'observed.json').exists())
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{'inputs':inputs})
        self.assertEqual(stream.getvalue(),'')
