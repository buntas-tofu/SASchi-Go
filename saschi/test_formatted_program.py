"""Independent whole-family, explicit output selector and exact log guards.

Tests assert public outcomes and static refusal boundaries, not engine internals.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from examples.verify_formatted_input import source, original_expected, ORIGINAL, assert_exact
from . import formatted_input, formatted_program
from .bitwise_output import PROFILE as BITWISE_PROFILE
from .emit_py import translate
from .job import build_job
from .log_artifacts import read_expected_log
from .plan import compile_plan
from .runtime import run_plan

ROOT = Path(__file__).resolve().parents[1]
REPORT_SOURCE = "title 'Probe';proc print data=d label noobs;label raw='Original' value='Rating';run;proc means data=d;run;"


def program(records=('A        High  ',), reports=False):
    return source(list(records)) + (REPORT_SOURCE if reports else '')


def portable(records=('A        High  ',), reports=False):
    parsed = compile_plan(program(records, reports)); assert not parsed.blocked, parsed.tickets
    return parsed.to_dict()


class FormattedProgramTests(unittest.TestCase):
    def test_original_complete_input_program_uses_public_family(self):
        plan = compile_plan(ORIGINAL.read_text()); self.assertFalse(plan.blocked)
        self.assertEqual([step.kind for step in plan.steps], ['informat_definition', 'formatted_data'] * 2)
        assert_exact(run_plan(plan.to_dict()), original_expected())

    def test_real_definitions_and_producer_required_before_selection(self):
        for text in ("title 'Probe';", "proc format;invalue eval 'A'=1;run;", source([], definition=''),
                     'data d;x=1;run;' + REPORT_SOURCE):
            self.assertTrue(compile_plan(text).blocked, text)
        literal = compile_plan("data d;length text $32;text='proc format;invalue eval';run;")
        self.assertFalse(literal.blocked); self.assertEqual(literal.steps[0].kind, 'data')
        self.assertEqual(run_plan(literal.to_dict())['datasets']['d']['rows'][0]['text'].rstrip(' '), 'proc format;invalue eval')
        legacy = compile_plan("data _null_;put 'proc format; input eval.';run;")
        self.assertFalse(legacy.blocked)
        self.assertEqual(run_plan(legacy.to_dict())['log'], ['proc format; input eval.'])

    def test_reports_and_title_share_private_dataset_lineage(self):
        parsed = compile_plan(program(reports=True)); self.assertFalse(parsed.blocked, parsed.tickets)
        result = run_plan(parsed.to_dict())
        self.assertEqual(list(result['reports']), ['print_01.txt', 'means_01.txt'])
        self.assertTrue(all(text.startswith('TITLE: Probe\n') for text in result['reports'].values()))
        self.assertEqual(result['datasets']['d']['schema']['raw'], {'type': 'character', 'length': 6})
        self.assertNotIn('Rating', result['reports']['means_01.txt'])

    def test_definition_and_dataset_names_are_separate_namespaces(self):
        text = source(['A        High  '], name='usr_rating')
        result = run_plan(compile_plan(text).to_dict())
        self.assertEqual(result['datasets']['usr_rating']['rows'][0]['value'], 9.)

    def test_empty_producer_schema_and_reports_validate_statically(self):
        plan = portable([], reports=True); result = run_plan(plan)
        self.assertEqual(result['datasets']['d']['rows'], [])
        self.assertEqual(result['reports']['print_01.txt'], 'TITLE: Probe\n"id" "Original" "Rating"\n')
        self.assertIn('"value" 0 . . . .\n', result['reports']['means_01.txt'])
        bad = deepcopy(plan); bad['steps'][3]['operations'][0]['args']['labels'][0]['name'] = 'absent'
        with self.assertRaises(ValueError): run_plan(bad)

    def test_forward_definition_and_report_references_refuse_even_empty(self):
        baseline = portable([], reports=True)
        for indices in ((1, 0, 2, 3, 4), (0, 3, 1, 2, 4), (0, 4, 1, 2, 3)):
            plan = deepcopy(baseline); plan['steps'] = [plan['steps'][i] for i in indices]
            with self.assertRaises(ValueError): run_plan(plan)
        text = source([], definition='') + "proc format;invalue usr_rating 'Medium'=5;run;"
        self.assertTrue(compile_plan(text).blocked)

    def test_duplicate_definition_and_destination_never_overwrite(self):
        baseline = portable([])
        for index in (0, 1):
            plan = deepcopy(baseline); plan['steps'].append(deepcopy(plan['steps'][index]))
            with self.assertRaises(ValueError): run_plan(plan)
        for catalog in ({'d': {'schema': {}, 'rows': []}}, {'unused': {'schema': {}, 'rows': []}}, False, []):
            before = deepcopy(catalog)
            with self.assertRaises(ValueError): run_plan(baseline, catalog)
            self.assertEqual(catalog, before)

    def test_report_counts_apply_across_all_intervening_new_steps(self):
        baseline = portable([], reports=True)
        for index in (3, 4):
            plan = deepcopy(baseline); plan['steps'].append(deepcopy(plan['steps'][index]))
            with self.assertRaises(ValueError): run_plan(plan)
        self.assertTrue(compile_plan(program([], reports=True) + 'proc means data=d;run;').blocked)

    def test_title_producer_definition_and_total_resource_bounds(self):
        baseline = portable([], reports=True)
        title = deepcopy(baseline['steps'][2])
        accepted = deepcopy(baseline); accepted['steps'] = accepted['steps'][:2] + [deepcopy(title) for _ in range(32)]
        self.assertEqual(formatted_program.validate_program(accepted)['counts']['informat_title'], 32)
        for count in (33, 65):
            bad = deepcopy(accepted); bad['steps'] = bad['steps'][:2] + [deepcopy(title) for _ in range(count)]
            with self.assertRaises(ValueError): run_plan(bad)
        producers = deepcopy(baseline); producers['steps'] = producers['steps'][:1]
        for i in range(8):
            step = deepcopy(baseline['steps'][1]); step['name'] = 'd' + str(i); producers['steps'].append(step)
        self.assertEqual(len(run_plan(producers)['datasets']), 8)
        extra = deepcopy(producers['steps'][1]); extra['name'] = 'excess'; producers['steps'].append(extra)
        with self.assertRaises(ValueError): run_plan(producers)

    def test_whole_profile_exact_version_and_no_partial_mode(self):
        baseline = portable([])
        for version in (True, 2., 1, None, '2'):
            bad = deepcopy(baseline); bad['version'] = version
            with self.assertRaises((ValueError, TypeError)): run_plan(bad)
        bad = deepcopy(baseline); bad['tickets'] = [{'line': 1, 'reason': 'unsupported'}]
        with self.assertRaises(RuntimeError): run_plan(bad)
        with self.assertRaises(ValueError): run_plan(bad, allow_partial=True)

    def test_old_and_both_new_families_cannot_cross_forge(self):
        baseline = portable([])
        bitwise = compile_plan('data _null_;x=band(3,1);put _all_;run;', output_contract=BITWISE_PROFILE).to_dict()
        for old_kind in ('data', 'control_data', 'flow_data', 'character_data', 'proc_print', 'bitwise_data'):
            for index in (0, 1):
                bad = deepcopy(baseline); bad['steps'][index]['kind'] = old_kind
                with self.assertRaises(ValueError): run_plan(bad)
        for new_step in baseline['steps']:
            bad = deepcopy(bitwise); bad['steps'][0]['operations'].append(deepcopy(new_step['operations'][0]))
            with self.assertRaises(ValueError): run_plan(bad)
        for step in bitwise['steps']:
            bad = deepcopy(baseline); bad['steps'].append(step)
            with self.assertRaises(ValueError): run_plan(bad)

    def test_old_markers_and_unselected_hidden_new_shapes_refuse(self):
        old = compile_plan('data d;x=1;run;').to_dict()
        for marker in (formatted_input.DATA_PROFILE, formatted_input.DEFINITION_PROFILE,
                       'labelled-print-v1', 'default-means-v1', 'informat-title-v1', BITWISE_PROFILE):
            bad = deepcopy(old); bad['steps'][0]['operations'][0]['args']['hidden'] = {'profile': marker}
            with self.assertRaises(ValueError): run_plan(bad)
        for kind in ('formatted_data', 'numeric_invalue', 'labelled_print', 'put_all_67'):
            bad = deepcopy(old); bad['matched'] = [{'kind': kind}]
            with self.assertRaises(ValueError): run_plan(bad)

    def test_unselected_DAG_cycles_and_large_old_source_remain_bounded(self):
        dag = []
        for _ in range(12): dag = [dag, dag, dag]
        old = compile_plan('data d;x=1;run;').to_dict(); old['matched'] = dag
        self.assertEqual(run_plan(old)['datasets']['d']['rows'], [{'x': 1.}])
        cyclic = []; cyclic.append(cyclic); old['matched'] = cyclic
        with self.assertRaises(ValueError): run_plan(old)
        text = 'data _null_;' + ''.join(f'x={i};' for i in range(20001)) + 'run;'
        plan = compile_plan(text); self.assertFalse(plan.blocked)
        self.assertEqual(len(plan.steps[0].operations), 20001)
        self.assertEqual(run_plan(plan.to_dict())['log'], [])

    def test_explicit_output_contract_does_not_activate_default_or_formatted_paths(self):
        text = 'data _null_;x=band(3,1);put _all_;run;'
        old = compile_plan(text); new = compile_plan(text, output_contract=BITWISE_PROFILE)
        self.assertFalse(old.blocked); self.assertFalse(new.blocked)
        self.assertEqual(old.steps[0].kind, 'data'); self.assertEqual(new.steps[0].kind, 'bitwise_data')
        self.assertEqual(run_plan(old.to_dict()), run_plan(new.to_dict()))
        for selector in ('unknown', '', [], True, 1):
            self.assertTrue(compile_plan(text, output_contract=selector).blocked)
        self.assertTrue(compile_plan(program(), output_contract=BITWISE_PROFILE).blocked)
        self.assertEqual(translate(text).plan, old.to_dict())

    def test_log_reader_rejects_malformed_deep_nonascii_or_wrong_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'expected.json'
            bad = [b'{"a":1,"a":2}', b'[NaN]', b'true', b'{}', b'[1]', b'[null]',
                   b'["a\\n"]', b'["\\ud800"]', b'["\\u00e9"]', b'["a\\t"]', b'\xff',
                   b'[' * 10000 + b']' * 10000,
                   json.dumps(['x'] * 1001).encode(), json.dumps(['x' * 4097]).encode(), b' ' * 1048577]
            for raw in bad:
                path.write_bytes(raw)
                with self.subTest(size=len(raw)):
                    with self.assertRaises(ValueError): read_expected_log(path)
            raw = json.dumps(['', ' a ', 'x' * 4096]).encode(); path.write_bytes(raw)
            expected, checksum = read_expected_log(path)
            self.assertEqual(expected, ['', ' a ', 'x' * 4096]); self.assertEqual(checksum, hashlib.sha256(raw).hexdigest())

    def test_log_comparator_exact_order_multiplicity_padding_and_optin_receipt(self):
        text = "data _null_;put 'first';put 'second';run;"
        plain = build_job(text); self.assertTrue(plain.receipt['accepted'])
        self.assertNotIn('log_comparison', plain.receipt)
        with tempfile.TemporaryDirectory() as directory:
            expected = Path(directory) / 'log.json'
            for records, accepted in ((['first', 'second'], True), (['second', 'first'], False),
                                      (['first', 'second', 'second'], False), (['first'], False),
                                      (['first ', 'second'], False), (['first', 'Second'], False), ([], False)):
                expected.write_text(json.dumps(records)); job = build_job(text, expect_log=expected)
                self.assertEqual(job.receipt['accepted'], accepted)
                self.assertEqual(job.receipt['log_comparison'], 'passed' if accepted else 'failed')
                self.assertEqual(job.receipt['expected_log_sha256'], hashlib.sha256(expected.read_bytes()).hexdigest())

    def test_actual_CLI_log_pass_wrong_and_invalid_manifest_publish_no_success(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); src = folder / 'program.sas'; src.write_text("data _null_;put 'first';put 'second';run;")
            for index, (raw, accepted) in enumerate(((b'["first","second"]', True),
                    (b'["second","first"]', False), (b'["first","second "]', False),
                    (b'[' * 10000 + b']' * 10000, False))):
                expectation = folder / f'{index}.json'; expectation.write_bytes(raw); output = folder / f'job{index}'
                process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'run', str(src),
                    '--expect-log', str(expectation), '--output', str(output)], cwd=ROOT,
                    capture_output=True, text=True, timeout=45)
                receipt = json.loads((output / 'receipt.json').read_text())
                self.assertEqual(process.returncode, 0 if accepted else 1, (process.stdout, process.stderr, receipt))
                self.assertIs(receipt['accepted'], accepted)
                self.assertEqual((output / 'result.json').exists(), accepted)
                self.assertFalse((output / 'reports').exists()); self.assertFalse((output / 'exports').exists())

    def test_all_legacy_output_prefixes_execute_and_translate(self):
        import os
        aliases = ('--o', '--ou', '--out', '--outp', '--outpu', '--output')
        environment = {**os.environ, 'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'}
        with tempfile.TemporaryDirectory(prefix='output-prefix-compat-') as temporary:
            folder = Path(temporary)
            source = folder / 'owned.sas'
            source.write_text("data _null_;put 'prefix roundtrip';run;")
            emitted = []
            for index, alias in enumerate(aliases):
                with self.subTest(command='run', alias=alias):
                    output = folder / ('run' + str(index))
                    process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'run', str(source), alias, str(output)],
                        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=45)
                    self.assertEqual(process.returncode, 0, (process.stdout, process.stderr))
                    receipt = json.loads((output / 'receipt.json').read_text())
                    self.assertIs(receipt['accepted'], True)
                    self.assertNotIn('output_contract', receipt)
                    self.assertEqual(json.loads((output / 'result.json').read_text()),
                                     {'datasets': {}, 'log': ['prefix roundtrip']})
                with self.subTest(command='translate', alias=alias):
                    output = folder / ('translate' + str(index) + '.py')
                    process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'translate', str(source),
                        '--target', 'python', alias, str(output)], cwd=ROOT, env=environment,
                        capture_output=True, text=True, timeout=45)
                    self.assertEqual(process.returncode, 0, (process.stdout, process.stderr))
                    self.assertIs(json.loads(process.stdout)['blocked'], False)
                    emitted.append(output.read_bytes())
            self.assertTrue(all(code == emitted[0] for code in emitted))
            execution = subprocess.run([sys.executable, '-B', str(folder / 'translate0.py')],
                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=45)
            self.assertEqual(execution.returncode, 0, execution.stderr)
            self.assertEqual(execution.stdout, 'prefix roundtrip\n')

    def test_output_prefix_and_contract_selection_remain_separate(self):
        import os
        environment = {**os.environ, 'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'}
        # This original three-variable example is separate from the corpus source.
        long_name = 'abcdefghijklmnopqrstuvwxyzabcdef'
        text = 'data _null_;result=band(7,3);' + long_name + '=1;pad=31;put _all_;run;'
        record = 'result=3 ' + long_name + '=1 pad=31 _ERROR_=0 _N_=1 '
        self.assertEqual(len(record), 67)
        with tempfile.TemporaryDirectory(prefix='output-contract-compat-') as temporary:
            folder = Path(temporary)
            source = folder / 'owned.sas'; source.write_text(text)
            expected = folder / 'expected.json'; expected.write_text(json.dumps([record]))
            selected = folder / 'selected'
            process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'run', str(source),
                '--output-contract', BITWISE_PROFILE, '--expect-log', str(expected), '--out', str(selected)],
                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=45)
            self.assertEqual(process.returncode, 0, (process.stdout, process.stderr))
            receipt = json.loads((selected / 'receipt.json').read_text())
            self.assertIs(receipt['accepted'], True)
            self.assertEqual(receipt['output_contract'], BITWISE_PROFILE)
            self.assertEqual(receipt['log_comparison'], 'passed')
            self.assertEqual(json.loads((selected / 'result.json').read_text()), {'datasets': {}, 'log': [record]})
            default = folder / 'default'
            process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'run', str(source), '--out', str(default)],
                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=45)
            self.assertEqual(process.returncode, 1, (process.stdout, process.stderr))
            receipt = json.loads((default / 'receipt.json').read_text())
            self.assertIs(receipt['accepted'], False)
            self.assertNotIn('output_contract', receipt)
            self.assertIn('64', receipt['error'])
            self.assertFalse((default / 'result.json').exists())
            self.assertFalse((default / 'reports').exists())
            self.assertFalse((default / 'exports').exists())
            python_file = folder / 'selected.py'
            process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'translate', str(source),
                '--output-contract', BITWISE_PROFILE, '--outp', str(python_file)],
                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=45)
            self.assertEqual(process.returncode, 0, (process.stdout, process.stderr))
            execution = subprocess.run([sys.executable, '-B', str(python_file)], cwd=ROOT, env=environment,
                capture_output=True, text=True, timeout=45)
            self.assertEqual(execution.returncode, 0, execution.stderr)
            self.assertEqual(execution.stdout, record + '\n')
            cpp_file = folder / 'blocked.cpp'
            process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'translate', str(source),
                '--target', 'cpp', '--output-contract', BITWISE_PROFILE, '--out', str(cpp_file)],
                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=45)
            self.assertEqual(process.returncode, 2, (process.stdout, process.stderr))
            status = json.loads(process.stdout)
            self.assertIs(status['blocked'], True)
            self.assertTrue(any(item['construct'] == 'cpp-target' and item['statement'] == 'put_all_67'
                                for item in status['tickets']))
