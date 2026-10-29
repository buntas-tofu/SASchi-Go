"""A0 whole-file repository/base-R evidence; no new execution capability."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from .compare import equal
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .test_parser import ROKU_CORPUS

ROOT = Path(__file__).resolve().parent.parent
WITNESS = ROOT / 'examples' / 'corpus_basics.R'
PINS = {
    'hello_world_text.sas': {
        'source': '823cd6fe27f7c8d6f6743d2e4edde6fd018106a2e613308987a304499a76cf41',
        'result': '1e8d41400b927ea06bf44426795c35ed6fad076b30272c9d71483928fdf6dad5',
        'stdout': '0ba904eae8773b70c75333db4de2f3ac45a8ad4ddba1b242f0b3cfc199391dd8',
        'log': ['Hello world!'],
        'accounting': {'source_bytes': 307, 'consumed_bytes': 307, 'statements': 3,
                       'steps': 1, 'put_statements': 1, 'block_comments': 2,
                       'statement_comments': 0, 'null_statements': 0}},
    'comments.sas': {
        'source': 'd131c0c99b20751bad95c2ac0d802e06a512174e4af8767341e6fae99441f418',
        'result': '98741fd94867a7760f30078f61f9f73f28402b8e027b31f95bca72f30bca0bb8',
        'stdout': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        'log': [],
        'accounting': {'source_bytes': 253, 'consumed_bytes': 253, 'statements': 0,
                       'steps': 0, 'put_statements': 0, 'block_comments': 2,
                       'statement_comments': 2, 'null_statements': 0}}}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def r_program(path):
    rscript = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([rscript, str(WITNESS), str(path)], capture_output=True,
                          text=True, timeout=30)


def program_witness(path):
    process = r_program(path)
    if process.returncode:
        raise ValueError(process.stderr.strip())
    accounting = {}; logs = []
    names = {'BYTES': 'source_bytes', 'CONSUMED': 'consumed_bytes',
             'STATEMENTS': 'statements', 'STEPS': 'steps', 'PUTS': 'put_statements',
             'BLOCK_COMMENTS': 'block_comments', 'STATEMENT_COMMENTS': 'statement_comments',
             'NULL_STATEMENTS': 'null_statements'}
    for line in process.stdout.splitlines():
        tag, value = line.split(':', 1)
        if tag == 'LOG':
            logs.append(bytes.fromhex(value).decode('ascii'))
        else:
            key = names[tag]
            if key in accounting:
                raise AssertionError('duplicate R accounting field')
            accounting[key] = int(value)
    if set(accounting) != set(names.values()):
        raise AssertionError('incomplete R source accounting')
    if accounting['source_bytes'] != accounting['consumed_bytes']:
        raise AssertionError('R witness left unconsumed source bytes')
    return {'datasets': {}, 'log': logs}, accounting


def emitted(source):
    translated = translate(source)
    if translated.blocked:
        raise AssertionError(translated.tickets)
    stream = io.StringIO(); namespace = {}
    with contextlib.redirect_stdout(stream):
        exec(translated.code, namespace)
    return namespace['result'], stream.getvalue()


def expected(name):
    return {'datasets': {}, 'log': list(PINS[name]['log'])}


class CorpusBasicsTests(unittest.TestCase):
    def check_cli(self, path, result):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'job'
            process = subprocess.run([sys.executable, '-m', 'saschi', 'run', str(path),
                                      '--output', str(output)], capture_output=True,
                                     text=True, timeout=30)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertEqual(process.stderr, '')
            self.assertEqual(json.loads(process.stdout),
                             {'accepted': True, 'receipt': str(output / 'receipt.json')})
            self.assertEqual(json.loads((output / 'result.json').read_text()), result)
            receipt = json.loads((output / 'receipt.json').read_text())
            self.assertTrue(receipt['accepted'])
            self.assertEqual(receipt['source_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(receipt['result_sha256'],
                             hashlib.sha256((output / 'result.json').read_bytes()).hexdigest())
            self.assertEqual(receipt['comparison'], 'not requested')
            self.assertFalse((output / 'observed.json').exists())
            self.assertFalse(receipt['tickets'])

    def check_complete(self, name):
        path = ROKU_CORPUS / name; pin = PINS[name]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), pin['source'])
        source = path.read_text(); plan = compile_plan(source)
        self.assertFalse(plan.blocked, plan.tickets)
        result, stdout = emitted(source); independent, accounting = program_witness(path)
        self.assertEqual(result, expected(name)); self.assertEqual(independent, result)
        self.assertEqual(run_plan(plan.to_dict()), result)
        self.assertEqual(accounting, pin['accounting'])
        self.assertEqual(stdout, ''.join(record + '\n' for record in pin['log']))
        self.assertEqual(digest(result), pin['result'])
        self.assertEqual(hashlib.sha256(stdout.encode()).hexdigest(), pin['stdout'])
        job = build_job(source)
        self.assertEqual(job.code, 0, job.receipt.get('error'))
        self.assertEqual(job.result, result); self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.receipt['completeness']['n_statements'], accounting['statements'])
        self.check_cli(path, result)
        print(f'VERIFIED corpus: {name}; entire source/result/stdout pins, hand accounting, '
              'independent base R and source/runtime/emitted/CLI; no live SAS')

    def test_entire_unchanged_hello_world_program(self):
        self.check_complete('hello_world_text.sas')

    def test_entire_unchanged_comment_only_program(self):
        self.check_complete('comments.sas')

    def test_noop_is_explicit_zero_execution(self):
        source = (ROKU_CORPUS / 'comments.sas').read_text()
        plan = compile_plan(source)
        self.assertEqual(plan.steps, []); self.assertEqual(plan.matched, [])
        self.assertEqual(plan.tickets, []); self.assertEqual(plan.version, 2)
        job = build_job(source)
        self.assertEqual(job.code, 0); self.assertEqual(job.result, {'datasets': {}, 'log': []})
        self.assertEqual(job.receipt['completeness']['n_statements'], 0)
        self.assertEqual(job.receipt['completeness']['n_tickets'], 0)
        self.assertEqual(job.receipt['completeness']['coverage'], 0.0)

    def test_hello_keeps_existing_literal_put_plan(self):
        plan = compile_plan((ROKU_CORPUS / 'hello_world_text.sas').read_text())
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].name, '_null_')
        self.assertEqual(len(plan.steps[0].operations), 1)
        self.assertEqual(plan.steps[0].operations[0].kind, 'put_literal')
        self.assertEqual(plan.steps[0].operations[0].args, {'literals': ['"Hello world!"']})

    def test_independent_scanner_keeps_comment_markers_inside_quotes(self):
        source = "/*outer;*/data _null_;put 'semi; /*literal*/ it''s';/*middle*/run;*tail;"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'original.sas'; path.write_text(source)
            independent, accounting = program_witness(path)
        result, stdout = emitted(source)
        self.assertEqual(independent, result)
        self.assertEqual(result['log'], ["semi; /*literal*/ it's"])
        self.assertEqual(stdout, "semi; /*literal*/ it's\n")
        self.assertEqual(accounting['statements'], 3)
        self.assertEqual(accounting['block_comments'], 2)
        self.assertEqual(accounting['statement_comments'], 1)

    def test_independent_scanner_handles_both_quote_pairs_and_crlf(self):
        source = '*head;\r\ndata _null_;put "a""b";put \'\';run;\r\n'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'original.sas'; path.write_bytes(source.encode())
            independent, accounting = program_witness(path)
        result, stdout = emitted(source)
        self.assertEqual(independent, result)
        self.assertEqual(result['log'], ['a"b', "'"])
        self.assertEqual(stdout, 'a"b\n\'\n')
        self.assertEqual(accounting['source_bytes'], len(source.encode()))
        self.assertEqual(accounting['statements'], 4)

    def test_independent_scanner_accounts_for_comment_only_variants(self):
        for source, blocks, statements in [('', 0, 0), ('  \n', 0, 0),
                                           ('/*a;*/ *b;\n*multi\nline;', 1, 2),
                                           ('%*macro;/*block*/', 1, 1)]:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / 'original.sas'; path.write_text(source)
                result, accounting = program_witness(path)
                self.assertEqual(result, {'datasets': {}, 'log': []})
                self.assertEqual(accounting['block_comments'], blocks)
                self.assertEqual(accounting['statement_comments'], statements)
                self.assertEqual(accounting['statements'], 0)
                self.assertEqual(emitted(source), (result, ''))

    def test_independent_witness_refuses_unconsumed_executable_tails(self):
        base = (ROKU_CORPUS / 'hello_world_text.sas').read_text()
        for tail in ('proc print;run;', 'data d;x=1;run;', "put 'outside';", 'unknown;'):
            with self.subTest(tail=tail), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / 'mutation.sas'; path.write_text(base + tail)
                with self.assertRaises(ValueError):
                    program_witness(path)

    def test_independent_witness_refuses_unterminated_lexical_tails(self):
        for tail in ('/*unclosed', '*unclosed', 'data _null_;put "unclosed;',
                     'data _null_;put \'record\';', 'data _null_;put \'record\';run'):
            with self.subTest(tail=tail), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / 'mutation.sas'; path.write_text(tail)
                with self.assertRaises(ValueError):
                    program_witness(path)

    def test_complete_sources_do_not_ignore_supported_appended_steps(self):
        for name in PINS:
            source = (ROKU_CORPUS / name).read_text() + "data _null_;put 'tail';run;"
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / 'mutation.sas'; path.write_text(source)
                independent, accounting = program_witness(path)
                result, stdout = emitted(source)
                self.assertEqual(independent, result)
                self.assertEqual(result['log'], PINS[name]['log'] + ['tail'])
                self.assertEqual(accounting['statements'], PINS[name]['accounting']['statements'] + 3)
                self.assertEqual(accounting['steps'], PINS[name]['accounting']['steps'] + 1)
                self.assertNotEqual(digest(result), PINS[name]['result'])
                self.assertNotEqual(hashlib.sha256(stdout.encode()).hexdigest(), PINS[name]['stdout'])
                self.assertNotEqual(hashlib.sha256(source.encode()).hexdigest(), PINS[name]['source'])

    def test_dataset_identity_cannot_supply_log_equivalence(self):
        original, stdout = emitted((ROKU_CORPUS / 'hello_world_text.sas').read_text())
        changed, altered = emitted("data _null_;put 'different';run;")
        self.assertEqual(original['datasets'], changed['datasets'])
        self.assertFalse(equal(original, changed))
        self.assertNotEqual(stdout, altered)
        for wrong in ([], ['Hello world?'], ['Hello world!', 'Hello world!']):
            candidate = {'datasets': {}, 'log': wrong}
            self.assertFalse(equal(original, candidate))
            self.assertNotEqual(digest(candidate), PINS['hello_world_text.sas']['result'])

    def test_exact_log_controls_cover_order_multiplicity_and_newlines(self):
        result, stdout = emitted("data _null_;put 'first';put 'second ';run;")
        self.assertEqual(result['log'], ['first', 'second '])
        self.assertEqual(stdout, 'first\nsecond \n')
        for wrong in (['second ', 'first'], ['first'], ['first', 'second ', 'second '],
                      ['first', 'second']):
            with self.subTest(wrong=wrong):
                self.assertFalse(equal(result, {'datasets': {}, 'log': wrong}))
        for wrong in ('first\nsecond ', 'first second \n', 'first\nsecond\n'):
            self.assertNotEqual(stdout, wrong)

    def test_failing_appended_source_publishes_no_partial_result(self):
        source = (ROKU_CORPUS / 'hello_world_text.sas').read_text() + 'proc print;run;'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'mutation.sas'; path.write_text(source)
            output = Path(temporary) / 'job'
            process = subprocess.run([sys.executable, '-m', 'saschi', 'run', str(path),
                                      '--output', str(output)], capture_output=True,
                                     text=True, timeout=30)
            self.assertEqual(process.returncode, 2)
            receipt = json.loads((output / 'receipt.json').read_text())
            self.assertFalse(receipt['accepted'])
            self.assertFalse((output / 'result.json').exists())
            self.assertFalse((output / 'observed.json').exists())
            self.assertNotIn('Hello world!', process.stdout)
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream), self.assertRaises(RuntimeError):
                exec(translate(source).code, {})
            self.assertEqual(stream.getvalue(), '')

    def test_runs_and_noop_plans_keep_no_cross_program_state(self):
        hello = compile_plan((ROKU_CORPUS / 'hello_world_text.sas').read_text()).to_dict()
        comments = compile_plan((ROKU_CORPUS / 'comments.sas').read_text()).to_dict()
        before = deepcopy((hello, comments))
        self.assertEqual(run_plan(hello), expected('hello_world_text.sas'))
        self.assertEqual(run_plan(comments), expected('comments.sas'))
        self.assertEqual(run_plan(hello), expected('hello_world_text.sas'))
        self.assertEqual((hello, comments), before)


if __name__ == '__main__':
    unittest.main()
