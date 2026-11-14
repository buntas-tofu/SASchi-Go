"""Explicit uint32/67-column source,portable,whole-oracle and CLI boundaries."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import inspect
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import ast

from examples.verify_bitwise_output import (ORIGINAL, PROFILE, assert_exact, atomic_cli, cli_check,
    corpus_expected, corpus_path, default_refusal, execute, generated_cases, hand_cases,
    original_expected, refusal_cases, source, width_source, witnesses, wrong_logs)
from sas_semantics import sas_put_all
from . import bitwise_output
from .emit_cpp import translate as cpp_translate
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan

ROOT = Path(__file__).resolve().parents[1]


def portable():
    parsed = compile_plan(source('a=1;b=bnot(a);'), output_contract=PROFILE)
    if parsed.blocked: raise AssertionError(parsed.tickets)
    return parsed.to_dict()


class BitwiseOutputTests(unittest.TestCase):
    def test_original_complete_source_R_state_and_overwrite(self):
        witness = witnesses([ORIGINAL])[0]; self.assertIsNotNone(witness)
        actual, context = execute(ORIGINAL, emitted=True)
        assert_exact(actual, original_expected()); assert_exact(witness['result'], actual)
        assert_exact(context['events'], witness['events'])
        self.assertEqual(context['row'], {'seed': 2., 'mask': 6., 'bits': 11., 'shift': 16.})
        self.assertEqual(context['display_names'], {'seed': 'Seed', 'mask': 'mask', 'bits': 'Bits', 'shift': 'Shift'})
        self.assertEqual(witness['accounting'], dict(statements=8, assignments=5, bitwise_calls=3, width=47, variables=4))

    def test_whole_unchanged_corpus_and_both_contracts(self):
        path = corpus_path(); raw = path.read_bytes()
        self.assertEqual(len(raw), 469)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'e774418156723a8c2aa8f6a2e6b9fac9f6c258a87ee1aff13502b8a654584799')
        witness = witnesses([path])[0]; actual, context = execute(path, emitted=True)
        assert_exact(actual, corpus_expected()); assert_exact(actual, witness['result'])
        assert_exact(context['events'], witness['events'])
        self.assertEqual(witness['accounting'], dict(statements=11, assignments=8, bitwise_calls=6, width=67, variables=8))
        default_refusal(path); self.assertEqual(path.read_bytes(), raw)

    def test_hand_programs_independent_R_and_public_execution(self):
        cases = hand_cases(); independent = witnesses([item[1] for item in cases])
        for (name, text, truth), oracle in zip(cases, independent):
            with self.subTest(name=name):
                self.assertIsNotNone(oracle); assert_exact(oracle['result'], truth)
                assert_exact(execute(text, emitted=True)[0], truth)

    def test_constructive_generated_sources(self):
        cases = generated_cases(36); independent = witnesses([case[0] for case in cases])
        for (text, truth), oracle in zip(cases, independent):
            self.assertIsNotNone(oracle); assert_exact(oracle['result'], truth)
            assert_exact(execute(text)[0], truth)

    def test_shared_source_refusals_and_static_domains(self):
        cases = refusal_cases(); independent = witnesses([case[1] for case in cases])
        for (name, text), oracle in zip(cases, independent):
            with self.subTest(name=name):
                self.assertTrue(compile_plan(text, output_contract=PROFILE).blocked)
                self.assertIsNone(oracle)

    def test_width64_65_66_67_and68_keeps_old_cap(self):
        for width in (64, 65, 66, 67):
            text, truth = width_source(width)
            result = execute(text, emitted=True)[0]
            assert_exact(result, truth); self.assertEqual(len(result['log'][0]), width)
            old = build_job(text)
            self.assertEqual(old.code, 0 if width == 64 else 1)
            if width > 64: self.assertIn('beyond 64 columns', old.receipt['error'])
        self.assertTrue(compile_plan(width_source(68)[0], output_contract=PROFILE).blocked)

    def test_new_execution_does_not_mutate_plan_catalog_or_trace(self):
        plan = portable(); saved = deepcopy(plan); supplied = {}; trace = []
        result = bitwise_output.execute_step(plan['steps'][0], supplied, trace=trace)
        self.assertEqual(plan, saved); self.assertEqual(supplied, {})
        self.assertEqual(result, run_plan(plan)); self.assertEqual(trace[-1]['fields'][0]['name'], 'a')
        trace[-1]['fields'][0]['value'] = 99
        self.assertEqual(bitwise_output.execute_step(plan['steps'][0])['log'], result['log'])
        with self.assertRaises(ValueError): bitwise_output.execute_step(plan['steps'][0], trace={})

    def test_direct_and_public_require_empty_catalog(self):
        plan = portable()
        for catalog in ({'unused': {'schema': {'x': 'number'}, 'rows': [{'x': 1.}]}}, [], True):
            saved = deepcopy(catalog)
            with self.assertRaises(ValueError): bitwise_output.execute_step(plan['steps'][0], catalog)
            with self.assertRaises(ValueError): run_plan(plan, catalog)
            self.assertEqual(catalog, saved)

    def test_exact_step_defaults_and_unknown_fields(self):
        base = portable()['steps'][0]
        for mutate in (lambda s: s.update(extra='ignored'), lambda s: s.update(name='d'),
                       lambda s: s.update(kind='data'), lambda s: s.update(inputs=['raw']), lambda s: s.update(by=['a']),
                       lambda s: s.update(nodupkey=0), lambda s: s.update(where={}),
                       lambda s: s.update(retained={'a': 1}), lambda s: s.update(lengths={'a': 8})):
            step = deepcopy(base); mutate(step)
            with self.assertRaises(ValueError): bitwise_output.validate_step(step)

    def test_version_and_source_line_types(self):
        base = portable()['steps'][0]
        for version in (1, True, 2., '2', None):
            with self.assertRaises(ValueError): bitwise_output.validate_step(base, version)
        for bad in (True, 1., 0, '1', None):
            step = deepcopy(base); step['line'] = bad
            with self.assertRaises(ValueError): bitwise_output.validate_step(step)
            step = deepcopy(base); step['operations'][0]['line'] = bad
            with self.assertRaises(ValueError): bitwise_output.validate_step(step)
        step = deepcopy(base); step['operations'][-1]['line'] = 1
        with self.assertRaises(ValueError): bitwise_output.validate_step(step)

    def test_final_operation_and_marker_are_exact(self):
        base = portable()['steps'][0]
        for mutate in (lambda o: o.update(kind='put_all'), lambda o: o.update(extra=True),
                       lambda o: o.update(args={}), lambda o: o['args'].update(width=67),
                       lambda o: o['args'].update(profile='old64'), lambda o: o['args'].update(profile=[])):
            step = deepcopy(base); mutate(step['operations'][-1])
            with self.assertRaises(ValueError): bitwise_output.validate_step(step)
        for operations in ([], [base['operations'][-1]], base['operations'] + [base['operations'][-1]]):
            step = deepcopy(base); step['operations'] = deepcopy(operations)
            with self.assertRaises(ValueError): bitwise_output.validate_step(step)

    def test_display_name_order_spelling_and_namespace(self):
        base = portable()['steps'][0]
        for shown in ({}, {'b': 'b', 'a': 'a'}, {'a': 'unrelated', 'b': 'b'},
                      {'a': 'a', 'b': 'b', '_all_': '_all_'}, {'a': 'K', 'b': 'b'}):
            step = deepcopy(base); step['display_names'] = shown
            with self.assertRaises(ValueError): bitwise_output.validate_step(step)
        text = source('Band=13;Result=band(Band,3);Band=bnot(4294967295);')
        self.assertEqual(execute(text)[0]['log'], ['Band=0 Result=1 ' + bitwise_output.TAIL])

    def test_nonmissing_uint32_portable_values_never_coerce(self):
        base = portable()['steps'][0]
        for value in (None, True, False, '1', {'missing': 'A'}, -1, .5, 4294967296, 10**400,
                      float('nan'), float('inf'), float('-inf')):
            step = deepcopy(base); step['operations'][0]['args']['value']['value'] = value
            with self.assertRaises(ValueError): bitwise_output.validate_step(step)

    def test_literal_text_exactness_before_float_parsing(self):
        for literal in ('1.000000000000000000000001', '1e-999', '0e33', '0' * 33, '4294967295.0000001'):
            self.assertTrue(compile_plan(source('a=' + literal + ';b=bnot(a);'), output_contract=PROFILE).blocked)
        self.assertEqual(execute(source('a=-0.0;b=band(a,1.000);'))[0]['log'], ['a=0 b=0 ' + bitwise_output.TAIL])

    def test_expression_kinds_keys_call_names_and_arity(self):
        base = portable()['steps'][0]
        malformed = [
            {'kind': 'missing', 'value': None}, {'kind': 'automatic', 'value': '_n_'},
            {'kind': 'character', 'value': '1'}, {'kind': 'arithmetic', 'op': '+', 'left': {'kind': 'number', 'value': 1}, 'right': {'kind': 'number', 'value': 0}},
            {'kind': 'number', 'value': 1, 'extra': 0}, {'kind': []},
            {'kind': 'call', 'name': [], 'args': []}, {'kind': 'call', 'name': 'round', 'args': []},
            {'kind': 'call', 'name': 'bnot', 'args': []}, {'kind': 'call', 'name': 'bnot', 'args': ()},
            {'kind': 'call', 'name': 'bnot', 'args': [{'kind': 'number', 'value': 0}], 'extra': 0}]
        for expression in malformed:
            step = deepcopy(base); step['operations'][0]['args']['value'] = expression
            with self.assertRaises(ValueError): bitwise_output.validate_step(step)

    def test_prior_binding_required_and_names_are_ascii(self):
        base = portable()['steps'][0]
        for name in ('later', '_error_', 'A', 'K', [], None):
            step = deepcopy(base); step['operations'][0]['args']['value'] = {'kind': 'variable', 'value': name}
            with self.assertRaises(ValueError): bitwise_output.validate_step(step)
        for name in ('_n_', '_error_', '_temporary_', 'K', 'a' * 33):
            self.assertTrue(compile_plan(source(name + '=1;b=bnot(0);'), output_contract=PROFILE).blocked)

    def test64_assignments_allowed65_refused(self):
        positive = source('a=0;' * 63 + 'a=bnot(0);')
        self.assertEqual(execute(positive)[1]['assignments'], 64)
        self.assertTrue(compile_plan(source('a=0;' * 64 + 'a=bnot(0);'), output_contract=PROFILE).blocked)
        plan = portable(); plan['steps'][0]['operations'] = [deepcopy(plan['steps'][0]['operations'][0])] * 65 + [plan['steps'][0]['operations'][-1]]
        with self.assertRaises(ValueError): run_plan(plan)

    def test_call_depth32_and33_and_total_nodes128(self):
        self.assertEqual(execute(source('a=' + 'bnot(' * 32 + '0' + ')' * 32 + ';'))[1]['bitwise_calls'], 32)
        self.assertTrue(compile_plan(source('a=' + 'bnot(' * 33 + '0' + ')' * 33 + ';'), output_contract=PROFILE).blocked)
        def tree(depth): return '0' if depth == 0 else 'band(' + tree(depth-1) + ',' + tree(depth-1) + ')'
        positive = source('a=0;b=' + tree(6) + ';')
        self.assertEqual(execute(positive)[1]['bitwise_calls'], 63)
        self.assertTrue(compile_plan(source('a=0;b=' + tree(6) + ';c=0;'), output_contract=PROFILE).blocked)

    def test_large_variable_limit_and_one_whole_step(self):
        text = source(''.join('v' + str(i) + '=0;' for i in range(17)) + 'v0=bnot(0);')
        self.assertTrue(compile_plan(text, output_contract=PROFILE).blocked)
        plan = portable(); plan['steps'].append(deepcopy(plan['steps'][0]))
        with self.assertRaises(ValueError): run_plan(plan)
        for extra in ('data d;x=1;run;', 'proc print data=d;run;', 'title "text";'):
            self.assertTrue(compile_plan(source('a=bnot(0);') + extra, output_contract=PROFILE).blocked)

    def test_false_nested_new_operation_cannot_enter_old_plan(self):
        old = compile_plan('data d;if 0 then x=1;run;').to_dict()
        old['steps'][0]['operations'][0]['args']['operation'] = deepcopy(portable()['steps'][0]['operations'][-1])
        with self.assertRaises(ValueError): run_plan(old)
        for value in ({'profile': PROFILE}, {'kind': bitwise_output.KIND}, {'kind': bitwise_output.OPERATION}):
            with self.assertRaises(ValueError): bitwise_output.refuse_legacy(value)

    def test_cycles_shared_DAG_and_20001_old_operations(self):
        graph = []
        for _ in range(12): graph = [graph, graph]
        lines, start = inspect.getsourcelines(bitwise_output.refuse_legacy)
        pop_line = start + next(i for i, line in enumerate(lines) if 'item, leaving = pending.pop()' in line)
        count = 0
        def trace(frame, event, argument):
            nonlocal count
            if frame.f_code is bitwise_output.refuse_legacy.__code__ and event == 'line' and frame.f_lineno == pop_line:
                count += 1; self.assertLessEqual(count, 128)
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace); bitwise_output.refuse_legacy(graph); self.assertLessEqual(count, 39)
        finally: sys.settrace(previous)
        cycle = [graph]; cycle.append(cycle)
        with self.assertRaises(ValueError): bitwise_output.refuse_legacy(cycle)
        with self.assertRaises(ValueError): bitwise_output.refuse_legacy([{'profile': PROFILE}, graph])
        old = compile_plan('data d;x=1;run;').to_dict(); old['steps'][0]['operations'] *= 20001
        self.assertEqual(run_plan(old)['datasets']['d']['rows'], [{'x': 1.}])

    def test_cyclic_expression_refuses_without_recursionerror(self):
        plan = portable(); value = {'kind': 'call', 'name': 'bnot', 'args': []}; value['args'].append(value)
        plan['steps'][0]['operations'][0]['args']['value'] = value
        with self.assertRaises(ValueError): run_plan(plan)

    def test_default_API_shapes_and_explicit_none_unchanged(self):
        text = ORIGINAL.read_text()
        self.assertEqual(compile_plan(text).to_dict(), compile_plan(text, output_contract=None).to_dict())
        self.assertEqual(translate(text).code, translate(text, output_contract=None).code)
        default = build_job(text); opted = build_job(text, output_contract=PROFILE)
        assert_exact(default.result, opted.result)
        self.assertNotIn('output_contract', default.receipt); self.assertNotIn('log_comparison', default.receipt)
        self.assertEqual(opted.receipt['output_contract'], PROFILE)
        old = compile_plan(corpus_path().read_text()).to_dict(); old['output_contract'] = PROFILE
        with self.assertRaisesRegex(ValueError, 'beyond 64 columns'): run_plan(old)

    def test_unknown_contract_and_CPP_refuse(self):
        text = ORIGINAL.read_text()
        self.assertTrue(compile_plan(text, output_contract='unknown').blocked)
        translation = cpp_translate(text, output_contract=PROFILE); self.assertTrue(translation.blocked)
        job = build_job(text, None, None, 'cpp', output_contract=PROFILE)
        self.assertEqual(job.code, 2); self.assertIsNone(job.result)

    def test_actual_CLI_correct_and_eight_wrong_log_controls(self):
        self.assertTrue(cli_check(corpus_path(), corpus_expected()))
        for name, wrong in wrong_logs():
            with self.subTest(name=name): self.assertTrue(cli_check(corpus_path(), corpus_expected(), wrong, True))

    def test_CLI_translation_explicit_and_default_runtime_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); output = folder / 'program.py'
            process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'translate', str(corpus_path()),
                                      '--output-contract', PROFILE, '--output', str(output)], cwd=ROOT, capture_output=True, text=True, timeout=45)
            self.assertEqual(process.returncode, 0, (process.stdout, process.stderr))
            namespace = {}; import contextlib
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream): exec(output.read_text(), namespace)
            assert_exact(namespace['result'], corpus_expected()); self.assertEqual(stream.getvalue(), corpus_expected()['log'][0] + '\n')
            failed = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'run', str(corpus_path()), '--output', str(folder/'old')],
                                    cwd=ROOT, capture_output=True, text=True, timeout=45)
            receipt = json.loads((folder/'old/receipt.json').read_text())
            self.assertEqual(failed.returncode, 1); self.assertFalse(receipt['accepted']); self.assertNotIn('output_contract', receipt)
            self.assertFalse((folder/'old/result.json').exists())

    def test_atomic_invalid_width_and_late_invalid_call(self):
        self.assertEqual(atomic_cli(), 2)

    def test_old_helper_remains_exact(self):
        raw = (ROOT/'sas_semantics.py').read_bytes()
        # The approved wave appends helpers; every byte of the prior reference stays pinned.
        legacy=raw[:103888]
        self.assertEqual(hashlib.sha256(legacy).hexdigest(), '5b1fc6fe484fac23fd9e8df5e43b6eff8365d73555151f2fff4e19232cc196ef')
        old_nodes=[n for n in ast.walk(ast.parse(legacy)) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
        self.assertEqual(len(old_nodes),151);self.assertEqual(len({n.name for n in old_nodes}),149)
        self.assertEqual(hashlib.sha256(raw[:115862]).hexdigest(), 'a01eb9f0e8baf9aab1588d6cdf0b6fcdafc637898b4fac1a8c684536c0d047ce')
        self.assertEqual(hashlib.sha256(raw[:116869]).hexdigest(), 'ac1105744bd11bcca1aca4a06893385e073cf8c71398ef7efaaf58342197328a')
        self.assertEqual(hashlib.sha256(raw[:117909]).hexdigest(), 'd1053c25efffa8fc1bbcc80d678b268c8f60d8d4f746ed6f6911ff6ed2b22588')
        self.assertEqual(hashlib.sha256(raw[:120700]).hexdigest(), '4bf65830aba443f2b7acfb7e40e15ff637762b369178f8ef5c736427954fb4e5')
        self.assertEqual(hashlib.sha256(raw[:124820]).hexdigest(), '6b1420350ec579714fb835fd2e1e69c2e1931864f0191be4e6a70da7599f716a')
        self.assertEqual(hashlib.sha256(raw[:126109]).hexdigest(), '19c30cc847d216682ec16ff37396ae05c244cdfe36b52b1501c3418ea06affdd')
        self.assertEqual(hashlib.sha256(raw[:128210]).hexdigest(), '008cb515ac6fcdfcac82e8af994517c96d6e82c7c75debf765080546fab6cbe5')
        self.assertEqual(hashlib.sha256(raw[:128823]).hexdigest(), '9d12bf3f4037478a7b1c7e51369dfa50d8cefc9c927ab7ef8c37ecbf95f0beaa')
        self.assertEqual(hashlib.sha256(raw[:131455]).hexdigest(), 'cf0f881751c3bb3c85c363f5d68eebc4b0d489a9367ed4bf61717cd240f33847')
        self.assertEqual(hashlib.sha256(raw[:133525]).hexdigest(), '017867893c6670211867fa3729f913732b2f021279472bf165e78e859ad5e46f')
        self.assertEqual(hashlib.sha256(raw[:136500]).hexdigest(), '0777d918fdb8671a42fc3cd096c65031e5851ff80dc6c596b02229f065118815')
        self.assertEqual(hashlib.sha256(raw[:137630]).hexdigest(), '1acf938a0bcdf144a7ca616814c7d5edb4000f41b64e603a15a4b76a9a00b0bf')
        self.assertEqual(hashlib.sha256(raw[:139711]).hexdigest(), '078d427219b8c1a78928a5b63919972a22da42f53c694cf40a231857035ffedd')
        self.assertEqual(hashlib.sha256(raw[:141396]).hexdigest(), '5b1fba802eb26f8281795bdce39a80ee47b4fd701627e1e2e74ea3133ecd14c0')
        prior_reference = raw[:141396]
        self.assertEqual(hashlib.sha256(prior_reference).hexdigest(), '5b1fba802eb26f8281795bdce39a80ee47b4fd701627e1e2e74ea3133ecd14c0')
        nodes = [n for n in ast.walk(ast.parse(prior_reference)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        self.assertEqual(len(nodes), 261); self.assertEqual(len({n.name for n in nodes}), 259)
        with self.assertRaisesRegex(ValueError, 'beyond 64 columns'):
            sas_put_all([{'name': 'x', 'kind': 'character', 'value': 'q'*46}])


if __name__ == '__main__':
    unittest.main()
