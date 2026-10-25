"""Composed counted DO/numeric PUT proof; repository and R evidence, no live SAS."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from .emit_py import translate
from .job import build_job
from .test_parser import ROKU_CORPUS

ROOT = Path(__file__).resolve().parent.parent
PROGRAM_SOURCE_SHA256 = '274196284d712ebcb9a4bd8c7dc882ad3529a3c1db6e7594678ba60e7aa8922b'
PROGRAM_STDOUT_SHA256 = '6949ee2ab038131a52c6fd3bb8ff5d3d04ebefaf90a88b6087d6f1a4b9eb68b0'
PROGRAM_RESULT_SHA256 = '3419496e6f2e732a8f0727f3fa9cce5c32a989a6e89dfefbec8a53fa989e286c'


def execute(source):
    translation = translate(source)
    if translation.blocked:
        raise AssertionError(translation.tickets)
    namespace, printed = {}, io.StringIO()
    with contextlib.redirect_stdout(printed):
        exec(translation.code, namespace)
    return namespace['result'], printed.getvalue()


def r_program(path):
    r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    run = subprocess.run([r, str(ROOT / 'examples/do_put_program.R'), str(path)],
                         capture_output=True, text=True, timeout=60, check=True)
    lines = run.stdout.splitlines()
    match = re.fullmatch(r'STATE:([+-]?[0-9]+):([0-9]+)', lines[0])
    if match is None:
        raise AssertionError('independent witness omitted control state')
    records = []
    for line in lines[1:]:
        if not line.startswith('RECORD:'):
            raise AssertionError('unexpected independent witness output')
        records.append(bytes.fromhex(line[7:]).decode('ascii'))
    if len(records) != int(match[2]):
        raise AssertionError('independent witness record count differs')
    return records, int(match[1])


class DoNumericPutIntegrationTests(unittest.TestCase):
    def test_loop_put_output_and_final_index_share_one_pdv(self):
        source = ('data d; before=_n_; do k=3 to -1 by -2; put k; output; end; '
                  'after=k; output; run;')
        result, printed = execute(source)
        self.assertEqual(result['log'], ['3 ', '1 ', '-1 '])
        self.assertEqual(printed, '3 \n1 \n-1 \n')
        self.assertEqual(result['datasets']['d'], {
            'schema': {'before': 'number', 'k': 'number', 'after': 'number'},
            'rows': [{'before': 1., 'k': 3., 'after': None},
                     {'before': 1., 'k': 1., 'after': None},
                     {'before': 1., 'k': -1., 'after': None},
                     {'before': 1., 'k': -3., 'after': -3.}]})

    def test_zero_trip_body_output_still_disables_implicit_output(self):
        result, printed = execute('data d; do i=4 to 2; put i; output; end; run;')
        self.assertEqual(result, {'datasets': {'d': {'schema': {'i': 'number'}, 'rows': []}}, 'log': []})
        self.assertEqual(printed, '')

    def test_nested_numeric_put_guards_cover_zero_trip_and_prior_steps(self):
        for source in ('data d; n=1; do i=2 to 1; put n; end; unused="&name"; run;',
                       'data d; unused="%call(x)"; n=1; do i=1 to 2; put n; end; run;',
                       'data prior; unused="&name"; run; data d; n=1; do i=2 to 1; put n; end; run;'):
            with self.subTest(source=source):
                job = build_job(source)
                self.assertEqual(job.code, 2)
                self.assertIsNone(job.result)
                self.assertIn('macro', str(job.receipt['tickets']).lower())

    def test_zero_trip_numeric_put_still_checks_input_format(self):
        source = 'data d; set raw; n=7; do i=2 to 1; put n; end; run;'
        for rows in ([], [{'n': 3}]):
            with self.subTest(rows=rows), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'inputs.json'
                path.write_text(json.dumps({'raw': {'schema': {'n': {'type': 'number', 'format': '8.2'}}, 'rows': rows}}))
                job = build_job(source, path)
                self.assertEqual(job.code, 1)
                self.assertIsNone(job.result)
                self.assertIn('format', job.receipt['error'].lower())

    def test_later_numeric_put_failure_cannot_publish_earlier_records(self):
        source = 'data d; v=1; do i=1 to 2; put v; v=1.25; output; end; run;'
        job = build_job(source)
        self.assertEqual(job.code, 1)
        self.assertFalse(job.receipt['accepted'])
        self.assertIsNone(job.result)
        translation = translate(source)
        self.assertFalse(translation.blocked, translation.tickets)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed), self.assertRaises(ValueError):
            exec(translation.code, {})
        self.assertEqual(printed.getvalue(), '')


class SteppedLoopCorpusTests(unittest.TestCase):
    def test_unmodified_external_program_complete_result(self):
        path = ROKU_CORPUS / 'loops_for_with_a_specified_step.sas'
        if not path.is_file():
            self.skipTest('Roku corpus not present')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), PROGRAM_SOURCE_SHA256)
        source = path.read_text()
        result, printed = execute(source)
        self.assertEqual(hashlib.sha256(printed.encode()).hexdigest(), PROGRAM_STDOUT_SHA256)
        packed = json.dumps(result, sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual(hashlib.sha256(packed).hexdigest(), PROGRAM_RESULT_SHA256)
        independent, final_index = r_program(path)
        self.assertEqual(result['log'], independent)
        self.assertEqual(len(independent), 5)
        self.assertEqual(final_index, 11)
        self.assertEqual(hashlib.sha256(('\n'.join(independent) + '\n').encode()).hexdigest(), PROGRAM_STDOUT_SHA256)
        job = build_job(source)
        self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.receipt['source_sha256'], PROGRAM_SOURCE_SHA256)
        self.assertEqual(job.receipt['tickets'], [])
        self.assertEqual(job.result, result)
        self.assertEqual(result['datasets'], {})
        print('VERIFIED corpus: loops_for_with_a_specified_step.sas; '
              'source/stdout/complete-result hashes pinned; independent base R agrees; no live SAS')


if __name__ == '__main__':
    unittest.main()
