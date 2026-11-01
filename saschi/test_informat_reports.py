"""Executable boundaries for the separate informat report components."""
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal, localcontext, ROUND_HALF_UP
from fractions import Fraction
import inspect
import json
import sys
import unittest

from .parser import split_statements
from . import informat_reports as reports


def title(text=None):
    return asdict(reports.compile_title(split_statements('title;' if text is None else 'title ' + json.dumps(text) + ';')[0]))


def printed(labels='word="Raw word" n="Score"'):
    return asdict(reports.compile_print(split_statements('proc print data=sample label noobs;label ' + labels + ';run;')))


def means():
    return asdict(reports.compile_means(split_statements('proc means data=sample;run;')))


def table(values=(4, 2, 1, 2, 4)):
    return {'sample': {'schema': {'word': {'type': 'character', 'length': 8}, 'n': {'type': 'number', 'length': 8}},
                       'rows': [{'word': ('row' + str(i)).ljust(8), 'n': value} for i, value in enumerate(values)]}}


class InformatReportTests(unittest.TestCase):
    def test_original_exact_statistics_and_local_labels(self):
        tables = table(); before = deepcopy(tables); trace = []
        actual = reports.execute_means(means(), tables, 'Active', trace=trace)
        self.assertEqual(actual, {'means_01.txt': 'TITLE: Active\nvariable n mean std min max\n"n" 5 2.60000000 1.34164079 1 4\n'})
        self.assertIn('default-means|stats|n|5|13|41|13/5|9/5', trace)
        report = reports.execute_print(printed(), tables, 'Active')
        self.assertEqual(report['print_01.txt'].splitlines()[1], '"Raw word" "Score"')
        self.assertEqual(tables, before)
        self.assertNotIn('label', tables['sample']['schema']['n'])

    def test_title_reset_edges_and_macro_policy(self):
        self.assertIsNone(reports.execute_title(title()))
        self.assertEqual(reports.execute_title(title('  Exact  ')), '  Exact  ')
        for value in ['', ' ', '&x', '%x', '\t', 'é', 'x' * 129, False, 1]:
            step = title('x'); step['operations'][0]['args']['text'] = value
            with self.subTest(value=value), self.assertRaises(ValueError): reports.validate_step(step)

    def test_exact_half_away_mean_positive_negative_and_zero(self):
        self.assertEqual(reports._fixed8(Fraction(1, 512)), '0.00195313')
        self.assertEqual(reports._fixed8(Fraction(-1, 512)), '-0.00195313')
        self.assertEqual(reports._fixed8(Fraction(-1, 10**20)), '0.00000000')
        values = [0] * 511 + [1]
        self.assertIn('0.00195313', reports.execute_means(means(), table(values))['means_01.txt'])

    def test_exact_square_root_midpoint_and_adjacent_variances(self):
        midpoint = Fraction(24691357, 200000000)
        square = midpoint * midpoint
        self.assertEqual(reports._fixed8(square, square_root=True), '0.12345679')
        self.assertEqual(reports._fixed8(square - Fraction(1, 10**30), square_root=True), '0.12345678')
        self.assertEqual(reports._fixed8(square + Fraction(1, 10**30), square_root=True), '0.12345679')
        with self.assertRaises(ValueError): reports._fixed8(Fraction(-1), square_root=True)

    def test_fixed8_matches_independent_decimal_for_rational_grid(self):
        with localcontext() as context:
            context.prec = 90
            for numerator in range(-9, 10):
                for denominator in (1, 2, 3, 7, 16, 31, 512, 999):
                    value = Fraction(numerator, denominator)
                    expected = (Decimal(numerator) / Decimal(denominator)).quantize(Decimal('.00000001'), rounding=ROUND_HALF_UP)
                    expected = '0.00000000' if expected == 0 else str(expected)
                    self.assertEqual(reports._fixed8(value), expected)
                    if numerator >= 0:
                        expected = (Decimal(numerator) / Decimal(denominator)).sqrt().quantize(Decimal('.00000001'), rounding=ROUND_HALF_UP)
                        self.assertEqual(reports._fixed8(value, square_root=True), format(expected, 'f'))

    def test_full_domain_extremes_and_fourteen_byte_tokens(self):
        text = reports.execute_means(means(), table([-1000, 1000]))['means_01.txt']
        self.assertIn('0.00000000 1414.21356237 -1000 1000', text)
        self.assertEqual(reports._fixed8(Fraction(-1000)), '-1000.00000000')
        self.assertEqual(len(reports._fixed8(Fraction(-1000))), 14)
        with self.assertRaises(ValueError): reports._fixed8(Fraction(-10000))

    def test_empty_missing_singleton_and_constant_statistics(self):
        for values, expected in [([], '0 . . . .'), ([None, None], '0 . . . .'), ([3, None], '1 3.00000000 . 3 3'), ([3, 3], '2 3.00000000 0.00000000 3 3')]:
            with self.subTest(values=values): self.assertIn('"n" ' + expected + '\n', reports.execute_means(means(), table(values))['means_01.txt'])
        self.assertEqual(reports.execute_print(printed(), table([])), {'print_01.txt': '"Raw word" "Score"\n'})

    def test_all_numeric_selection_preserves_descriptor_order(self):
        tables = {'sample': {'schema': {'b': {'type': 'number', 'length': 8}, 'id': {'type': 'character', 'length': 1}, 'a': {'type': 'number', 'length': 8}}, 'rows': [{'b': 2, 'id': 'X', 'a': 1}]}}
        text = reports.execute_means(means(), tables)['means_01.txt']
        self.assertEqual([line.split(' ')[0] for line in text.splitlines()[1:]], ['"b"', '"a"'])

    def test_schema_plainness_and_eager_empty_validation(self):
        for mutation in [lambda x: x['sample']['schema']['n'].update(label='No'), lambda x: x['sample']['schema']['n'].update(format='best12.'), lambda x: x['sample']['schema']['n'].update(length=True), lambda x: x['sample']['schema'].update(BAD={'type': 'number', 'length': 8})]:
            tables = table([]); mutation(tables)
            with self.assertRaises(ValueError): reports.execute_means(means(), tables)
        with self.assertRaises(ValueError): reports.execute_print(printed('absent="X"'), table([]))
        tables = table([]); del tables['sample']['schema']['n']
        with self.assertRaises(ValueError): reports.execute_means(means(), tables)

    def test_original_numeric_cells_validate_before_coercion(self):
        for value in [True, False, '1', {'missing': 'A'}, float('inf'), float('nan'), .5, 1001, -1001]:
            with self.subTest(value=value), self.assertRaises(ValueError): reports.execute_means(means(), table([value]))
            with self.subTest(value=value), self.assertRaises(ValueError): reports.execute_print(printed(), table([value]))

    def test_character_cells_are_exact_ascii_padded_and_escape(self):
        for value in ['x', '\t' * 8, 'é' * 8, None, 2]:
            tables = table([1]); tables['sample']['rows'][0]['word'] = value
            with self.assertRaises(ValueError): reports.execute_print(printed(), tables)
        tables = table([1]); tables['sample']['rows'][0]['word'] = ' \\"x    '
        self.assertEqual(len(tables['sample']['rows'][0]['word']), 8)
        result = reports.execute_print(printed(), tables)['print_01.txt']
        self.assertIn(json.dumps(' \\"x') + ' 1\n', result)

    def test_strict_step_defaults_version_and_profiles(self):
        for factory in (title, printed, means):
            for version in [1, 2.0, True, '2', None]:
                with self.assertRaises(ValueError): reports.validate_step(factory(), version)
            for field, value in [('extra', 1), ('retained', {'x': 1}), ('display_names', {'n': 'N'}), ('by', ['n']), ('nodupkey', 0), ('where', {})]:
                step = factory(); step[field] = value
                with self.assertRaises(ValueError): reports.validate_step(step)
            step = factory(); step['operations'][0]['args']['profile'] = 'mixed-print-v1'
            with self.assertRaises(ValueError): reports.validate_step(step)

    def test_unrelated_portable_presentation_knobs_refuse(self):
        for factory in (printed, means):
            for field in ['names', 'ordinal', 'basename', 'statistics', 'labels' if factory is means else 'width']:
                step = factory(); step['operations'][0]['args'][field] = []
                with self.assertRaises(ValueError): reports.validate_step(step)
            step = factory(); step['inputs'] = ['other']
            with self.assertRaises(ValueError): reports.validate_step(step)
            step = factory(); step['operations'][0]['line'] += 1
            with self.assertRaises(ValueError): reports.validate_step(step)

    def test_label_validation_duplicates_and_unknown_names(self):
        for source in ['label n="x" n="y"', 'label n=""', 'label n=" "', 'label n="&x"', 'label _n_="x"', 'label n="' + 'x' * 65 + '"']:
            with self.assertRaises(ValueError): reports.compile_print(split_statements('proc print data=sample label noobs;' + source + ';run;'))
        for labels in [[], [{'name': 'n', 'text': 'X', 'extra': 0}], [{'name': 'N', 'text': 'X'}]]:
            step = printed(); step['operations'][0]['args']['labels'] = labels
            with self.assertRaises(ValueError): reports.validate_step(step)

    def test_source_consumption_ascii_and_terminators(self):
        for source in ['proc print data=sample label;label n="X";run;', 'proc print data=sample label noobs;run;', 'proc print data=sample label noobs;label n="X";var n;run;', 'proc print data=sample label noobs;label n="X";run', 'proc print data=sample label noobs;label n="X" junk;run;']:
            with self.assertRaises(ValueError): reports.compile_print(split_statements(source))
        for source in ['proc means data=sample n;run;', 'proc means data=sample;var n;run;', 'proc means data=sample;run']:
            with self.assertRaises(ValueError): reports.compile_means(split_statements(source))
        with self.assertRaises(ValueError): reports.compile_title(split_statements('title "é";')[0])

    def test_doubled_quotes_and_same_line_source_positions(self):
        step = reports.compile_print(split_statements('proc print data=SAMPLE label noobs;label n="A ""quote""" word=\'It\'\'s\';run;'))
        context = reports.validate_step(asdict(step))
        self.assertEqual(context['labels'], {'n': 'A "quote"', 'word': "It's"})
        self.assertEqual(step.operations[0].args['source_lines'], [1, 1])

    def test_row_column_numeric_and_rendered_caps(self):
        with self.assertRaises(ValueError): reports.execute_means(means(), table([0] * 1001))
        self.assertIn('1000 0.00000000 0.00000000 0 0', reports.execute_means(means(), table([0] * 1000))['means_01.txt'])
        schema = {'n' + str(i): {'type': 'number', 'length': 8} for i in range(9)}
        with self.assertRaises(ValueError): reports.execute_means(means(), {'sample': {'schema': schema, 'rows': []}})
        step = printed('n="' + 'X' * 64 + '"'); tables = table([0]); tables['sample']['schema'] = {'v' + str(i): {'type': 'character', 'length': 32} for i in range(32)}
        tables['sample']['rows'] = [{name: 'x' * 32 for name in tables['sample']['schema']}]
        step['operations'][0]['args']['labels'] = [{'name': 'v0', 'text': 'X'}]
        with self.assertRaises(ValueError): reports.execute_print(step, tables)

    def test_report_names_control_bytes_and_final_newline(self):
        for value in [{}, {'print.txt': 'x\n'}, {'print_01.txt': '"X"'}, {'print_01.txt': '"X"\n\t\n'}, {'means_01.txt': 'variable n mean std min max\n'}, {'print_01.txt': '"X"\n"\\u00e9"\n'}, {'print_01.txt': '"X"\n"\\t"\n'}]:
            with self.assertRaises(ValueError): reports.validate_reports(value)
        merged = reports.execute_print(printed(), table([])) | reports.execute_means(means(), table([]))
        self.assertEqual(reports.validate_reports(merged), merged)

    def test_exact_header_row_and_total_boundary(self):
        step = printed(); schema = {'c' + str(i): {'type': 'character', 'length': 10} for i in range(32)}
        step['operations'][0]['args']['labels'] = [{'name': name, 'text': 'X' * 30} for name in schema]
        tables = {'sample': {'schema': schema, 'rows': [{name: 'x' * 10 for name in schema} for _ in range(1000)]}}
        text = reports.execute_print(step, tables)['print_01.txt']
        self.assertEqual(len(text.splitlines()[0]), 1055)
        self.assertEqual(len(text.splitlines()[1]), 415)
        self.assertEqual(len(text), 417056)
        with self.assertRaises(ValueError): reports.execute_print(step, tables, 'T')
        changed = deepcopy(step); changed['operations'][0]['args']['labels'][0]['text'] += 'X'
        with self.assertRaises(ValueError): reports.execute_print(changed, tables)
        changed = deepcopy(tables); changed['sample']['schema']['c0']['length'] = 11
        for row in changed['sample']['rows']: row['c0'] += 'x'
        with self.assertRaises(ValueError): reports.execute_print(step, changed)

    def test_hidden_markers_cycles_DAG_and_large_old_flat_shape(self):
        for kind in reports.KINDS:
            with self.assertRaises(ValueError): reports.refuse_legacy({'kind': 'data', 'skipped': {'kind': kind}})
        for profile in reports.PROFILES:
            with self.assertRaises(ValueError): reports.refuse_legacy({'profile': profile})
        cycle = []; cycle.append(cycle)
        with self.assertRaises(ValueError): reports.refuse_legacy(cycle)
        dag = []
        for _ in range(12): dag = [dag, dag]
        lines, first = inspect.getsourcelines(reports.refuse_legacy)
        anchor = first + next(i for i, text in enumerate(lines) if 'pending.pop()' in text)
        visits = [0]
        def count(frame, event, arg):
            if event == 'line' and frame.f_code is reports.refuse_legacy.__code__ and frame.f_lineno == anchor: visits[0] += 1
            return count
        sys.settrace(count)
        try: reports.refuse_legacy(dag)
        finally: sys.settrace(None)
        self.assertLessEqual(visits[0], 39)
        with self.assertRaises(ValueError): reports.refuse_legacy([{'kind': 'default_means'}, dag])
        reports.refuse_legacy([{'kind': 'assign', 'args': {'value': i}} for i in range(20001)])

    def test_callers_and_trace_do_not_mutate_inputs(self):
        steps = [title('X'), printed(), means()]; tables = table(); original = deepcopy((steps, tables)); trace = []
        current = reports.execute_title(steps[0], trace=trace)
        reports.execute_print(steps[1], tables, current, trace=trace)
        reports.execute_means(steps[2], tables, current, trace=trace)
        self.assertEqual((steps, tables), original)
        self.assertTrue(any('13/5|9/5' in event for event in trace))

    def test_independent_R_exact_limb_rounding(self):
        from examples.verify_labelled_print import round_witness
        import random
        rng = random.Random(7315)
        cases = [('mean', Fraction(1, 512)), ('mean', Fraction(-1, 512)), ('std', Fraction(24691357, 200000000)**2)]
        middle = cases[-1][1]
        cases += [('std', middle - Fraction(1, 10**30)), ('std', middle + Fraction(1, 10**30)), ('std', Fraction(2000000))]
        cases += [('std', Fraction(rng.randint(0, 1000000), rng.randint(1, 1000000))) for _ in range(70)]
        cases += [('mean', Fraction(rng.randint(-1000, 1000), rng.randint(1, 1000))) for _ in range(70)]
        expected = []
        with localcontext() as context:
            context.prec = 100
            for kind, value in cases:
                exact = Decimal(value.numerator) / Decimal(value.denominator)
                if kind == 'std': exact = exact.sqrt()
                token = exact.quantize(Decimal('.00000001'), rounding=ROUND_HALF_UP)
                expected.append('0.00000000' if token == 0 else format(token, 'f'))
        self.assertEqual(round_witness(cases), expected)

    def test_original_full_source_public_R_emitted_and_CLI(self):
        from examples.verify_labelled_print import ORIGINAL, original_expected, original_trace, ORIGINAL_ACCOUNT, program_witness, execute, assert_tree, cli_check
        from pathlib import Path
        import tempfile
        expected = original_expected(); witness = program_witness()
        assert_tree(witness['result'], expected); assert_tree(witness['trace'], original_trace())
        self.assertEqual(witness['accounting'], ORIGINAL_ACCOUNT)
        self.assertEqual(len(original_trace()), 30)
        for emitted in (False, True):
            actual = execute(ORIGINAL.read_text(), emitted)
            assert_tree(actual['result'], expected); assert_tree(actual['trace'], original_trace())
        with tempfile.TemporaryDirectory(prefix='informat-report-unit-') as temporary:
            cli_check(ORIGINAL.read_text(), expected['datasets'], expected['reports'], Path(temporary) / 'accepted')

    def test_complete_generated_source_and_shared_refusal_surfaces(self):
        from examples.verify_labelled_print import hand_cases, generated_cases, refusal_cases, batch_witness, execute, assert_tree
        from .plan import compile_plan
        from .runtime import run_plan
        cases = hand_cases()[:5] + generated_cases(count=9)
        for source, witness in zip(cases, batch_witness(cases), strict=True):
            self.assertIsNotNone(witness); actual = execute(source, True)
            assert_tree(actual['result'], witness['result']); assert_tree(actual['trace'], witness['trace'])
        refused = refusal_cases()
        for source, witness in zip(refused, batch_witness(refused), strict=True):
            self.assertIsNone(witness)
            parsed = compile_plan(source)
            if not parsed.blocked:
                with self.assertRaises((ValueError, RuntimeError)): run_plan(parsed.to_dict())

    def test_old_source_compiler_and_old_report_markers_preserved(self):
        from examples.verify_labelled_print import ORIGINAL
        from .plan import _compile_before_formatted_program
        from .procedures import validate_step as validate_old
        from .mixed_reports import validate_step as validate_mixed
        self.assertTrue(_compile_before_formatted_program(ORIGINAL.read_text()).blocked)
        step = printed(); step['kind'] = 'proc_print'; step['operations'][0]['kind'] = 'proc_print'
        step['operations'][0]['args']['profile'] = 'numeric-print-v1'
        with self.assertRaises(ValueError): validate_old(step)
        step = printed(); step['kind'] = 'mixed_print'; step['operations'][0]['kind'] = 'mixed_print'
        step['operations'][0]['args']['profile'] = 'mixed-print-v1'
        with self.assertRaises(ValueError): validate_mixed(step)

    def test_new_family_preflight_empty_labels_and_numeric_selection(self):
        from examples.verify_labelled_print import source
        from .plan import compile_plan
        from .runtime import run_plan
        parsed = compile_plan(source([])).to_dict()
        original = deepcopy(parsed)
        for step in parsed['steps']:
            if step['kind'] == 'labelled_print': step['operations'][0]['args']['labels'][0]['name'] = 'absent'
        with self.assertRaises(ValueError): run_plan(parsed)
        parsed = deepcopy(original)
        for step in parsed['steps']:
            if step['kind'] == 'default_means': step['operations'][0]['args']['statistics'] = []
        with self.assertRaises(ValueError): run_plan(parsed)

    def test_genuine_late_failure_discards_earlier_MEANS_artifact(self):
        from examples.verify_labelled_print import wide_source
        from .job import build_job
        from unittest.mock import patch
        seen = []; native = reports.execute_means
        def observe(*args, **kwargs): seen.append('means'); return native(*args, **kwargs)
        with patch.object(reports, 'execute_means', observe): result = build_job(wide_source(1, means_first=True))
        self.assertFalse(result.plan.blocked); self.assertEqual(seen, ['means'])
        self.assertIsNone(result.result); self.assertEqual(result.code, 1)


if __name__ == '__main__':
    unittest.main()
