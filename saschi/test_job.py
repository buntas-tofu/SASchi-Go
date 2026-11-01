"""Behavioral tests for the shared job path.

The run command, the web workbench, and the showcase all build their
artifacts through build_job. These tests pin the three outcomes a job can
have: accepted with a passing comparison, rejected with a failed
comparison, and blocked by a ticket before anything executes.
"""
import unittest
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from . import cli
from .job import _read_expected, build_job
from .provenance import digest

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


class ExpectedOutputTests(unittest.TestCase):
    def test_byte_json_values_and_errors_match_standard_loader(self):
        import codecs
        import hashlib
        documents = ['{"text":"caf\u00e9 \U0001f600", "rows":[1,1.0,-0.0,null,true]}',
                     ' {"duplicate":1,"duplicate":2} ',
                     '[NaN,Infinity,-Infinity,1e309,"\\ud800"]',
                     '', '{', '{} trailing', '\ufeff{}']
        payloads = [document.encode(encoding)
                    for document in documents
                    for encoding in ('utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le',
                                     'utf-16-be', 'utf-32', 'utf-32-le', 'utf-32-be')]
        payloads += [b'\xff', b'\x00', b'"\xed\xa0\x80"',
                     codecs.BOM_UTF8 + codecs.BOM_UTF8 + b'{}',
                     codecs.BOM_UTF16_LE + b'\x00']
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'expected.json'
            for payload in payloads:
                with self.subTest(payload=repr(payload)):
                    path.write_bytes(payload)
                    try:
                        expected = json.loads(payload)
                    except (ValueError, UnicodeError) as old:
                        with self.assertRaises(type(old)) as new:
                            _read_expected(path)
                        self.assertEqual(str(new.exception), str(old))
                    else:
                        actual, checksum = _read_expected(path)
                        self.assertEqual(json.dumps(actual), json.dumps(expected))
                        self.assertEqual(checksum, hashlib.sha256(payload).hexdigest())

    def test_expected_failures_preserve_receipt_hash_boundary(self):
        import hashlib
        cases = [(b'{', False, 'not requested'),
                 (b'\xff', False, 'not requested'),
                 (b'{}', True, 'not requested'),
                 (b'[]', True, 'not requested'),
                 (b'null', True, 'not requested'),
                 (b'{"out":{"schema":{"x":"number"},"rows":[{"x":9}]}}', True, 'failed')]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'expected.json'
            for payload, has_hash, comparison in cases:
                with self.subTest(payload=payload):
                    path.write_bytes(payload)
                    job = build_job('data out; x=1; run;', expect=path)
                    self.assertEqual(job.code, 1)
                    self.assertFalse(job.receipt['accepted'])
                    self.assertIsNotNone(job.result)
                    self.assertEqual(job.receipt['comparison'], comparison)
                    self.assertEqual('expected_sha256' in job.receipt, has_hash)
                    if has_hash:
                        self.assertEqual(job.receipt['expected_sha256'], hashlib.sha256(payload).hexdigest())
            path.unlink()
            missing = build_job('data out; x=1; run;', expect=path)
            self.assertEqual(missing.code, 1)
            self.assertNotIn('expected_sha256', missing.receipt)

    def test_expected_loading_allocations_stay_bounded(self):
        program = '''
import hashlib, json, tempfile, tracemalloc
from pathlib import Path
from saschi.job import _read_expected
with tempfile.TemporaryDirectory() as td:
    path = Path(td) / 'expected.json'
    path.write_text(json.dumps(['x' * 524288] * 40))
    tracemalloc.start()
    value, checksum = _read_expected(path)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    with path.open('rb') as handle:
        assert checksum == hashlib.file_digest(handle, 'sha256').hexdigest()
    assert len(value) == 40 and all(v == 'x' * 524288 for v in value)
    print(json.dumps({'peak_bytes': peak, 'file_bytes': path.stat().st_size}))
'''
        run = subprocess.run([sys.executable, '-c', program], cwd=REPO,
                             env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(REPO)},
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        observation = json.loads(run.stdout)
        self.assertGreater(observation['file_bytes'], 20_000_000)
        self.assertLess(observation['peak_bytes'], 2.25 * observation['file_bytes'])


def legacy_write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


class JSONArtifactTests(unittest.TestCase):
    def test_json_bytes_match_legacy_format(self):
        values = [None, {}, [], -0.0, 1.7976931348623157e308,
                  {'z': [True, False, None, 1, 1.0, -0.0, 5e-324],
                   'text': '\u00e9\U0001f600\ud800\n\t"\\', 'empty': {}, 'a': []},
                  {7: 'numeric key', False: 'boolean key', None: 'null key'}]
        with tempfile.TemporaryDirectory() as td:
            expected, actual = Path(td) / 'legacy.json', Path(td) / 'streamed.json'
            for value in values:
                with self.subTest(value=repr(value)):
                    legacy_write_json(expected, value)
                    cli.write_json(actual, value)
                    self.assertEqual(actual.read_bytes(), expected.read_bytes())

    def test_invalid_values_preserve_existing_and_absent_destinations(self):
        cycle = []
        cycle.append(cycle)
        values = [{'nested': [float('nan')]}, {'nested': [float('inf')]},
                  {'nested': [float('-inf')]}, {'nested': [object()]},
                  {'nested': [cycle]}, {('invalid', 'key'): 1}]
        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / 'out.json'
            for value in values:
                for present in (False, True):
                    with self.subTest(value=repr(value), present=present):
                        if present:
                            destination.write_bytes(b'original bytes\n')
                        else:
                            destination.unlink(missing_ok=True)
                        with self.assertRaises((ValueError, TypeError)) as old:
                            legacy_write_json(destination, value)
                        with self.assertRaises(type(old.exception)) as new:
                            cli.write_json(destination, value)
                        self.assertEqual(str(new.exception), str(old.exception))
                        self.assertEqual(destination.exists(), present)
                        if present:
                            self.assertEqual(destination.read_bytes(), b'original bytes\n')

    def test_json_serialization_allocations_stay_bounded(self):
        # A fresh process isolates tracing from test-runner allocations. The
        # input exists before tracing; the budget covers serialization only.
        program = '''
import json, tempfile, tracemalloc
from pathlib import Path
from saschi.cli import write_json
data = [{'payload': 'x' * 512}] * 20000
with tempfile.TemporaryDirectory() as td:
    path = Path(td) / 'large.json'
    tracemalloc.start()
    write_json(path, data)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(json.dumps({'peak_bytes': peak, 'output_bytes': path.stat().st_size}))
'''
        run = subprocess.run([sys.executable, '-c', program], cwd=REPO,
                             env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(REPO)},
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        observation = json.loads(run.stdout)
        self.assertGreater(observation['output_bytes'], 10_000_000)
        self.assertLess(observation['peak_bytes'], 2_000_000)

    def test_cli_artifacts_and_receipt_hashes_match_legacy(self):
        cases = [('accepted', 'data out; set raw; run;', 1, 0),
                 ('comparison', 'data out; set raw; run;', 9, 1),
                 ('blocked', 'data out; set raw; x=count(id); run;', 1, 2),
                 ('execution', 'data out; set raw; by id; run;', 1, 1)]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inputs, expected = root / 'inputs.json', root / 'expected.json'
            for name, source, expected_value, code in cases:
                with self.subTest(case=name):
                    source_path = root / (name + '.sas')
                    source_path.write_text(source)
                    rows = [{'id': 2}, {'id': 1}] if name == 'execution' else [{'id': 1}]
                    inputs.write_text(json.dumps({'raw': {'schema': {'id': 'number'}, 'rows': rows}}))
                    expected.write_text(json.dumps({'out': {'schema': {'id': 'number'},
                                                           'rows': [{'id': expected_value}]}}))
                    results = []
                    for writer_name, writer in [('legacy', legacy_write_json), ('streamed', cli.write_json)]:
                        output = root / (name + '-' + writer_name)
                        stdout = io.StringIO()
                        with patch('saschi.cli.write_json', writer), patch('saschi.job.datetime') as clock:
                            clock.now.return_value.isoformat.return_value = '2026-10-26T00:00:00+00:00'
                            with contextlib.redirect_stdout(stdout):
                                actual_code = cli.main(['run', str(source_path), '--inputs', str(inputs),
                                                        '--expect', str(expected), '--output', str(output)])
                        self.assertEqual(actual_code, code)
                        response = json.loads(stdout.getvalue())
                        self.assertEqual(response['accepted'], code == 0)
                        self.assertEqual(response['receipt'], str(output / 'receipt.json'))
                        artifacts = {p.name: p.read_bytes() for p in output.iterdir()}
                        receipt = json.loads(artifacts['receipt.json'])
                        result_name = 'result.json' if code == 0 else 'observed.json'
                        if result_name in artifacts:
                            self.assertEqual(receipt['result_sha256'], digest(output / result_name))
                        results.append(artifacts)
                    self.assertEqual(results[0], results[1])

    def test_mid_write_failure_cleans_staging_and_publishes_nothing(self):
        real_open = io.open

        class FailingWriter:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.handle.close()

            def write(self, text):
                self.handle.write(text[:1])
                raise OSError('injected result write failure')

        def failing_open(file, mode='r', *args, **kwargs):
            handle = real_open(file, mode, *args, **kwargs)
            if mode == 'w' and Path(file).name == 'result.json':
                return FailingWriter(handle)
            return handle

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'job.sas'
            source.write_text('data out; x=1; run;')
            for name, writer in [('legacy', legacy_write_json), ('streamed', cli.write_json)]:
                with self.subTest(writer=name):
                    output = root / name
                    stdout = io.StringIO()
                    with patch('saschi.cli.write_json', writer), patch('io.open', failing_open):
                        with contextlib.redirect_stdout(stdout):
                            code = cli.main(['run', str(source), '--output', str(output)])
                    self.assertEqual(code, 1)
                    self.assertEqual(json.loads(stdout.getvalue()), {'error': 'injected result write failure'})
                    self.assertFalse(output.exists())
                    self.assertEqual(list(root.glob('.saschi-*')), [])


class LogicalReportJobTests(unittest.TestCase):
    """Reports opt into exact comparison and share the job publication boundary."""
    source = 'proc print data=raw noobs; var x; run;'
    inputs = {'raw': {'schema': {'x': 'number'}, 'rows': [{'x': 1}, {'x': 2}]}}
    reports = {'print.txt': 'x\n1\n2\n'}

    def files(self, directory, reports=None, expected=None):
        directory = Path(directory)
        ip = directory / 'input.json'
        rp = directory / 'reports.json'
        ep = directory / 'expected.json'
        ip.write_text(json.dumps(self.inputs))
        rp.write_text(json.dumps(self.reports if reports is None else reports))
        ep.write_text(json.dumps(self.inputs if expected is None else expected))
        return ip, ep, rp

    def test_dataset_and_report_comparators_are_independent_and_exact(self):
        with tempfile.TemporaryDirectory() as td:
            ip, ep, rp = self.files(td)
            job = build_job(self.source, ip, ep, 'python', expect_reports=rp)
            self.assertEqual(job.code, 0, job.receipt)
            self.assertEqual(job.result['reports'], self.reports)
            self.assertEqual(job.receipt['comparison'], 'passed')
            self.assertEqual(job.receipt['report_comparison'], 'passed')
            for report in ({'other.txt': self.reports['print.txt']},
                           {'print.txt': 'x\n2\n1\n'}, {'print.txt': 'x\n1\n2'},
                           {'print.txt': 'x\n1.0\n2\n'}, {'print.txt': 'x\r\n1\r\n2\r\n'}):
                rp.write_text(json.dumps(report))
                wrong = build_job(self.source, ip, ep, expect_reports=rp)
                self.assertEqual(wrong.code, 1)
                self.assertEqual(wrong.receipt['report_comparison'], 'failed')
                self.assertEqual(wrong.result['reports'], self.reports)
            rp.write_text(json.dumps(self.reports))
            ep.write_text(json.dumps({'raw': {'schema': {'x': 'number'}, 'rows': [{'x': True}, {'x': 2}]}}))
            wrong = build_job(self.source, ip, ep, expect_reports=rp)
            self.assertEqual(wrong.code, 1)
            self.assertEqual(wrong.receipt['report_comparison'], 'passed')
            self.assertEqual(wrong.receipt['comparison'], 'failed')

    def test_report_reader_rejects_unsafe_and_malformed_maps(self):
        from .report_artifacts import read_expected_reports
        cases = [b'{', b'[]', b'{}', b'null', b'NaN', b'\xff',
                 b'{"print.txt":"a","print.txt":"b"}',
                 b'{"../print.txt":"x"}', b'{"CON.txt":"x"}',
                 b'{"a/b.txt":"x"}', b'{"print.txt":false}',
                 b'{"print.txt":"\\ud800"}', b' ' * 1048577]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'expected.json'
            for payload in cases:
                with self.subTest(payload=repr(payload[:80])):
                    path.write_bytes(payload)
                    with self.assertRaises(ValueError):
                        read_expected_reports(path)
            path.write_text(json.dumps({'other.txt': 'wrong but safe\n'}))
            self.assertEqual(read_expected_reports(path)[0], {'other.txt': 'wrong but safe\n'})

    def test_cli_publishes_reports_only_on_complete_acceptance(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            ip, ep, rp = self.files(directory)
            source = directory / 'program.sas'
            source.write_text(self.source)
            for name, report, expected, code in (
                    ('good', self.reports, self.inputs, 0),
                    ('wrong-report', {'print.txt': 'wrong\n'}, self.inputs, 1),
                    ('wrong-data', self.reports, {'raw': {'schema': {'x': 'number'}, 'rows': []}}, 1)):
                rp.write_text(json.dumps(report)); ep.write_text(json.dumps(expected))
                out = directory / name
                with contextlib.redirect_stdout(io.StringIO()):
                    actual = cli.main(['run', str(source), '--inputs', str(ip), '--expect', str(ep),
                                       '--expect-reports', str(rp), '--output', str(out)])
                self.assertEqual(actual, code)
                self.assertEqual((out / 'reports/print.txt').exists(), code == 0)
                self.assertEqual((out / 'result.json').exists(), code == 0)
                self.assertEqual((out / 'observed.json').exists(), code != 0)
                if code == 0:
                    self.assertEqual((out / 'reports/print.txt').read_bytes(), b'x\n1\n2\n')

    def test_report_write_and_job_rename_failures_publish_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            ip, ep, rp = self.files(directory)
            source = directory / 'program.sas'; source.write_text(self.source)
            original = Path.open
            def fail_report(path, *args, **kwargs):
                if path.name == 'print.txt':
                    raise OSError('injected report write failure')
                return original(path, *args, **kwargs)
            for name, context in [('write', patch.object(Path, 'open', fail_report)),
                                  ('rename', patch.object(Path, 'rename', side_effect=OSError('injected rename failure')))]:
                output = directory / name
                with context, contextlib.redirect_stdout(io.StringIO()):
                    code = cli.main(['run', str(source), '--inputs', str(ip), '--expect', str(ep),
                                     '--expect-reports', str(rp), '--output', str(output)])
                self.assertEqual(code, 1)
                self.assertFalse(output.exists())
                self.assertEqual(list(directory.glob('.saschi-*')), [])

    def test_old_program_result_and_receipt_have_no_report_fields(self):
        job = build_job('data d;x=1;run;', None, None, 'python')
        self.assertEqual(job.code, 0)
        self.assertNotIn('reports', job.result)
        self.assertFalse(any('report' in key for key in job.receipt))

    def test_export_and_report_comparison_failures_share_publication_boundary(self):
        source_text = ('data exported; file "values.csv" dlm=","; input x; put x; '
                       'datalines;\n1\n2\n;\nrun;\n' + self.source)
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            ip, ep, rp = self.files(directory)
            source = directory / 'program.sas'; source.write_text(source_text)
            xp = directory / 'exports.json'
            for name, report, exports, code in (
                    ('good', self.reports, {'values.csv': '1\n2\n'}, 0),
                    ('bad-report', {'print.txt': 'wrong\n'}, {'values.csv': '1\n2\n'}, 1),
                    ('bad-export', self.reports, {'values.csv': 'wrong\n'}, 1)):
                rp.write_text(json.dumps(report)); xp.write_text(json.dumps(exports))
                output = directory / name
                with contextlib.redirect_stdout(io.StringIO()):
                    actual = cli.main(['run', str(source), '--inputs', str(ip), '--expect-reports', str(rp),
                                       '--expect-exports', str(xp), '--output', str(output)])
                self.assertEqual(actual, code)
                self.assertEqual((output / 'reports').exists(), code == 0)
                self.assertEqual((output / 'exports').exists(), code == 0)
                self.assertEqual((output / 'result.json').exists(), code == 0)

    def test_later_execution_failure_withholds_report_and_export_buffers(self):
        source_text = (self.source + 'data exported; file "values.csv" dlm=","; input x; put x; '
                       'datalines;\n1\n;\nrun;\n'
                       'data bad;set absent;run;')
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td); ip, ep, rp = self.files(directory)
            source = directory / 'program.sas'; source.write_text(source_text)
            out = directory / 'failed'
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(['run', str(source), '--inputs', str(ip), '--output', str(out)])
            self.assertNotEqual(code, 0)
            self.assertFalse((out / 'reports').exists())
            self.assertFalse((out / 'exports').exists())
            self.assertFalse((out / 'result.json').exists())

    def test_deep_report_manifest_produces_a_rejected_job_receipt(self):
        from .report_artifacts import read_expected_reports
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td); ip, ep, rp = self.files(directory)
            rp.write_text('{"print.txt":' + '[' * 10000 + '0' + ']' * 10000 + '}')
            self.assertLess(rp.stat().st_size, 1048576)
            with self.assertRaises(ValueError):
                read_expected_reports(rp)
            job = build_job(self.source, ip, expect_reports=rp)
            self.assertEqual(job.code, 1)
            self.assertFalse(job.receipt['accepted'])
            self.assertEqual(job.receipt['report_comparison'], 'failed')
            self.assertEqual(job.result['reports'], self.reports)
            source = directory / 'program.sas'; source.write_text(self.source)
            output = directory / 'failed'
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(['run', str(source), '--inputs', str(ip),
                                 '--expect-reports', str(rp), '--output', str(output)])
            self.assertEqual(code, 1)
            receipt = json.loads((output / 'receipt.json').read_text())
            self.assertFalse(receipt['accepted'])
            self.assertEqual(receipt['report_comparison'], 'failed')
            self.assertTrue((output / 'observed.json').is_file())
            self.assertFalse((output / 'result.json').exists())
            self.assertFalse((output / 'reports').exists())
            self.assertFalse((output / 'exports').exists())


if __name__ == '__main__':
    unittest.main()
