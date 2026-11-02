"""Public source and portable boundaries for PROC SORT input KEEP=."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from . import sort_projection as projection


def producer(records='b,2,1,11\na,1,2,22\nc,2,3,33',
             columns='label :$2. k id discarded', name='raw'):
    return ('data ' + name + ';\ninfile datalines dsd;\ninput ' + columns
            + ';\ndatalines4;\n' + (records + '\n' if records else '') + ';;;;\nrun;\n')


def source(records='b,2,1,11\na,1,2,22\nc,2,3,33', keep='label k id',
           by='k', options='', tail=''):
    return (producer(records) + 'proc sort data=raw(keep=' + keep + ') out=ordered'
            + options + ';\nby ' + by + ';\nrun;\n' + tail)


class SortProjectionTests(unittest.TestCase):
    def plan(self, text=None):
        parsed = compile_plan(source() if text is None else text)
        self.assertFalse(parsed.blocked, parsed.tickets)
        return parsed.to_dict()

    def blocked(self, text):
        self.assertTrue(compile_plan(text).blocked)

    def table(self):
        return run_plan(compile_plan(producer()).to_dict())['datasets']['raw']

    def test_keep_restricts_columns_without_mutating_source(self):
        result = run_plan(self.plan())
        self.assertEqual(list(result['datasets']['ordered']['schema']), ['label', 'k', 'id'])
        self.assertEqual([row['id'] for row in result['datasets']['ordered']['rows']], [2, 1, 3])
        self.assertEqual(list(result['datasets']['raw']['schema']), ['label', 'k', 'id', 'discarded'])
        self.assertEqual([row['id'] for row in result['datasets']['raw']['rows']], [1, 2, 3])

    def test_keep_list_order_does_not_reorder_descriptors(self):
        result = run_plan(self.plan(source(keep='id label k')))
        table = result['datasets']['ordered']
        self.assertEqual(list(table['schema']), ['label', 'k', 'id'])
        self.assertEqual(table['schema']['label'], {'type': 'character', 'length': 2})
        self.assertEqual(table['rows'][0]['label'], 'a ')

    def test_projection_precedes_sort_removed_by_refuses(self):
        self.blocked(source(keep='label id', by='k'))
        plan = self.plan()
        plan['steps'][1]['operations'][0]['args']['keep'] = ['label', 'id']
        with self.assertRaises(ValueError):
            projection.validate_program(plan)

    def test_nodupkey_keeps_first_stable_unequal_payload(self):
        result = run_plan(self.plan(source(options=' nodupkey')))
        rows = result['datasets']['ordered']['rows']
        self.assertEqual([(row['k'], row['id'], row['label']) for row in rows], [(1, 2, 'a '), (2, 1, 'b ')])

    def test_blank_padding_and_ordinary_missing_sort(self):
        result = run_plan(self.plan(source(',1,1,11\na,,2,22\nB,-1,3,33\na,,4,44', by='label k')))
        rows = result['datasets']['ordered']['rows']
        self.assertEqual([row['id'] for row in rows], [1, 3, 2, 4])
        self.assertEqual(rows[0]['label'], '  ')
        self.assertIsNone(rows[2]['k'])

    def test_exact_fraction_is_valid_sort_input(self):
        result = run_plan(self.plan(source('a,0.5,1,11\nb,-0.25,2,22\nc,0.5,3,33')))
        self.assertEqual([row['id'] for row in result['datasets']['ordered']['rows']], [2, 1, 3])

    def test_empty_table_keeps_full_selected_schema(self):
        result = run_plan(self.plan(source('')))
        self.assertEqual(result['datasets']['ordered']['rows'], [])
        self.assertEqual(list(result['datasets']['ordered']['schema']), ['label', 'k', 'id'])

    def test_reports_capture_before_and_after_projection(self):
        text = (producer() + 'title "before"; proc print data=raw; run;\n'
                + 'proc sort data=raw(keep=id label k) out=ordered; by k; run;\n'
                + 'title "after"; proc print data=ordered; run; title;')
        reports = run_plan(self.plan(text))['reports']
        self.assertIn('obs label k id discarded\n', reports['print_01.txt'])
        self.assertIn('obs label k id\n', reports['print_02.txt'])
        self.assertIn('1 "b" 2 1 11\n', reports['print_01.txt'])
        self.assertIn('1 "a" 1 2\n', reports['print_02.txt'])

    def test_public_step_context_is_copied_and_exact(self):
        step = self.plan()['steps'][1]
        original = deepcopy(step['operations'][0]['args'])
        context = projection.validate_step(step)
        self.assertEqual(context, original)
        context['keep'].append('not_source')
        self.assertEqual(step['operations'][0]['args'], original)
        self.assertEqual(step['kind'], 'projected_sort')
        self.assertEqual(original['profile'], 'sort-input-keep-v1')

    def test_preflight_executes_no_sort_engine(self):
        plan = self.plan()
        with patch.object(projection, 'execute_sort', side_effect=AssertionError('preflight must not sort')):
            self.assertIsNotNone(projection.validate_program(plan))

    def test_actual_sort_once_each_and_original_source_ordinals(self):
        text = source(tail='proc sort data=ordered out=unique_rows nodupkey; by k; run;')
        trace = []
        with patch.object(projection, 'execute_sort', wraps=projection.execute_sort) as execute:
            projection.run_program(self.plan(text), trace=trace)
        self.assertEqual(execute.call_count, 2)
        events = [event for event in trace if isinstance(event, dict) and event.get('event') == 'sort']
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]['source_ordinals'], [2, 1, 3])
        self.assertEqual(events[0]['kept_ordinals'], [2, 1, 3])
        self.assertEqual(events[1]['source_ordinals'], [1, 2, 3])
        self.assertEqual(events[1]['kept_ordinals'], [1, 2])
        self.assertFalse(any(isinstance(event, dict) and event.get('event') == 'projection' for event in trace))

    def test_emitted_and_runtime_results_agree(self):
        text = source(tail='proc print data=ordered; run;')
        emitted = translate(text)
        self.assertFalse(emitted.blocked)
        namespace = {}
        exec(emitted.code, namespace)
        self.assertEqual(namespace['result'], run_plan(emitted.plan))

    def test_plain_ascending_and_completed_directed_profiles_stay_distinct(self):
        plain = producer() + 'proc sort data=raw out=ordered; by k; run;'
        directed = producer() + 'proc sort data=raw out=ordered; by descending k; run;'
        all_columns = producer() + 'proc sort data=raw out=ordered nodupkey; by _all_; run;'
        self.assertEqual(compile_plan(plain).steps[1].kind, 'sort')
        self.assertEqual(compile_plan(directed).steps[1].kind, 'bounded_sort')
        self.assertEqual(compile_plan(all_columns).steps[1].kind, 'bounded_sort')
        for text in (plain, directed, all_columns):
            self.assertFalse(compile_plan(text).blocked)
            self.assertNotIn('sort-input-keep-v1', str(compile_plan(text).to_dict()))

    def test_comments_strings_and_opaque_payload_do_not_select(self):
        text = (producer('(KEEP=k),2,1,11', 'label :$20. k id discarded')
                + 'title "PROC SORT DATA=raw(KEEP=k)"; proc print data=raw; run;'
                + '/* PROC SORT DATA=raw(KEEP=k) OUT=x; BY k; RUN; */')
        parsed = compile_plan(text)
        self.assertFalse(parsed.blocked, parsed.tickets)
        self.assertNotIn('projected_sort', [step.kind for step in parsed.steps])

    def test_valid_keep_header_dataset_parentheses_are_not_function_calls(self):
        for name in ['raw', 'ROUND']:
            text = producer(name=name)
            text += 'proc sort data=' + name + '(keep=label k id) out=ordered; by k; run;'
            with self.subTest(dataset=name):
                job = build_job(text)
                self.assertEqual(job.code, 0)
                self.assertFalse(job.plan.blocked)
                completeness = job.receipt['completeness']
                self.assertEqual(completeness['status'], 'recorded')
                self.assertEqual(completeness['n_functions'], 0)
                self.assertEqual(completeness['n_matched'], 0)

    def test_invalid_keep_header_retains_real_function_census_and_refusal(self):
        for function, matched in [('f', 0), ('round', 1)]:
            text = source().replace('(keep=label k id)', '(keep=label k ' + function + '(id))')
            with self.subTest(function=function):
                job = build_job(text)
                self.assertEqual(job.code, 2)
                self.assertTrue(job.plan.blocked)
                completeness = job.receipt['completeness']
                self.assertEqual(completeness['status'], 'recorded')
                self.assertTrue(completeness['blocked'])
                # Invalid headers retain the ordinary dataset/function scanner.
                self.assertEqual(completeness['n_functions'], 2)
                self.assertEqual(completeness['n_matched'], matched)

    def test_prior_genuine_character_producer_is_required(self):
        self.blocked('proc sort data=raw(keep=label k) out=ordered; by k; run;' + producer())
        self.blocked(source().replace('label :$2.', 'label'))
        self.blocked('data raw; label=1; output; run; proc sort data=raw(keep=label) out=ordered; by label; run;')

    def test_keep_names_unknown_duplicate_and_empty_refuse(self):
        for keep in ['', 'label label k', 'label absent', 'label k k', 'label _all_', 'label k-id', '_character_']:
            with self.subTest(keep=keep):
                self.blocked(source(keep=keep))

    def test_numeric_only_selected_schema_refuses_even_without_print(self):
        self.blocked(source(keep='k id'))
        self.blocked(source('', keep='k id'))

    def test_unadmitted_projection_and_sort_combinations_refuse(self):
        for text in [source().replace('(keep=label k id)', '(drop=discarded)'),
                     source().replace('(keep=label k id)', '(keep=label k id drop=discarded)'),
                     source().replace('out=ordered', 'out=ordered(keep=label)'),
                     source(by='descending k'), source(by='_all_', options=' nodupkey'),
                     source(options=' dupout=removed'), source(options=' noduprecs'),
                     source(options=' sortseq=linguistic'), source(options=' noequalS')]:
            with self.subTest(text=text):
                self.blocked(text)

    def test_by_names_duplicate_unknown_and_special_refuse(self):
        for by in ['', 'k k', 'missing', '_all_', 'k notsorted', 'k-id']:
            with self.subTest(by=by):
                self.blocked(source(by=by))

    def test_fresh_explicit_out_required_even_when_empty(self):
        self.blocked(source('').replace('out=ordered', 'out=raw'))
        self.blocked(source('').replace('out=ordered', ''))
        self.blocked(source('') + 'proc sort data=raw(keep=label k) out=ordered; by k; run;')

    def test_exact_semicolons_and_step_statement_consumption(self):
        for text in [source()[:-2], source().replace('by k;', 'by k'),
                     source().replace('by k;', 'by k; output;'), source() + 'unknown;']:
            with self.subTest(text=text):
                self.blocked(text)

    def test_portable_step_defaults_and_provenance_refuse(self):
        for change in [lambda s: s.update(kind='sort'), lambda s: s.update(by=['k']),
                       lambda s: s.update(nodupkey=True), lambda s: s.update(where={}),
                       lambda s: s.update(retained={'k': 0}), lambda s: s.update(line=True),
                       lambda s: s['operations'][0].update(line=0),
                       lambda s: s['operations'][0]['args'].update(extra=True),
                       lambda s: s['operations'][0]['args'].update(source_lines=[1, 0]),
                       lambda s: s['operations'][0]['args'].update(source_lines=[True, 20])]:
            plan = self.plan(); change(plan['steps'][1])
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                projection.validate_program(plan)

    def test_portable_keep_and_by_context_refusals(self):
        for field, values in [('keep', [[], ['label', 'label'], ['label', 'absent'], ['LABEL', 'k'], ['k', 'id'], ['label'] * 33]),
                              ('by', [[], ['k', 'k'], ['missing'], ['K'], ['_all_'], ['k'] * 9])]:
            for value in values:
                plan = self.plan(); plan['steps'][1]['operations'][0]['args'][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    projection.validate_program(plan)

    def test_portable_boolean_options_require_actual_bool(self):
        for value in [0, 1, 'true', None, []]:
            plan = self.plan(); plan['steps'][1]['operations'][0]['args']['nodupkey'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                projection.validate_program(plan)

    def test_hidden_marker_rejected_in_old_shapes(self):
        for hidden in [{'kind': 'projected_sort'}, {'profile': 'sort-input-keep-v1'}]:
            plan = compile_plan('data x; a=1; output; run;').to_dict()
            plan['steps'][0]['operations'][0]['args']['hidden'] = hidden
            with self.subTest(hidden=hidden), self.assertRaises(ValueError):
                run_plan(plan)

    def test_cyclic_legacy_and_new_portable_containers_refuse(self):
        plan = self.plan(); plan['matched'].append(plan)
        with self.assertRaises(ValueError):
            projection.validate_program(plan)
        legacy = compile_plan('data x; a=1; run;').to_dict()
        legacy['steps'][0]['retained']['cycle'] = legacy
        with self.assertRaises(ValueError):
            run_plan(legacy)

    def test_version_and_initial_catalog_are_strict(self):
        for version in [True, 1, 2.0, 3]:
            plan = self.plan(); plan['version'] = version
            with self.subTest(version=version), self.assertRaises(ValueError):
                projection.validate_program(plan)
        for catalog in [[], {'unrelated': {}}]:
            with self.subTest(catalog=catalog), self.assertRaises(ValueError):
                projection.validate_program(self.plan(), catalog)

    def test_invalid_excluded_values_cannot_hide_behind_keep_or_dedup(self):
        step = self.plan(source(options=' nodupkey'))['steps'][1]
        table = self.table()
        for bad in [True, float('nan'), float('inf'), {'missing': 'A'}, 0.1, 1e-20, 2147483648]:
            altered = deepcopy(table); altered['rows'][-1]['discarded'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                projection.execute_sort(step, {'raw': altered})

    def test_invalid_excluded_descriptors_validate_even_empty(self):
        step = self.plan(source(''))['steps'][1]
        for change in [lambda t: t['schema']['discarded'].update(length=4),
                       lambda t: t['schema']['discarded'].update(label='excluded'),
                       lambda t: t['schema']['discarded'].update(type='unknown')]:
            table = self.table(); table['rows'] = []; change(table)
            with self.subTest(change=change), self.assertRaises(ValueError):
                projection.execute_sort(step, {'raw': table})

    def test_invalid_excluded_row_shape_and_character_validate(self):
        text = producer('a,x,1\nb,y,2', 'label :$2. ignored :$2. k')
        text += 'proc sort data=raw(keep=label k) out=ordered; by k; run;'
        plan = self.plan(text)
        table = run_plan(compile_plan(producer('a,x,1\nb,y,2', 'label :$2. ignored :$2. k')).to_dict())['datasets']['raw']
        for change in [lambda t: t['rows'][0].pop('ignored'),
                       lambda t: t['rows'][0].update(ignored='x'),
                       lambda t: t['rows'][0].update(ignored='é '),
                       lambda t: t['rows'][0].update(extra=1)]:
            altered = deepcopy(table); change(altered)
            with self.subTest(change=change), self.assertRaises(ValueError):
                projection.execute_sort(plan['steps'][1], {'raw': altered})

    def test_unused_producer_cannot_hide_invalid_excluded_data(self):
        text = source() + producer('x,1,2,0.1', name='unused')
        self.blocked(text)
        plan = self.plan(source() + producer(name='unused'))
        plan['steps'][-1]['operations'][0]['args']['records'][-1] = 'x,1,2,0.1'
        with self.assertRaises(ValueError):
            projection.validate_program(plan)

    def test_selected_thirty_two_columns_and_eight_keys_boundaries(self):
        columns = 'c :$1. ' + ' '.join('n' + str(index) for index in range(31))
        names = ['c'] + ['n' + str(index) for index in range(31)]
        text = producer('x,' + ','.join('1' for _ in range(31)), columns)
        header = 'proc sort data=raw(keep=' + ' '.join(reversed(names)) + ') out=ordered; by '
        valid = text + header + ' '.join(names[:8]) + '; run;'
        table = run_plan(self.plan(valid))['datasets']['ordered']
        self.assertEqual(list(table['schema']), names)
        self.blocked(text + header + ' '.join(names[:9]) + '; run;')

    def test_row_step_and_report_limits_remain(self):
        plan = self.plan(); table = self.table(); table['rows'] = [table['rows'][0]] * 1001
        with self.assertRaises(ValueError):
            projection.execute_sort(plan['steps'][1], {'raw': table})
        plan['steps'].extend([plan['steps'][0]] * 64)
        with self.assertRaises(ValueError):
            projection.validate_program(plan)
        self.blocked(source(tail='proc print data=ordered; run;' * 3))
        self.blocked(source(tail='title "x";' * 33))

    def test_late_fractional_print_after_first_sort_and_report(self):
        text = (producer('a,0.5,1,11\nb,1,2,22')
                + 'proc sort data=raw(keep=label id) out=first; by id; run;\n'
                + 'proc print data=first; run;\n'
                + 'proc sort data=raw(keep=label k id) out=second; by k; run;\n'
                + 'proc print data=second; run;')
        plan = self.plan(text); before = deepcopy(plan); trace = []
        with self.assertRaises(ValueError):
            projection.run_program(plan, trace=trace)
        self.assertEqual(plan, before)
        self.assertEqual(len([event for event in trace if isinstance(event, dict) and event.get('event') == 'sort']), 2)
        self.assertTrue(any(isinstance(event, str) and event.startswith('mixed-print|output|print_01.txt|') for event in trace))

    def test_injected_late_sort_after_buffered_report_returns_no_result(self):
        text = source(tail='proc print data=ordered; run; proc sort data=ordered(keep=label id) out=last; by id; run;')
        plan = self.plan(text); real = projection.execute_sort; calls = []
        def fail_second(step, tables, version=2, *, trace=None):
            calls.append(step['name'])
            if len(calls) == 2:
                raise ValueError('injected late projected SORT failure')
            return real(step, tables, version, trace=trace)
        trace = []
        with patch.object(projection, 'execute_sort', fail_second), self.assertRaisesRegex(ValueError, 'late projected SORT'):
            projection.run_program(plan, trace=trace)
        self.assertEqual(calls, ['ordered', 'last'])
        self.assertTrue(any(isinstance(event, str) and event.startswith('mixed-print|output|') for event in trace))

    def test_legacy_sort_within_new_family_preserves_earlier_profile(self):
        text = producer() + 'proc sort data=raw out=old; by label; run;\n'
        text += 'proc sort data=old(keep=label k) out=last nodupkey; by label; run;'
        plan = self.plan(text)
        self.assertEqual(plan['steps'][1]['kind'], 'sort')
        self.assertEqual(plan['steps'][1]['operations'], [])
        result = run_plan(plan)
        self.assertEqual(list(result['datasets']['last']['schema']), ['label', 'k'])

    def test_legacy_source_sort_cannot_replace_prior_tables_in_keep_family(self):
        # The KEEP family preserves every source table, including at legacy joins.
        for records in ['', 'b,2,1,11\na,1,2,22\nc,2,3,33']:
            for header in ['proc sort data=ordered out=raw;',
                           'proc sort data=ordered out=ordered;',
                           'proc sort data=ordered;']:
                with self.subTest(empty=not records, header=header):
                    self.blocked(source(records, tail=header + ' by id; run;'))

    def test_legacy_portable_and_direct_sort_collisions_refuse_before_execution(self):
        text = source(tail='proc sort data=ordered out=last; by id; run;')
        plan = self.plan(text)
        tables = run_plan(self.plan())['datasets']
        fresh = projection.execute_sort(plan['steps'][-1], tables)
        self.assertEqual([row['id'] for row in fresh['rows']], [1, 2, 3])
        before = deepcopy(tables)
        for destination in ['raw', 'ordered']:
            changed = deepcopy(plan); changed['steps'][-1]['name'] = destination
            with self.subTest(destination=destination):
                with self.assertRaises(ValueError):
                    projection.validate_program(changed)
                with self.assertRaises(ValueError):
                    projection.execute_sort(changed['steps'][-1], tables)
                self.assertEqual(tables, before)

    def test_old_standalone_legacy_replacement_remains_supported(self):
        for header in ['proc sort data=raw;', 'proc sort data=raw out=raw;']:
            text = producer() + header + ' by id; run;'
            plan = compile_plan(text)
            self.assertFalse(plan.blocked, plan.tickets)
            self.assertEqual([step.kind for step in plan.steps], ['character_data', 'sort'])
            table = run_plan(plan.to_dict())['datasets']['raw']
            self.assertEqual(list(table['schema']), ['label', 'k', 'id', 'discarded'])
            self.assertEqual([row['id'] for row in table['rows']], [1, 2, 3])

    def test_direct_execute_requires_its_kind_and_version(self):
        step = self.plan()['steps'][1]; table = self.table()
        changed = deepcopy(step); changed['kind'] = 'data'
        with self.assertRaises(ValueError):
            projection.execute_sort(changed, {'raw': table})
        with self.assertRaises(ValueError):
            projection.execute_sort(step, {'raw': table}, version=True)


if __name__ == '__main__':
    unittest.main()
