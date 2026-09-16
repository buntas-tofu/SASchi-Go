"""Failure-path and publication tests for operations and synthesis."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from .cli import main
from .provenance import source_state
import synth


class OperationsTests(unittest.TestCase):
    def test_run_receipt_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root/'job.sas'; expected = root/'expected.json'; output = root/'out'
            source.write_text('data d; x=1.5; run;')
            expected.write_text(json.dumps({'d': {'schema': {'x':'number'}, 'rows':[{'x':1.5}]}}))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['run',str(source),'--expect',str(expected),'--output',str(output)]),0)
                receipt = json.loads((output/'receipt.json').read_text())
                self.assertTrue(receipt['accepted'])
                self.assertEqual(receipt['comparison'],'passed')
                original = (output/'receipt.json').read_bytes()
                self.assertEqual(main(['run',str(source),'--output',str(output)]),1)
                self.assertEqual((output/'receipt.json').read_bytes(), original)

    def test_failed_comparison_is_not_published_as_result(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'job.sas'; expected=root/'expected.json'; output=root/'out'
            source.write_text('data d; x=1; run;'); expected.write_text('{"d": {}}')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['run',str(source),'--expect',str(expected),'--output',str(output)]),1)
            self.assertFalse((output/'result.json').exists())
            self.assertTrue((output/'observed.json').exists())
            self.assertFalse(json.loads((output/'receipt.json').read_text())['accepted'])

    def test_blocked_job_has_receipt_without_results(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'job.sas'; output=root/'out'; source.write_text('%macro m; %mend;')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['run',str(source),'--output',str(output)]),2)
            self.assertFalse((output/'result.json').exists())
            self.assertTrue(json.loads((output/'receipt.json').read_text())['tickets'])

    def test_source_fingerprint_changes(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'module.py'; p.write_text('x=1\n'); before=source_state(td)['source_sha256']
            p.write_text('x=2\n'); self.assertNotEqual(before,source_state(td)['source_sha256'])

    def test_synthesis_requires_every_planned_case(self):
        incomplete={'ran':0,'fpass':0,'ncaught':0,'blind':0,'ffail':[]}
        with tempfile.TemporaryDirectory() as td, patch.object(synth,'SYNTH_OUT',td), patch.dict(os.environ,{'K':'1'}), patch.object(synth,'run_family',return_value=incomplete), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(synth.main(),1)
            with patch.dict(os.environ,{'K':'0'}), self.assertRaises(ValueError):
                synth.main()

    def test_synthesis_missing_runtime_is_a_failure(self):
        with tempfile.TemporaryDirectory() as td, patch.object(synth,'PY','/missing/python'):
            result,error=synth.run_prog('py','print(1)',Path(td))
            self.assertIsNone(result)
            self.assertTrue(error)

    def test_synthesis_does_not_reuse_a_stale_result(self):
        with tempfile.TemporaryDirectory() as td:
            wd=Path(td); (wd/'results.csv').write_text('x\n1\n')
            result,error=synth.run_prog('py','pass',wd)
            self.assertIsNone(result)
            self.assertEqual(error,'no CSV')
