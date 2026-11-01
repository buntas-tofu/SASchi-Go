"""DS-069 source/portable records, exact character bytes and atomic evidence."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import inspect
import sys
import unittest

from examples.verify_character_input import (ORIGINAL, assert_exact, atomic_cli, batch_witness,
    cli_check, execute, generated_cases, hand_cases, original_accounting, original_expected, SOURCE_PIN, RESULT_PIN,
    refusal_cases, source, validate_original_trace, wrong_cases)
from . import character_input
from .emit_cpp import translate as translate_cpp
from .plan import compile_plan
from .runtime import run_plan


def direct(text):
    parsed = character_input.compile_program(text, compile_plan)
    if parsed is None or parsed.blocked:
        raise ValueError(None if parsed is None else parsed.tickets)
    return parsed


def portable(records=(), columns='a :$4. n'):
    return asdict(direct(source(list(records), columns)).steps[0])


class CharacterInputTests(unittest.TestCase):
    def test_original_hand_and_independent_complete_source(self):
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(), SOURCE_PIN)
        self.assertEqual(hashlib.sha256(json.dumps(original_expected(), separators=(',', ':')).encode()).hexdigest(), RESULT_PIN)
        witness = batch_witness([ORIGINAL.read_text()])[0]
        self.assertIsNotNone(witness)
        assert_exact(witness['result'], original_expected())
        self.assertEqual(witness['accounting'], original_accounting())
        assert_exact(execute(ORIGINAL.read_text(), emitted=True), original_expected())
        self.assertEqual(validate_original_trace(), {'observations': 6, 'attempts': 7, 'outputs': 6})

    def test_all_handpins_source_runtime_emitted_R(self):
        cases = hand_cases(); witnesses = batch_witness([case[1] for case in cases])
        for (name, text, truth), witness in zip(cases, witnesses):
            with self.subTest(name=name):
                self.assertIsNotNone(witness)
                assert_exact(witness['result'], truth)
                assert_exact(execute(text, emitted=True), truth)

    def test_constructive_generated_physical_records(self):
        cases = generated_cases(39); witnesses = batch_witness([case[0] for case in cases])
        for (text, truth), witness in zip(cases, witnesses):
            self.assertIsNotNone(witness); assert_exact(witness['result'], truth)
            assert_exact(execute(text), truth)

    def test_source_refusals_independent_on_empty_and_populated(self):
        cases = refusal_cases(); witnesses = batch_witness([case[1] for case in cases])
        for (name, text), witness in zip(cases, witnesses):
            with self.subTest(name=name):
                self.assertTrue(compile_plan(text).blocked)
                self.assertIsNone(witness)

    def test_exact_typed_schema_and_private_rows(self):
        step = portable([' A ,1.5', ',.']); saved = deepcopy(step)
        context = character_input.validate_step(step)
        self.assertEqual(context['schema'], {'a': {'type': 'character', 'length': 4},
                                            'n': {'type': 'number', 'length': 8}})
        table, log = character_input.execute_step(step)
        self.assertEqual(log, []); self.assertEqual(table['rows'], [{'a': 'A   ', 'n': 1.5}, {'a': '    ', 'n': None}])
        table['schema']['a']['length'] = 1; table['rows'][0]['a'] = 'changed'
        self.assertEqual(step, saved)
        self.assertEqual(character_input.execute_step(step)[0]['rows'][0]['a'], 'A   ')

    def test_physical_short_extra_and_blank_never_flowover(self):
        for records in (['A', '1'], ['A,1,ignored'], ['']):
            with self.assertRaises(ValueError): direct(source(records))
        self.assertEqual(character_input.execute_step(portable([''], 'a :$4.'))[0]['rows'], [{'a': '    '}])

    def test_empty_and_single_empty_span_differ(self):
        empty = character_input.execute_step(portable([], 'a :$4.'))[0]
        blank = character_input.execute_step(portable([''], 'a :$4.'))[0]
        self.assertEqual(empty['schema'], blank['schema']); self.assertEqual(empty['rows'], [])
        self.assertEqual(blank['rows'], [{'a': '    '}])

    def test_every_empty_span_and_outer_space_padding(self):
        step = portable([',,', ' A B ,  , . '], 'x :$4. y :$2. n')
        self.assertEqual(character_input.execute_step(step)[0]['rows'], [
            {'x': '    ', 'y': '  ', 'n': None}, {'x': 'A B ', 'y': '  ', 'n': None}])
        for field in ('.', ' . ', 'ABCDE'):
            step = portable([]); step['operations'][0]['args']['records'] = [field + ',1']
            step['operations'][0]['args']['source_lines'][4:] = [6, 7]
            with self.assertRaises(ValueError): character_input.validate_step(step)

    def test_maximum_record_width_and_record_count(self):
        self.assertEqual(len(character_input.execute_step(portable(['x' * 64 + ',' + ' ' * 15], 'a :$64. n'))[0]['rows']), 1)
        for records in (['x' * 64 + ',' + ' ' * 16], ['A,1'] * 1001):
            with self.assertRaises(ValueError): direct(source(records, 'a :$64. n'))
        self.assertEqual(len(character_input.execute_step(portable(['A,1'] * 1000))[0]['rows']), 1000)

    def test_name_count_width_and_exact_ascii_before_casefold(self):
        columns = 'a :$1. ' + ' '.join('n' + str(i) for i in range(31))
        self.assertEqual(len(character_input.validate_step(portable([], columns))['schema']), 32)
        for declaration in (columns + ' excess', 'a :$0.', 'a :$65.', 'a :$2. A',
                            'K :$2.', 'aK :$2.', '_error_ :$2.', 'a :$2. _numeric_'):
            with self.assertRaises(ValueError): direct(source([], declaration))
        step = portable([], 'MiXeD :$1. Input')
        self.assertEqual(list(character_input.validate_step(step)['schema']), ['mixed', 'input'])

    def test_old_exact_numeric_conversion_eager_on_late_record(self):
        for token in ('0.1', '2147483648', '1e-16', '.A', 'NaN', '1' * 33):
            with self.assertRaises(ValueError): direct(source(['A,1', 'B,' + token]))
        rows = character_input.execute_step(portable(['A,-0', 'B,+.5', 'C,.', 'D,']))[0]['rows']
        self.assertEqual([row['n'] for row in rows], [0., .5, None, None])

    def test_character_punctuation_remains_opaque_source(self):
        text = source(['%&(),1', ';\\,2', 'x/*,3'])
        table = character_input.execute_step(asdict(direct(text).steps[0]))[0]
        self.assertEqual([row['a'] for row in table['rows']], ['%&()', ';\\  ', 'x/* '])
        self.assertEqual(len(direct(text).steps), 1)

    def test_line_provenance_comments_multiline_and_CRLF(self):
        text = '/* harmless sqrt(log(1)); */\n' + source(['A,1']).replace('input a :$4. n;', 'input\n A :$4.\n N;')
        step = asdict(direct(text).steps[0]); lines = step['operations'][0]['args']['source_lines']
        self.assertEqual(lines, [2, 3, 4, 7, 9, 10])
        other = asdict(direct(text.replace('\n', '\r\n')).steps[0]); self.assertEqual(step, other)
        self.assertTrue(any(item[2] == 4 for item in direct(text).matched))
        commented = '/* ignored π comment */\n' + source(['A,1'])
        self.assertIsNotNone(batch_witness([commented])[0])
        self.assertEqual(character_input.execute_step(asdict(direct(commented).steps[0]))[0]['rows'], [{'a': 'A   ', 'n': 1.}])

    def test_exact_terminator_and_datalines4_header_boundary(self):
        for text in (source([]).replace(';;;;', ' ;;;;'), source([]).replace(';;;;', ';;;; '),
                     source([]).replace('datalines4;\n', 'datalines4;A,1\n'),
                     source([]).replace(';;;;\n', ';;;\n'), source([]).replace('run;', '')):
            with self.assertRaises(ValueError): direct(text)

    def test_portable_exact_step_operation_and_profile_fields(self):
        baseline = portable([])
        for change in (lambda s: s.update(extra='ignored'), lambda s: s.update(inputs=['raw']),
                       lambda s: s.update(display_names={'a': 'A'}), lambda s: s.update(lengths={'a': 4}),
                       lambda s: s.update(retained={'a': ''}), lambda s: s.update(where={}),
                       lambda s: s.update(nodupkey=0), lambda s: s['operations'][0].update(extra=0),
                       lambda s: s['operations'][0]['args'].update(extra='ignored'),
                       lambda s: s['operations'][0]['args'].update(profile='input-list-v1')):
            step = deepcopy(baseline); change(step)
            with self.assertRaises(ValueError): character_input.validate_step(step)
        for version in (1, 2., True, '2', None):
            with self.assertRaises(ValueError): character_input.validate_step(baseline, version)

    def test_forged_descriptor_validation_even_empty(self):
        baseline = portable([])
        for change in (lambda c: c.update(extra='ignored'), lambda c: c.update(type='numeric'),
                       lambda c: c.update(length=True), lambda c: c.update(length=0),
                       lambda c: c.update(length=65), lambda c: c.update(name='_error_'),
                       lambda c: c.update(name='A'), lambda c: c.update(name='K')):
            step = deepcopy(baseline); change(step['operations'][0]['args']['columns'][0])
            with self.assertRaises(ValueError): character_input.validate_step(step)
        step = deepcopy(baseline); step['operations'][0]['args']['columns'][1]['length'] = 4
        with self.assertRaises(ValueError): character_input.validate_step(step)

    def test_forged_line_counts_types_and_payload_provenance(self):
        baseline = portable([])
        for key in ('line',):
            for bad in (True, 1., 0, '1', None):
                step = deepcopy(baseline); step[key] = bad
                with self.assertRaises(ValueError): character_input.validate_step(step)
        for index in range(6):
            step = deepcopy(baseline); step['operations'][0]['args']['source_lines'][index] = True
            with self.assertRaises(ValueError): character_input.validate_step(step)
        for lines in ([1, 2, 3, 4, 7, 8], [1, 3, 2, 4, 5, 6], [1, 2, 3, 4, 5, 5]):
            step = deepcopy(baseline); step['operations'][0]['args']['source_lines'] = lines
            with self.assertRaises(ValueError): character_input.validate_step(step)

    def test_forged_raw_records_do_not_bypass_byte_field_or_domain_checks(self):
        for record in ('"A",1', "A'B,1", 'é,1', 'A\t,1', 'A\n,1', 'ABCDE,1', 'A,0.1', 'A,1,2', 'A'):
            step = portable([]); args = step['operations'][0]['args']; args['records'] = [record]
            args['source_lines'][4:] = [6, 7]
            with self.assertRaises(ValueError): character_input.validate_step(step)

    def test_direct_fresh_destination_case_insensitive_and_no_mutation(self):
        step = portable([])
        for supplied in ({'d': {}}, {'D': {}}, {1: {}}, [], 'bad'):
            before = deepcopy(supplied)
            with self.assertRaises(ValueError): character_input.execute_step(step, supplied)
            self.assertEqual(supplied, before)
        supplied = {'other': {'schema': {}, 'rows': []}}; before = deepcopy(supplied)
        character_input.execute_step(step, supplied); self.assertEqual(supplied, before)

    def test_new_family_rejects_initial_catalog_even_unused(self):
        parsed = compile_plan(source([])); self.assertFalse(parsed.blocked, parsed.tickets)
        supplied = {'unused': {'schema': {'x': 'number'}, 'rows': [{'x': 1.}]}}
        before = deepcopy(supplied)
        with self.assertRaises(ValueError): run_plan(parsed.to_dict(), supplied)
        self.assertEqual(supplied, before)

    def test_old_kind_hidden_operation_and_profile_guards(self):
        baseline = compile_plan('data d;x=1;run;').to_dict()
        new = portable([])['operations'][0]
        for value in (new, {'kind': 'if', 'args': {'then': new}}, {'profile': character_input.PROFILE}):
            with self.assertRaises(ValueError): character_input.refuse_legacy(value)
        for position in (0, -1):
            plan = deepcopy(baseline); plan['steps'][0]['operations'].insert(position, deepcopy(new))
            with self.assertRaises(ValueError): run_plan(plan)
        step = portable([]); step['kind'] = 'data'
        plan = deepcopy(baseline); plan['steps'] = [step]
        with self.assertRaises(ValueError): run_plan(plan)

    def test_cycle_guard_malformed_kinds_and_large_old_shapes(self):
        cyclic = []; cyclic.append(cyclic)
        with self.assertRaises(ValueError): character_input.refuse_legacy(cyclic)
        character_input.refuse_legacy({'kind': [], 'args': {}})
        old = compile_plan('data d;x=1;run;').to_dict()
        old['steps'][0]['operations'] *= 20001
        character_input.refuse_legacy(old['steps'][0]['operations'])
        self.assertEqual(run_plan(old)['datasets']['d']['rows'], [{'x': 1.}])

    def test_hidden_guard_shared_graph_is_linear_and_still_checks_late_leaves(self):
        graph = []
        for _ in range(12):
            graph = [graph, graph]
        lines, first = inspect.getsourcelines(character_input.refuse_legacy)
        pop_line = first + next(index for index, line in enumerate(lines) if 'item, leaving = pending.pop()' in line)
        count = 0
        def bounded(frame, event, argument):
            nonlocal count
            if frame.f_code is character_input.refuse_legacy.__code__ and event == 'line' and frame.f_lineno == pop_line:
                count += 1
                self.assertLessEqual(count, 128, 'shared containers were traversed repeatedly')
            return bounded
        previous = sys.gettrace()
        try:
            sys.settrace(bounded)
            character_input.refuse_legacy(graph)
            self.assertLessEqual(count, 39)
            count = 0
            with self.assertRaises(ValueError):
                character_input.refuse_legacy([{'kind': character_input.OPERATION}, graph])
        finally:
            sys.settrace(previous)
        cycle = [graph]
        cycle.append(cycle)
        with self.assertRaises(ValueError):
            character_input.refuse_legacy(cycle)

    def test_compiler_only_character_and_SORT_composition(self):
        for text in (source([]) + 'data other;x=1;run;', 'data other;x=1;run;' + source([]),
                     source([]) + 'proc means data=d;run;'):
            self.assertTrue(compile_plan(text).blocked)
        text = source(['B,1', 'A,2', 'A,3'], sort=True)
        rows = execute(text, emitted=True)['datasets']['ordered']['rows']
        self.assertEqual([row['n'] for row in rows], [2., 3., 1.])
        sixty_four = ''.join(source([], name='d' + str(i)) for i in range(64))
        self.assertFalse(compile_plan(sixty_four).blocked)
        self.assertTrue(compile_plan(sixty_four + source([], name='overflow')).blocked)

    def test_source_prefixes_do_not_trigger_on_comments_or_old_opaque_data(self):
        for prefix in ('/* input A :$7.; infile datalines dsd; datalines4; */\n', '* datalines4;\n'):
            text = prefix + 'data d;x=1;run;'
            self.assertIsNone(character_input.compile_program(text, compile_plan))
            self.assertFalse(compile_plan(text).blocked)
        text = 'data d;input x;datalines;\n1 ignored_datalines4\n;\nrun;'
        self.assertIsNone(character_input.compile_program(text, compile_plan))
        self.assertEqual(run_plan(compile_plan(text).to_dict())['datasets']['d']['rows'], [{'x': 1.}])

    def test_original_actual_CLI_and_exact_wrong_dataset_controls(self):
        self.assertTrue(cli_check(ORIGINAL.read_text(), original_expected()))
        for _, wrong in wrong_cases(): self.assertTrue(cli_check(ORIGINAL.read_text(), wrong, True))

    def test_late_bad_record_and_later_step_fail_atomically_CLI(self):
        self.assertEqual(atomic_cli(), 2)

    def test_CPP_refuses_new_operation_and_kind(self):
        translation = translate_cpp(source(['A,1']))
        self.assertTrue(translation.blocked)
        self.assertTrue(any(ticket.construct == 'cpp-target' for ticket in translation.tickets))


if __name__ == '__main__':
    unittest.main()
