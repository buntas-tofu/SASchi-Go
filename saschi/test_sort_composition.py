"""Source, portable, execution and publication boundaries for SORT composition."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from .plan import compile_plan
from .runtime import run_plan
from .emit_py import translate
from .emit_cpp import translate as cpp_translate
from .job import build_job
from . import sort_composition as composition
from . import sort_projection, sort_options

ROOT = Path(__file__).resolve().parents[1]
CARDS = 'b,2,1,11\na,1,2,22\nc,2,3,33\nb,.,4,44\nb,2,5,55\n,-1,6,66'
SCHEMA = {'label': {'type': 'character', 'length': 2},
          'k': {'type': 'number', 'length': 8}, 'id': {'type': 'number', 'length': 8},
          'junk': {'type': 'number', 'length': 8}}
RAW_ROWS = [{'label': 'b ', 'k': 2.0, 'id': 1.0, 'junk': 11.0},
            {'label': 'a ', 'k': 1.0, 'id': 2.0, 'junk': 22.0},
            {'label': 'c ', 'k': 2.0, 'id': 3.0, 'junk': 33.0},
            {'label': 'b ', 'k': None, 'id': 4.0, 'junk': 44.0},
            {'label': 'b ', 'k': 2.0, 'id': 5.0, 'junk': 55.0},
            {'label': '  ', 'k': -1.0, 'id': 6.0, 'junk': 66.0}]


def producer(records=CARDS, columns='label :$2. k id junk', name='raw'):
    return ('data ' + name + ';\ninfile datalines dsd;\ninput ' + columns + ';\ndatalines4;\n'
            + (records + '\n' if records else '') + ';;;;\nrun;\n')


def source(records=CARDS, *, mode='drop', names='junk', by='k', options='', tail=''):
    return (producer(records) + 'proc sort data=raw(' + mode + '=' + names + ') out=ordered'
            + options + ';\nby ' + by + ';\nrun;\n' + tail)


def plan(text=None):
    parsed = compile_plan(source() if text is None else text)
    if parsed.blocked:
        raise AssertionError([(ticket.line, ticket.reason) for ticket in parsed.tickets])
    return parsed.to_dict()


def table(rows=None):
    return {'schema': deepcopy(SCHEMA), 'rows': deepcopy(RAW_ROWS if rows is None else rows)}


def expected_table(ordinals, columns=('label', 'k', 'id'), rows=RAW_ROWS):
    # Literal ordinal arrays in each test are hand expectations, never runtime output.
    return {'schema': {name: deepcopy(SCHEMA[name]) for name in columns},
            'rows': [{name: deepcopy(rows[i - 1][name]) for name in columns} for i in ordinals]}


class SortCompositionTests(unittest.TestCase):
    def blocked(self, text):
        parsed = compile_plan(text)
        self.assertTrue(parsed.blocked, text)

    def test_ascending_drop_has_exact_independent_result_and_preserves_source(self):
        actual = run_plan(plan())
        self.assertEqual(actual, {'datasets': {'raw': table(),
                         'ordered': expected_table([4, 6, 2, 1, 3, 5])}, 'log': []})

    def test_reversed_keep_list_preserves_descriptor_order_with_direction(self):
        result = run_plan(plan(source(mode='keep', names='id label k', by='descending k label')))
        self.assertEqual(result['datasets']['ordered'], expected_table([1, 5, 3, 2, 6, 4]))
        self.assertEqual(list(result['datasets']['ordered']['schema']), ['label', 'k', 'id'])

    def test_drop_list_order_does_not_change_selected_descriptor_order(self):
        base = producer('b,2,1,11,x\na,1,2,22,y', 'label :$2. k id junk ignored :$2.')
        for names in ['ignored junk', 'junk ignored']:
            with self.subTest(names=names):
                value = plan(base + 'proc sort data=raw(drop=' + names + ') out=ordered;by k;run;')
                self.assertEqual(run_plan(value)['datasets']['ordered'], expected_table([2, 1], rows=RAW_ROWS[:2]))

    def test_descending_applies_only_to_its_next_key(self):
        value = run_plan(plan(source(by='label descending k id')))
        self.assertEqual(value['datasets']['ordered'], expected_table([6, 2, 1, 5, 4, 3]))

    def test_multiple_descending_keys_and_missing_reverse(self):
        value = run_plan(plan(source(by='descending label descending k')))
        self.assertEqual(value['datasets']['ordered'], expected_table([3, 1, 5, 4, 2, 6]))

    def test_nodupkey_uses_selected_keys_not_payload_or_last_row(self):
        value = run_plan(plan(source(mode='keep', names='id label k', by='descending k label', options=' nodupkey')))
        self.assertEqual(value['datasets']['ordered'], expected_table([1, 3, 2, 6, 4]))

    def test_equal_payload_ties_have_distinct_stable_row_identities(self):
        value = plan(source('A,2,7,8\nA,2,7,8\nA,2,7,8', by='descending k', options=' nodupkey'))
        trace = []; result = composition.run_program(value, trace=trace)
        event, = [item for item in trace if isinstance(item, dict) and item.get('event') in ('sort', 'sort_composition')]
        self.assertEqual(event['source_ordinals'], [1, 2, 3])
        self.assertEqual(event['kept_ordinals'], [1])
        self.assertEqual(len(result['datasets']['ordered']['rows']), 1)

    def test_exact_trace_binds_selection_keys_order_and_original_ordinals(self):
        value = plan(); trace = []; composition.run_program(value, trace=trace)
        event, = [item for item in trace if isinstance(item, dict) and item.get('event') in ('sort', 'sort_composition')]
        self.assertEqual(event, {'event': 'sort_composition', 'line': 13, 'source': 'raw',
            'destination': 'ordered', 'selection': {'mode': 'drop', 'names': ['junk']},
            'keys': [{'name': 'k', 'descending': False}],
            'source_ordinals': [4, 6, 2, 1, 3, 5], 'kept_ordinals': [4, 6, 2, 1, 3, 5]})

    def test_fractional_sorting_without_print_retains_exact_values(self):
        text = source('a,0.5,1,11\nb,-0.25,2,22\nc,.,3,33', by='descending k')
        rows = run_plan(plan(text))['datasets']['ordered']['rows']
        self.assertEqual([(row['id'], row['k']) for row in rows], [(1, 0.5), (2, -0.25), (3, None)])

    def test_empty_input_preserves_selected_schema_and_checks_removed_keys(self):
        result = run_plan(plan(source('')))
        self.assertEqual(result['datasets']['ordered'], expected_table([], rows=[]))
        for text in [source('', names='k'), source('', mode='keep', names='label id', by='descending k')]:
            with self.subTest(text=text): self.blocked(text)

    def test_projection_precedes_by_resolution_even_on_nonempty_data(self):
        for text in [source(names='k'), source(mode='keep', names='label id', by='descending k')]:
            self.blocked(text)
        value = plan(); value['steps'][1]['operations'][0]['args']['selection']['names'] = ['k']
        with self.assertRaises(ValueError): composition.validate_program(value)

    def test_selected_schema_must_be_nonempty_and_character_bearing(self):
        for records in [CARDS, '']:
            for text in [source(records, names='label'), source(records, names='label k id junk'),
                         source(records, mode='keep', names='k id', by='descending k')]:
                with self.subTest(text=text): self.blocked(text)

    def test_context_and_execution_are_deep_copies(self):
        value = plan(); step = value['steps'][1]; before = deepcopy(value); raw = table(); tables = {'raw': raw}
        context = composition.validate_step(step)
        self.assertEqual(context, step['operations'][0]['args'])
        context['selection']['names'].append('absent'); context['keys'][0]['descending'] = True
        self.assertEqual(value, before)
        trace = []; result = composition.execute_sort(step, tables, trace=trace)
        result['schema']['label']['length'] = 64; result['rows'][0]['label'] = 'changed'
        trace[0]['selection']['names'].append('absent'); trace[0]['keys'][0]['name'] = 'absent'
        self.assertEqual(tables, {'raw': table()}); self.assertEqual(value, before)

    def test_preflight_never_executes_any_admitted_sort_primitive(self):
        value = plan(self.joined_source())
        with patch.object(composition, 'execute_sort', side_effect=AssertionError('preflight sorted')), \
             patch.object(sort_options, 'execute_sort', side_effect=AssertionError('preflight directed sorted')), \
             patch.object(sort_projection, 'execute_sort', side_effect=AssertionError('preflight KEEP sorted')):
            self.assertIsNotNone(composition.validate_program(value))

    def test_each_actual_sort_runs_once_and_plans_catalogs_remain_immutable(self):
        value = plan(self.joined_source()); before = deepcopy(value); catalog = {}; trace = []
        with patch.object(composition, 'execute_sort', wraps=composition.execute_sort) as execute:
            result = composition.run_program(value, catalog, trace=trace)
        self.assertEqual(execute.call_count, 4); self.assertEqual(value, before); self.assertEqual(catalog, {})
        self.assertEqual([row['id'] for row in result['datasets']['last']['rows']], [6, 5, 4, 3, 2, 1])
        events = [item for item in trace if isinstance(item, dict) and item.get('event') in ('sort', 'sort_composition')]
        self.assertEqual([event['event'] for event in events], ['sort', 'sort', 'sort', 'sort_composition'])
        for event in events[:3]:
            self.assertEqual(set(event), {'event', 'line', 'source', 'destination', 'source_ordinals', 'kept_ordinals'})
        self.assertEqual(events[0]['source_ordinals'], [1, 2, 3, 4, 5, 6])
        self.assertEqual(events[1]['source_ordinals'], [6, 5, 4, 3, 2, 1])
        self.assertEqual(events[2]['source_ordinals'], [6, 5, 4, 3, 2, 1])

    @staticmethod
    def joined_source():
        return (producer() + 'proc sort data=raw out=plain;by id;run;\n'
            + 'proc sort data=plain out=directed;by descending id;run;\n'
            + 'proc sort data=directed(keep=id label k) out=oldkeep;by id;run;\n'
            + 'proc sort data=oldkeep(drop=k) out=last;by descending id;run;')

    def test_old_ascending_keep_has_unchanged_kind_shape_and_is_not_owned_alone(self):
        value = plan(source(mode='keep', names='label k id'))
        self.assertEqual(value['steps'][1]['kind'], 'projected_sort')
        self.assertEqual(value['steps'][1]['operations'][0]['args'], {
            'profile': 'sort-input-keep-v1', 'keep': ['label', 'k', 'id'], 'by': ['k'],
            'nodupkey': False, 'source_lines': [14, 15]})
        self.assertIsNone(composition.validate_program(value))
        self.assertEqual([s['kind'] for s in plan(self.joined_source())['steps']],
                         ['character_data', 'sort', 'bounded_sort', 'projected_sort', 'composed_sort'])

    def test_source_decoys_in_comments_titles_and_opaque_cards_do_not_select(self):
        text = producer('DROP=junk,1,2,3', 'label :$20. k id junk')
        text += 'title "KEEP=label DESCENDING k";proc print data=raw;run;'
        text += '/* proc sort data=raw(drop=junk) out=decoy;by descending k;run; */'
        parsed = compile_plan(text); self.assertFalse(parsed.blocked, parsed.tickets)
        self.assertNotIn('composed_sort', [step.kind for step in parsed.steps])
        self.assertIsNone(composition.validate_program(parsed.to_dict()))

    def test_genuine_prior_character_producer_and_empty_catalog_are_required(self):
        suffix = 'proc sort data=raw(drop=junk) out=ordered;by k;run;'
        self.blocked(suffix + producer())
        self.blocked('data raw;label=1;k=1;junk=1;output;run;' + suffix)
        self.blocked(source().replace('label :$2.', 'label'))
        for catalog in [[], {'supplied': table()}]:
            with self.subTest(catalog=catalog), self.assertRaises(ValueError):
                composition.validate_program(plan(), catalog)

    def test_valid_literal_headers_are_not_function_calls_even_for_function_dataset_name(self):
        for mode, names, by in [('drop', 'junk', 'k'), ('keep', 'id label k', 'descending k')]:
            text = producer(name='ROUND') + 'proc sort data=ROUND(' + mode + '=' + names + ') out=ordered;by ' + by + ';run;'
            job = build_job(text); self.assertEqual(job.code, 0)
            self.assertEqual(job.receipt['completeness']['n_functions'], 0)
            self.assertEqual(job.receipt['completeness']['n_matched'], 0)

    def test_invalid_headers_preserve_function_census_and_refusal(self):
        for function, matches in [('f', 0), ('round', 1)]:
            job = build_job(source().replace('(drop=junk)', '(drop=' + function + '(junk))'))
            self.assertEqual(job.code, 2); self.assertTrue(job.plan.blocked)
            self.assertEqual(job.receipt['completeness']['n_functions'], 2)
            self.assertEqual(job.receipt['completeness']['n_matched'], matches)

    def test_unknown_duplicate_empty_special_and_range_selections_refuse(self):
        for mode in ['keep', 'drop']:
            for names in ['', 'junk junk', 'absent', '_all_', '_character_', 'k-id', 'label:']:
                with self.subTest(mode=mode, names=names):
                    self.blocked(source(mode=mode, names=names, by='descending k'))

    def test_unsupported_headers_family_joins_and_steps_refuse(self):
        for text in [source().replace('(drop=junk)', '(drop=junk keep=label k)'),
                     source().replace('out=ordered', 'out=ordered(keep=label)'),
                     source(options=' dupout=removed nodupkey'), source(options=' noduprecs'),
                     source(options=' noequals'), source(options=' sortseq=linguistic'),
                     source(by='_all_', options=' nodupkey'),
                     source() + 'proc sort data=raw out=allrows nodupkey;by _all_;run;',
                     source() + 'proc sort data=ordered dupout=removed nodupkey;by label;run;',
                     source() + 'proc means data=ordered;run;', source() + 'unknown;']:
            with self.subTest(text=text): self.blocked(text)

    def test_fresh_destinations_and_sources_are_checked_even_when_empty(self):
        for records in [CARDS, '']:
            for text in [source(records).replace('out=ordered', 'out=raw'),
                         source(records).replace('out=ordered', ''),
                         source(records) + 'proc sort data=raw(drop=junk) out=ordered;by k;run;',
                         source(records) + 'proc sort data=ordered;by id;run;',
                         source(records) + 'proc sort data=ordered out=raw;by id;run;']:
                with self.subTest(text=text): self.blocked(text)
        step = plan()['steps'][1]; before = {'raw': table(), 'ordered': table()}
        with self.assertRaises(ValueError): composition.execute_sort(step, before)
        self.assertEqual(before, {'raw': table(), 'ordered': table()})
        with self.assertRaises(ValueError): composition.execute_sort(step, {'absent': table()})

    def test_bad_by_lists_and_exact_statement_consumption_refuse(self):
        for by in ['', 'k k', 'absent', 'descending', 'k notsorted', 'k-id', '_all_']:
            with self.subTest(by=by): self.blocked(source(by=by))
        for text in [source()[:-2], source().replace('by k;', 'by k'),
                     source().replace('by k;', 'by k;output;')]: self.blocked(text)

    def test_step_defaults_operation_identity_and_provenance_are_exact(self):
        changes = [lambda s: s.update(kind='sort'), lambda s: s.update(by=['k']),
            lambda s: s.update(nodupkey=True), lambda s: s.update(nodupkey=0), lambda s: s.update(where={}),
            lambda s: s.update(unexpected=1), lambda s: s.update(lengths=[]),
            lambda s: s.update(retained={'k': 0}), lambda s: s.update(lengths={'label': 2}),
            lambda s: s.update(display_names={'label': 'Label'}), lambda s: s.update(line=True),
            lambda s: s['operations'][0].update(kind='sort'), lambda s: s['operations'][0].update(line=1),
            lambda s: s['operations'][0]['args'].update(extra=True),
            lambda s: s['operations'][0]['args'].update(source_lines=[15, 14]),
            lambda s: s['operations'][0]['args'].update(source_lines=[True, 15]),
            lambda s: s['operations'][0]['args'].update(source_lines=[14.0, 15]),
            lambda s: s['operations'][0]['args'].update(source_lines=[14, 15, 16])]
        for change in changes:
            value = plan(); change(value['steps'][1])
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                composition.validate_program(value)

    def test_portable_selection_shape_and_required_selecting_feature_are_strict(self):
        invalid = [None, [], {}, {'mode': 'DROP', 'names': ['junk']},
            {'mode': 'drop', 'names': []}, {'mode': 'drop', 'names': ['junk', 'junk']},
            {'mode': 'drop', 'names': ['JUNK']}, {'mode': 'drop', 'names': ['absent']},
            {'mode': 'drop', 'names': ['junk'], 'extra': True},
            {'mode': 'drop', 'names': ['n' + str(i) for i in range(33)]},
            {'mode': 'keep', 'names': ['label', 'k', 'id']}]
        for selection in invalid:
            value = plan(); value['steps'][1]['operations'][0]['args']['selection'] = selection
            with self.subTest(selection=selection), self.assertRaises(ValueError): composition.validate_program(value)

    def test_portable_keys_boolean_types_and_nodupkey_are_strict(self):
        invalid = [[], [{'name': 'k', 'descending': 1}], [{'name': 'K', 'descending': False}],
            [{'name': 'k', 'descending': False, 'extra': 1}], [{'name': 'k'}],
            [{'name': 'k', 'descending': False}] * 2, [{'name': 'absent', 'descending': False}],
            [{'name': 'n' + str(i), 'descending': False} for i in range(9)]]
        for keys in invalid:
            value = plan(); value['steps'][1]['operations'][0]['args']['keys'] = keys
            with self.subTest(keys=keys), self.assertRaises(ValueError): composition.validate_program(value)
        for bad in [0, 1, 'true', None, []]:
            value = plan(); value['steps'][1]['operations'][0]['args']['nodupkey'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError): composition.validate_program(value)

    def test_version_kinds_cycles_and_hidden_markers_refuse(self):
        for version in [True, 1, 2.0, 3, None]:
            value = plan(); value['version'] = version
            with self.subTest(version=version), self.assertRaises(ValueError): composition.validate_program(value)
        value = plan(); value['matched'].append(value)
        with self.assertRaises(ValueError): composition.validate_program(value)
        value = plan(); value['steps'][1]['operations'][0]['args']['selection']['names'].append(value)
        with self.assertRaises(ValueError): composition.validate_program(value)
        for hidden in [{'kind': 'composed_sort'}, {'profile': 'sort-projection-composition-v1'}]:
            value = compile_plan('data x;a=1;output;run;').to_dict()
            value['steps'][0]['operations'][0]['args']['hidden'] = hidden
            with self.subTest(hidden=hidden), self.assertRaises(ValueError): run_plan(value)
        step = plan()['steps'][1]; step['kind'] = 'data'
        with self.assertRaises(ValueError): composition.execute_sort(step, {'raw': table()})
        with self.assertRaises(ValueError): composition.validate_step(plan()['steps'][1], version=True)

    def test_invalid_excluded_values_and_descriptors_are_eagerly_validated(self):
        step = plan(source(options=' nodupkey'))['steps'][1]
        for bad in [True, float('nan'), float('inf'), {'missing': 'A'}, 0.1, 1e-20, 2147483648]:
            raw = table(); raw['rows'][4]['junk'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError): composition.execute_sort(step, {'raw': raw})
            with self.subTest(unused_bad=bad), self.assertRaises(ValueError):
                composition.execute_sort(step, {'raw': table(), 'unused': raw})
        for mutate in [lambda t: t['schema']['junk'].update(length=4),
                       lambda t: t['schema']['junk'].update(label='excluded'),
                       lambda t: t['schema']['junk'].update(type='unknown')]:
            raw = table([]); mutate(raw)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): composition.execute_sort(step, {'raw': raw})

    def test_invalid_excluded_character_row_shapes_and_unused_tables_refuse(self):
        text = producer('a,x,1\nb,y,2', 'label :$2. ignored :$2. k')
        text += 'proc sort data=raw(drop=ignored) out=ordered;by k;run;'
        step = plan(text)['steps'][1]
        raw = {'schema': {'label': {'type': 'character', 'length': 2}, 'ignored': {'type': 'character', 'length': 2},
                          'k': {'type': 'number', 'length': 8}},
               'rows': [{'label': 'a ', 'ignored': 'x ', 'k': 1.0}, {'label': 'b ', 'ignored': 'y ', 'k': 2.0}]}
        for mutate in [lambda t: t['rows'][0].pop('ignored'), lambda t: t['rows'][0].update(ignored='x'),
                       lambda t: t['rows'][0].update(ignored='é '), lambda t: t['rows'][0].update(extra=1)]:
            bad = deepcopy(raw); mutate(bad)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): composition.execute_sort(step, {'raw': bad})
        self.blocked(source() + producer('x,1,2,0.1', name='unused'))
        value = plan(source() + producer(name='unused'))
        value['steps'][-1]['operations'][0]['args']['records'][-1] = 'x,1,2,0.1'
        with self.assertRaises(ValueError): composition.validate_program(value)

    def test_maximum_columns_and_eight_keys_keep_descriptor_order(self):
        names = ['c'] + ['n' + str(i) for i in range(31)]
        base = producer('x,' + ','.join('1' for _ in range(31)), 'c :$1. ' + ' '.join(names[1:]))
        header = 'proc sort data=raw(keep=' + ' '.join(reversed(names)) + ') out=ordered;by descending '
        text = base + header + ' '.join(names[:8]) + ';run;'
        result = run_plan(plan(text))['datasets']['ordered']
        self.assertEqual(list(result['schema']), names); self.assertEqual(len(result['rows']), 1)
        self.blocked(base + header + ' '.join(names[:9]) + ';run;')
        self.blocked(producer('x,1', 'label :$65. k') + 'proc sort data=raw(drop=k) out=ordered;by label;run;')

    def test_row_step_title_and_report_limits_preserve_old_caps(self):
        step = plan()['steps'][1]; raw = table([RAW_ROWS[0]] * 1000)
        self.assertEqual(len(composition.execute_sort(step, {'raw': raw})['rows']), 1000)
        raw['rows'].append(deepcopy(RAW_ROWS[0]))
        with self.assertRaises(ValueError): composition.execute_sort(step, {'raw': raw})
        prefix = producer('x,1,1,1')
        sorts = ['proc sort data=raw(drop=junk) out=s' + str(i) + ';by k;run;' for i in range(64)]
        self.assertFalse(compile_plan(prefix + ''.join(sorts[:63])).blocked)
        self.blocked(prefix + ''.join(sorts))
        self.assertFalse(compile_plan(source(tail='title "x";' * 32)).blocked)
        self.blocked(source(tail='title "x";' * 33))
        self.assertFalse(compile_plan(source(tail='proc print data=ordered;run;' * 2)).blocked)
        self.blocked(source(tail='proc print data=ordered;run;' * 3))

    def test_reports_snapshot_schema_and_source_before_later_projection(self):
        text = producer('b,2,1,11\na,1,2,22') + 'title "raw";proc print data=raw;run;\n'
        text += 'proc sort data=raw(drop=junk) out=ordered;by k;run;\ntitle "sorted";proc print data=ordered;run;title;'
        result = run_plan(plan(text))
        self.assertEqual(result['reports'], {
            'print_01.txt': 'TITLE: raw\nobs label k id junk\n1 "b" 2 1 11\n2 "a" 1 2 22\n',
            'print_02.txt': 'TITLE: sorted\nobs label k id\n1 "a" 1 2\n2 "b" 2 1\n'})
        self.assertEqual(result['datasets']['raw'], table(RAW_ROWS[:2]))

    def test_emitted_program_has_independent_exact_result_and_cpp_refuses(self):
        text = source(); emitted = translate(text)
        self.assertFalse(emitted.blocked); namespace = {}; exec(emitted.code, namespace)
        self.assertEqual(namespace['result'], {'datasets': {'raw': table(),
            'ordered': expected_table([4, 6, 2, 1, 3, 5])}, 'log': []})
        self.assertTrue(cpp_translate(text).blocked)

    @staticmethod
    def late_source():
        return (producer('a,0.5,1,11\nb,1,2,22')
            + 'proc sort data=raw(keep=label id) out=first;by descending id;run;\n'
            + 'proc print data=first;run;\n'
            + 'proc sort data=raw(drop=junk) out=second;by descending k;run;\n'
            + 'proc print data=second;run;')

    def test_late_render_failure_follows_actual_sorts_and_buffered_report(self):
        value = plan(self.late_source()); before = deepcopy(value); trace = []
        with patch.object(composition, 'execute_sort', wraps=composition.execute_sort) as execute, self.assertRaises(ValueError):
            composition.run_program(value, trace=trace)
        self.assertEqual(execute.call_count, 2); self.assertEqual(value, before)
        self.assertTrue(any(isinstance(e, str) and e.startswith('mixed-print|output|print_01.txt|') for e in trace))
        job = build_job(self.late_source())
        self.assertFalse(job.plan.blocked); self.assertEqual(job.code, 1); self.assertIsNone(job.result)

    def test_injected_sort_failure_after_buffered_report_has_no_job_result(self):
        text = source(tail='proc print data=ordered;run;proc sort data=ordered(drop=k) out=last;by id;run;')
        real = composition.execute_sort; calls = []
        def fail_second(*args, **kwargs):
            calls.append(args[0]['name'])
            if len(calls) == 2: raise ValueError('injected late SORT')
            return real(*args, **kwargs)
        with patch.object(composition, 'execute_sort', fail_second): job = build_job(text)
        self.assertEqual(calls, ['ordered', 'last']); self.assertEqual(job.code, 1); self.assertIsNone(job.result)

    def test_actual_cli_exact_result_reports_wrong_comparators_and_late_atomicity(self):
        text = source('b,2,1,11\na,1,2,22', tail='title "sorted";proc print data=ordered;run;')
        expected = {'raw': table(RAW_ROWS[:2]), 'ordered': expected_table([2, 1], rows=RAW_ROWS[:2])}
        reports = {'print_01.txt': 'TITLE: sorted\nobs label k id\n1 "a" 1 2\n2 "b" 2 1\n'}
        with tempfile.TemporaryDirectory(prefix='saschi-composition-cli-') as temporary:
            area = Path(temporary); source_path = area / 'source.sas'; source_path.write_text(text)
            data_path = area / 'expected.json'; data_path.write_text(json.dumps(expected))
            reports_path = area / 'reports.json'; reports_path.write_text(json.dumps(reports))
            def run(label, source_file=source_path):
                output = area / label
                result = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'run', str(source_file), '--expect', str(data_path),
                    '--expect-reports', str(reports_path), '--output', str(output)], cwd=ROOT, capture_output=True, timeout=60)
                return result, output, json.loads((output / 'receipt.json').read_text())
            process, output, receipt = run('accepted')
            self.assertEqual(process.returncode, 0, process.stderr.decode())
            self.assertTrue(receipt['accepted']); self.assertEqual(receipt['report_contract'], 'ascii-titled-mixed-integer-v1')
            self.assertEqual(json.loads((output / 'result.json').read_text()), {'datasets': expected, 'log': [], 'reports': reports})
            self.assertEqual((output / 'reports/print_01.txt').read_bytes(), reports['print_01.txt'].encode())
            wrong = deepcopy(expected); wrong['ordered']['rows'].reverse(); data_path.write_text(json.dumps(wrong))
            process, output, receipt = run('wrong-data')
            self.assertEqual(process.returncode, 1); self.assertFalse(receipt['accepted']); self.assertFalse((output / 'reports').exists())
            self.assertEqual(receipt['comparison'], 'failed')
            wrong = deepcopy(expected); wrong['ordered']['schema']['label']['length'] = 3
            for row in wrong['ordered']['rows']: row['label'] = row['label'].ljust(3)
            data_path.write_text(json.dumps(wrong))
            process, output, receipt = run('wrong-schema')
            self.assertEqual(process.returncode, 1); self.assertFalse(receipt['accepted'])
            self.assertEqual(receipt['comparison'], 'failed'); self.assertFalse((output / 'reports').exists())
            data_path.write_text(json.dumps(expected)); reports_path.write_text(json.dumps({'print_01.txt': reports['print_01.txt'].rstrip('\n')}))
            process, output, receipt = run('wrong-report')
            self.assertEqual(process.returncode, 1); self.assertFalse(receipt['accepted']); self.assertFalse((output / 'reports').exists())
            self.assertEqual(receipt['report_comparison'], 'failed')
            source_path.write_text(self.late_source())
            process, output, receipt = run('late')
            self.assertEqual(process.returncode, 1); self.assertFalse(receipt['accepted'])
            for name in ('result.json', 'observed.json', 'reports', 'exports'): self.assertFalse((output / name).exists())


if __name__ == '__main__': unittest.main()
