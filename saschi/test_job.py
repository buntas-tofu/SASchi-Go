"""Behavioral tests for the shared job path.

The run command, the web workbench, and the showcase all build their
artifacts through build_job. These tests pin the three outcomes a job can
have: accepted with a passing comparison, rejected with a failed
comparison, and blocked by a ticket before anything executes.
"""
import unittest
from pathlib import Path

from .job import build_job

REPO = Path(__file__).resolve().parent.parent


class BuildJobTests(unittest.TestCase):
    def test_accepted_workflow_job_passes_its_comparison(self):
        source = (REPO / 'examples' / 'workflow' / 'job.sas').read_text(encoding='utf-8')
        job = build_job(source, REPO / 'examples' / 'workflow' / 'inputs.json',
                        REPO / 'examples' / 'workflow' / 'expected.json')
        self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.code, 0)
        self.assertEqual(job.receipt['comparison'], 'passed')
        self.assertIsNotNone(job.result)
        self.assertIn('joined', job.result['datasets'])

    def test_blocked_job_executes_nothing(self):
        source = 'data d;\n  set raw;\n  d = count(x);\nrun;\n'
        job = build_job(source)
        self.assertFalse(job.receipt['accepted'])
        self.assertEqual(job.code, 2)
        self.assertEqual(job.result, None)
        self.assertEqual(job.receipt['comparison'], 'not requested')
        self.assertTrue(job.receipt['tickets'])
        self.assertIn('blocked', job.receipt['error'])

    def test_failed_comparison_rejects_the_job(self):
        import tempfile
        from .plan import compile_plan
        source = 'data out;\n  set raw;\n  put id=;\nrun;\n'
        inputs = {'raw': {'schema': {'id': 'number'}, 'rows': [{'id': 1.0}, {'id': 2.0}]}}
        plan = compile_plan(source)
        expected = {'out': {'schema': {'id': 'number'}, 'rows': [{'id': 9.9}]}}
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            ip, ep = tdir / 'inputs.json', tdir / 'expected.json'
            import json
            ip.write_text(json.dumps(inputs))
            ep.write_text(json.dumps(expected))
            job = build_job(source, ip, ep)
        self.assertFalse(job.receipt['accepted'])
        self.assertEqual(job.code, 1)
        self.assertEqual(job.receipt['comparison'], 'failed')


if __name__ == '__main__':
    unittest.main()
