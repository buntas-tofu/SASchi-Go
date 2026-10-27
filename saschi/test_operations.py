"""Failure-path and publication tests for operations and synthesis."""
import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from .cli import main
from .provenance import source_state
import synth


class OperationsTests(unittest.TestCase):
    def test_text_workload_has_deterministic_short_character_groups(self):
        from collections import Counter
        from tools import run_text_workloads as workload
        first = workload.generated_catalog(101, 7)
        self.assertEqual(first, workload.generated_catalog(101, 7))
        self.assertNotEqual(first, workload.generated_catalog(101, 8))
        rows = first['raw']['rows']
        self.assertEqual(len(rows), 101)
        groups = Counter(row['team'] for row in rows)
        self.assertGreater(len(groups), 45)
        self.assertEqual(set(groups.values()), {1, 2, 3})
        for row in rows:
            for name in ('team', 'payload', 'tag', 'note'):
                self.assertTrue(row[name].isascii())
                self.assertLessEqual(len(row[name]), workload.RAW_SCHEMA[name]['length'])
        self.assertTrue(any(row['payload'] == 'NA' for row in rows))
        self.assertTrue(any(row['payload'] == '' for row in rows))
        self.assertTrue(any(len(row['payload']) > 120 for row in rows))
        self.assertLess(len({(row['team'], row['seq']) for row in rows}), len(rows))

    def test_text_workload_hand_pin_preserves_padding_order_and_metadata(self):
        from tools import run_text_workloads as workload
        from .compare import table_equal
        from .plan import compile_plan
        from .runtime import run_plan
        source = (workload.FIXTURE / 'job.sas').read_text()
        plan = compile_plan(source)
        self.assertFalse(plan.blocked, plan.tickets)
        inputs = workload.tiny_catalog()
        original = json.dumps(inputs)
        result = run_plan(plan.to_dict(), inputs)
        expected = {'label': workload.LABEL, 'encoding': 'ascii',
                    'schema': workload.FINAL_SCHEMA, 'rows': workload.fixed_rows()}
        self.assertTrue(table_equal(result['datasets']['snapshots'], expected))
        self.assertEqual(json.dumps(inputs), original)
        self.assertEqual(len(expected['rows']), 10)
        self.assertEqual([r['note'].rstrip() for r in expected['rows']][2], 'NA')

    def test_text_workload_missing_r_writes_a_failed_report(self):
        from tools import run_text_workloads as workload
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'missing-r'
            with patch.dict(os.environ, {'ROSETTA_RSCRIPT': ''}), \
                 patch.object(workload.shutil, 'which', return_value=None), \
                 patch.object(workload, 'invoke') as invoke, \
                 patch.object(sys, 'argv', ['run_text_workloads.py', '--output', str(output), '--sizes', '1']), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(workload.main(), 1)
            invoke.assert_not_called()
            report = json.loads((output / 'report.json').read_text())
            self.assertFalse(report['all_passed'])
            self.assertTrue(report['source_stable'])
            self.assertIn('base R is required', report['error'])
            self.assertEqual(report['cases'], [])
            self.assertEqual(report['refusals'], [])
            self.assertEqual(report['comparator_controls'], [])

    def test_workload_timeout_stops_workers_before_artifacts_are_final(self):
        from tools import run_workloads
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for wrapped in (True, False):
                with self.subTest(timing_wrapper=wrapped):
                    marker = root / ('late-worker-' + str(wrapped))
                    child = ('from pathlib import Path; import time; time.sleep(2); '
                             f'Path({str(marker)!r}).write_text("late")')
                    parent = ('import subprocess, sys, time; '
                              f'subprocess.Popen([sys.executable, "-c", {child!r}]); '
                              'print("worker started", flush=True); time.sleep(10)')
                    with contextlib.ExitStack() as stack:
                        if not wrapped:
                            paths = stack.enter_context(patch.object(run_workloads, 'Path'))
                            paths.return_value.exists.return_value = False
                        result = run_workloads.invoke(root, str(wrapped), [sys.executable, '-c', parent], 0.5)
                    self.assertEqual(result['returncode'], 124)
                    self.assertIn('timed out', (root / (str(wrapped) + '.stderr.log')).read_text())
                    self.assertIn('worker started', (root / (str(wrapped) + '.stdout.log')).read_text())
                    before = {p.name: p.read_bytes() for p in root.iterdir()}
                    time.sleep(2)
                    self.assertFalse(marker.exists(), 'a timed-out descendant kept running')
                    self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)

    def test_workload_missing_r_writes_a_failed_report(self):
        from tools import run_workloads
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'missing-r'
            with patch.dict(os.environ, {'ROSETTA_RSCRIPT': ''}), \
                 patch.object(run_workloads.shutil, 'which', return_value=None), \
                 patch.object(run_workloads, 'invoke') as invoke, \
                 patch.object(sys, 'argv', ['run_workloads.py', '--output', str(output), '--sizes', '1']), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_workloads.main(), 1)
            invoke.assert_not_called()
            report = json.loads((output / 'report.json').read_text())
            self.assertFalse(report['all_passed'])
            self.assertTrue(report['source_stable'])
            self.assertIn('base R is required', report['error'])
            self.assertEqual(report['cases'], [])
            self.assertEqual(report['refusals'], [])
            self.assertEqual(report['comparator_controls'], [])
            self.assertIn('environment', report)
            self.assertIn('source_sha256', report['source'])

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
