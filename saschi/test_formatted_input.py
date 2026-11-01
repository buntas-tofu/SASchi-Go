"""DS-071/072 portable boundaries, independent source witnesses and old guards."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import inspect
import json
import sys
import unittest

from examples.verify_formatted_input import (ORIGINAL, SOURCE_PIN, RESULT_PIN, assert_exact,
    atomic_cli, batch_witness, cli_check, definition_cases, direct, execute, generated_cases,
    hand_cases, original_accounting, original_expected, original_trace, refusal_cases, source, wrong_cases)
from . import formatted_input as module
from .parser import split_statements
from .plan import compile_plan
from .runtime import run_plan
from .emit_cpp import translate as translate_cpp


def portable(records=(), fields='id $ @10 raw $6. @10 value usr_rating.'):
    context = direct(source(list(records), fields))
    return asdict(context['steps'][-1]), context['registry']


class FormattedInputTests(unittest.TestCase):
    def test_original_full_source_hand_R_public_runtime_emitted(self):
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(), SOURCE_PIN)
        self.assertEqual(hashlib.sha256(json.dumps(original_expected(), separators=(',', ':')).encode()).hexdigest(), RESULT_PIN)
        observed = batch_witness([ORIGINAL.read_text()])[0]
        self.assertIsNotNone(observed); assert_exact(observed['result'], original_expected())
        self.assertEqual(observed['accounting'], original_accounting())
        assert_exact(execute(ORIGINAL.read_text(), emitted=True), original_expected())
        assert_exact(observed['trace'], original_trace())
        assert_exact(direct(ORIGINAL.read_text())['trace'], original_trace())

    def test_all_handpins_and_independent_R(self):
        cases = hand_cases('invalue'); observed = batch_witness([case[1] for case in cases])
        for (name, text, truth), witness in zip(cases, observed):
            with self.subTest(name=name):
                self.assertIsNotNone(witness); assert_exact(witness['result'], truth)
                assert_exact(direct(text)['result'], truth)
                assert_exact(execute(text, emitted=True), truth)

    def test_generated_complete_record_schedules(self):
        cases = generated_cases(43); observed = batch_witness([case[0] for case in cases])
        for (text, truth), witness in zip(cases, observed):
            self.assertIsNotNone(witness); assert_exact(witness['result'], truth)
            assert_exact(execute(text), truth)

    def test_shared_refusals_empty_static_and_late_records(self):
        cases = refusal_cases(); observed = batch_witness([case[1] for case in cases])
        for (name, text), witness in zip(cases, observed):
            with self.subTest(name=name):
                self.assertIsNone(witness); self.assertTrue(compile_plan(text).blocked)
                with self.assertRaises(ValueError): direct(text)

    def test_definition_handpins_and_quoted_adjacency(self):
        cases = definition_cases(); observed = batch_witness([case[1] for case in cases], definitions=True)
        for (name, text, truth), witness in zip(cases, observed):
            self.assertIsNotNone(witness, name); assert_exact(witness['registry'], truth)
        text = "proc format;invalue eval'A'=1'B'=2;run;\ndata d;input id $ @3 n eval.;datalines;\nx A\n;\nrun;\n"
        witness = batch_witness([text])[0]; self.assertIsNotNone(witness)
        assert_exact(witness['result'], direct(text)['result'])

    def test_definition_derived_width_and_job_local_private_registry(self):
        context = direct(source(['A        Medium']))
        definition = asdict(context['steps'][0]); saved = deepcopy(definition)
        result = module.validate_definition_step(definition)
        self.assertEqual(result['width'], 6)
        self.assertEqual(list(result['mapping']), ['High', 'Low', 'Medium'])
        result['mapping']['High'] = 0; result['entries'][0]['value'] = 0
        self.assertEqual(definition, saved)
        self.assertEqual(module.validate_definition_step(definition)['mapping']['High'], 9)
        step = asdict(context['steps'][1])
        with self.assertRaises(ValueError): module.validate_data_step(step, {})

    def test_strict_literal_types_names_and_31_byte_boundary(self):
        original = asdict(direct(source([]))['steps'][0])
        for name in ('eval', 'usr_', 'usr_' + 'x' * 27):
            step = deepcopy(original); step['name'] = name
            self.assertEqual(module.validate_definition_step(step)['name'], name)
        for name in ('date', 'usr_x2', 'usr_' + 'x' * 28, 'USR_x', 'usr_K', '_error_', [], None):
            step = deepcopy(original); step['name'] = name
            with self.assertRaises(ValueError): module.validate_definition_step(step)
        for raw in ('', ' ', ' A', 'A ', 'A' * 33, 'é', 'a\t', 'A&B', '%x', "a'b", 'a"b'):
            step = deepcopy(original); step['operations'][0]['args']['entries'][0]['raw'] = raw
            with self.assertRaises(ValueError): module.validate_definition_step(step)
        for value in (True, 1., '1', None, [], 1001, -1001):
            step = deepcopy(original); step['operations'][0]['args']['entries'][0]['value'] = value
            with self.assertRaises(ValueError): module.validate_definition_step(step)

    def test_definition_entry_count_duplicate_and_exact_shape(self):
        original = asdict(direct(source([]))['steps'][0])
        entries = [{'raw': f'K{i}', 'value': i} for i in range(32)]
        step = deepcopy(original); step['operations'][0]['args']['entries'] = entries
        self.assertEqual(len(module.validate_definition_step(step)['mapping']), 32)
        for bad in ([], entries + [{'raw': 'Extra', 'value': 0}], [{'raw': 'X', 'value': 1}] * 2,
                    [{'raw': 'X', 'value': 1, 'extra': True}], {'X': 1}, [None]):
            step = deepcopy(original); step['operations'][0]['args']['entries'] = bad
            with self.assertRaises(ValueError): module.validate_definition_step(step)

    def test_registry_forged_derived_state_and_caller_nonmutation(self):
        step, registry = portable(['A        High  ']); saved = deepcopy((step, registry))
        for change in (lambda c: c.update(width=5), lambda c: c.update(width=True),
                       lambda c: c.update(name='eval'), lambda c: c.update(extra='ignored'),
                       lambda c: c['mapping'].update(High=True),
                       lambda c: c['entries'][0].update(value=8),
                       lambda c: c.update(source_lines=[True, 3])):
            bad = deepcopy(registry); change(bad['usr_rating'])
            with self.assertRaises(ValueError): module.validate_data_step(step, bad)
        context = module.validate_data_step(step, registry); context['schema']['id']['length'] = 1
        table, _ = module.execute_data(step, registry); table['rows'][0]['raw'] = 'changed'
        self.assertEqual((step, registry), saved)

    def test_first_character_period_refusal_distinct_fixed_period_missing(self):
        text = source(['A        .     High  '], 'id $ @10 raw $6. @16 value usr_rating.')
        rows = direct(text)['result']['datasets']['d']['rows']
        self.assertEqual(rows, [{'id': 'A       ', 'raw': '      ', 'value': 9.}])
        self.assertIsNotNone(batch_witness([text])[0])
        with self.assertRaises(ValueError): direct(source(['.        High  ']))

    def test_no_just_no_upcase_and_right_padding_only(self):
        for raw in ('high  ', ' High ', 'LOW   '):
            with self.assertRaises(ValueError): direct(source(['A        ' + raw]))
        self.assertEqual(direct(source(['A        High  ']))['result']['datasets']['d']['rows'][0]['value'], 9.)
        self.assertEqual(direct(source(['A          7   ']))['result']['datasets']['d']['rows'][0]['value'], 7.)

    def test_exact_integer_numeric_fallback_and_refused_missing(self):
        accepted = ('+1', '-0', '1000', '-1000', '.1e1', '1.000', '001e0', '0e-15')
        for token in accepted:
            text = source(['A        ' + token.ljust(6)])
            assert_exact(batch_witness([text])[0]['result'], direct(text)['result'])
        for token in ('.', '.A', '', '0.1', '5e-1', '1e-16', '1001', 'NaN', '1_0'):
            with self.assertRaises(ValueError): direct(source(['A        ' + token.ljust(6)]))

    def test_complete_fixed_spans_no_flowover_truncation_or_padding(self):
        for records in (['A        High ', 'B        Medium'], ['A', 'High  '], ['']):
            with self.assertRaises(ValueError): direct(source(records))
        text = source(['A        Medium ignored'])
        self.assertEqual(direct(text)['result']['datasets']['d']['rows'][0]['raw'], 'Medium')

    def test_source_line_provenance_multiline_comments_and_crlf(self):
        text = '/* context */\n' + source(['A        High  ']).replace('input id', 'input\n ID')
        one = direct(text); two = direct(text.replace('\n', '\r\n'))
        self.assertEqual([asdict(s) for s in one['steps']], [asdict(s) for s in two['steps']])
        lines = asdict(one['steps'][-1])['operations'][0]['args']['source_lines']
        self.assertEqual(lines, [5, 6, 8, 10, 11])
        self.assertEqual(batch_witness([text])[0]['accounting']['statements'], 7)

    def test_empty_input_static_fields_names_and_forward_references(self):
        for fields in ('id $ @10 raw $0. @10 value usr_rating.', 'id $ @10 ID $6. @10 value usr_rating.',
                       'id $ @10 value usr_missing.', 'id $ @10 raw $6.', 'id $ @80 value usr_rating.'):
            with self.assertRaises(ValueError): direct(source([], fields))
        text = source([], definition='') + "proc format;invalue usr_rating 'Medium'=5;run;\n"
        with self.assertRaises(ValueError): direct(text)
        self.assertIsNone(batch_witness([text])[0])

    def test_source_complete_terminators_and_opaque_boundaries(self):
        for text in (source([]).replace('run;', 'run', 1), source([]).replace('datalines;', 'datalines; junk'),
                     source([]).replace('\n;\n', '\n ;\n'), source([]).replace('\n;\n', '\n; \n')):
            with self.assertRaises(ValueError): direct(text)
            self.assertIsNone(batch_witness([text])[0])
        for record in ('A        Hi;gh ', 'A        "High"', 'A        K     ', 'A        Hi\tgh '):
            with self.assertRaises(ValueError): direct(source([record]))

    def test_portable_exact_defaults_operations_profile_and_version(self):
        baseline, registry = portable([])
        for change in (lambda s: s.update(extra=0), lambda s: s.update(inputs=['raw']),
                       lambda s: s.update(nodupkey=0), lambda s: s.update(where={}),
                       lambda s: s.update(lengths={'id': 8}), lambda s: s.update(retained={'id': ''}),
                       lambda s: s.update(display_names={'id': 'ID'}),
                       lambda s: s['operations'][0].update(extra=0),
                       lambda s: s['operations'][0]['args'].update(width=6),
                       lambda s: s['operations'][0]['args'].update(profile='character-records-v1')):
            step = deepcopy(baseline); change(step)
            with self.assertRaises(ValueError): module.validate_data_step(step, registry)
        for version in (1, True, 2., '2', None):
            with self.assertRaises(ValueError): module.validate_data_step(baseline, registry, version)

    def test_forged_field_shapes_on_empty_data(self):
        baseline, registry = portable([])
        for change in (lambda f: f[0].update(width=8), lambda f: f[0].update(read='character'),
                       lambda f: f[1].update(column=True), lambda f: f[1].update(column=0),
                       lambda f: f[1].update(width=True), lambda f: f[1].update(width=33),
                       lambda f: f[1].update(name='ID'), lambda f: f[1].update(name='K'),
                       lambda f: f[2].update(informat='date'), lambda f: f[2].update(width=6),
                       lambda f: f.append(deepcopy(f[2]))):
            step = deepcopy(baseline); change(step['operations'][0]['args']['fields'])
            with self.assertRaises(ValueError): module.validate_data_step(step, registry)

    def test_forged_physical_lines_counts_and_raw_value_types(self):
        baseline, registry = portable([])
        for index in range(5):
            step = deepcopy(baseline); step['operations'][0]['args']['source_lines'][index] = True
            with self.assertRaises(ValueError): module.validate_data_step(step, registry)
        for bad in ([1, 2, 3, 4, 4], [4, 5, 6, 8, 9], [], None):
            step = deepcopy(baseline); step['operations'][0]['args']['source_lines'] = bad
            with self.assertRaises(ValueError): module.validate_data_step(step, registry)
        for record in (True, None, {}, 'A        High ', 'A        high  ', 'A        .     '):
            step = deepcopy(baseline); args = step['operations'][0]['args']; args['records'] = [record]
            args['source_lines'][3:] = [args['source_lines'][2] + 2, args['source_lines'][2] + 3]
            with self.assertRaises(ValueError): module.validate_data_step(step, registry)

    def test_maximum_fields_records_columns_and_empty_descriptor_shape(self):
        fields = 'id $ ' + ' '.join(f'@10 c{i} $1.' for i in range(30)) + ' @10 value usr_rating.'
        table = direct(source([], fields))['result']['datasets']['d']
        self.assertEqual(len(table['schema']), 32); self.assertEqual(table['rows'], [])
        text = source([], fields)
        assert_exact(batch_witness([text])[0]['result'], direct(text)['result'])
        assert_exact(execute(text), direct(text)['result'])
        with self.assertRaises(ValueError): direct(source([], fields + ' @10 excess $1.'))
        maximum = source(['A        High  '] * 1000)
        self.assertEqual(len(direct(maximum)['result']['datasets']['d']['rows']), 1000)
        assert_exact(batch_witness([maximum])[0]['result'], execute(maximum))
        with self.assertRaises(ValueError): direct(source(['A        High  '] * 1001))
        self.assertEqual(len(direct(source(['A        High  ' + ' ' * 65]))['result']['datasets']['d']['rows']), 1)
        with self.assertRaises(ValueError): direct(source(['A        High  ' + ' ' * 66]))

    def test_program_registry_definition_producer_and_freshness_limits(self):
        definitions = ''.join(f"proc format;invalue usr_d{chr(97+i)} 'Medium'=5;run;" for i in range(8))
        text = source([], definition=definitions, fields='id $ @10 value usr_da.')
        self.assertEqual(len(direct(text)['registry']), 8)
        with self.assertRaises(ValueError): direct(text.replace('data d;', "proc format;invalue usr_extra 'Medium'=5;run;data d;"))
        with self.assertRaises(ValueError): direct(source([]) + source([], name='other'))
        with self.assertRaises(ValueError): direct(source([]) + source([], definition=''))
        step, registry = portable([])
        for catalog in ({'d': {'schema': {}, 'rows': []}}, {'D': {'schema': {}, 'rows': []}}):
            saved = deepcopy(catalog)
            with self.assertRaises(ValueError): module.execute_data(step, registry, catalog)
            self.assertEqual(catalog, saved)

    def test_completed_DAG_hidden_nodes_cycles_and_large_legacy(self):
        dag = []
        for _ in range(12): dag = [dag, dag, dag]
        pops = 0; target = module.refuse_legacy.__code__
        def tracer(frame, event, arg):
            nonlocal pops
            if frame.f_code is target and event == 'line': pops += 1
            return tracer
        sys.settrace(tracer)
        try: module.refuse_legacy(dag)
        finally: sys.settrace(None)
        self.assertLess(pops, 2000)
        for hidden in ({'kind': module.DATA_KIND}, {'profile': module.DEFINITION_PROFILE}):
            with self.assertRaises(ValueError): module.refuse_legacy([dag, hidden])
        cycle = []; cycle.append(cycle)
        with self.assertRaises(ValueError): module.refuse_legacy(cycle)
        module.refuse_legacy([{'kind': 'assign', 'args': {}} for _ in range(20001)])
        module.refuse_legacy({'kind': [], 'profile': {}})

    def test_old_kinds_and_markers_cannot_admit_new_operations(self):
        context = direct(source([]))
        for step in context['steps']:
            forged = asdict(step); forged['kind'] = 'data'
            with self.assertRaises(ValueError): run_plan({'version': 2, 'steps': [forged], 'tickets': [], 'matched': []})
        text = 'data d;input id $ @10 x eval.;datalines;\nA        High  \n;\nrun;\n'
        self.assertTrue(compile_plan(text).blocked)
        translation = translate_cpp(source([]))
        self.assertTrue(translation.blocked); self.assertIn('#error', translation.code)

    def test_actual_CLI_success_and_eight_wrong_dataset_comparators(self):
        cli_check(ORIGINAL.read_text(), original_expected())
        for name, wrong in wrong_cases():
            with self.subTest(name=name): cli_check(ORIGINAL.read_text(), wrong, True)

    def test_actual_late_failure_atomic_publication(self):
        self.assertEqual(atomic_cli(), 1)


if __name__ == '__main__': unittest.main()
