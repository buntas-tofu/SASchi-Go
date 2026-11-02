"""Source, portable boundary and execution checks for additive SORT options."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from .emit_py import translate
from .plan import compile_plan, _compile_before_sort_options
from .runtime import run_plan
from . import sort_options as sorts


def producer(records='b,1,1\na,2,2\nc,2,3', columns='label :$2. k id', name='raw'):
    return ('data ' + name + ';\ninfile datalines dsd;\ninput ' + columns
            + ';\ndatalines4;\n' + (records + '\n' if records else '') + ';;;;\nrun;\n')


def source(records='b,1,1\na,2,2\nc,2,3', by='descending k', options='', tail=''):
    return (producer(records) + 'proc sort data=raw out=ordered' + options
            + ';\nby ' + by + ';\nrun;\n' + tail)


class SortOptionsTests(unittest.TestCase):
    def plan(self, text=None):
        parsed = compile_plan(source() if text is None else text)
        self.assertFalse(parsed.blocked, parsed.tickets)
        return parsed.to_dict()

    def blocked(self, text):
        self.assertTrue(compile_plan(text).blocked)

    def test_mixed_direction_stable_ties(self):
        result = run_plan(self.plan(source('a,1,1\na,3,2\nb,9,3\na,3,4', 'label descending k')))
        self.assertEqual([r['id'] for r in result['datasets']['ordered']['rows']], [2, 4, 1, 3])

    def test_ordinary_missing_direction_reversal(self):
        result = run_plan(self.plan(source('a,,1\nb,-1,2\nc,2,3\nd,2,4')))
        self.assertEqual([r['id'] for r in result['datasets']['ordered']['rows']], [3, 4, 2, 1])

    def test_character_descending_ascii_and_padding(self):
        result = run_plan(self.plan(source('a,1,1\nB,2,2\n,3,3\na,4,4', 'descending label')))
        self.assertEqual([r['id'] for r in result['datasets']['ordered']['rows']], [1, 4, 2, 3])
        self.assertEqual(result['datasets']['ordered']['rows'][0]['label'], 'a ')

    def test_descriptor_order_differs_from_alphabetical(self):
        text = producer('a,2\nb,1\na,2', 'z :$2. a') + 'proc sort data=raw out=ordered nodupkey; by _all_; run;'
        result = run_plan(self.plan(text))
        table = result['datasets']['ordered']
        self.assertEqual(list(table['schema']), ['z', 'a'])
        self.assertEqual(table['rows'], [{'z': 'a ', 'a': 2.0}, {'z': 'b ', 'a': 1.0}])

    def test_descending_then_existing_nodupkey_survivors(self):
        tail = 'proc sort data=ordered out=unique_rows nodupkey; by label; run;'
        p = self.plan(source('a,1,1\na,3,2\na,3,3\nb,2,4', 'label descending k', tail=tail))
        result = run_plan(p)
        self.assertEqual([r['id'] for r in result['datasets']['unique_rows']['rows']], [2, 4])
        self.assertEqual(len(result['datasets']['raw']['rows']), 4)

    def test_exact_fraction_sort_without_print(self):
        result = run_plan(self.plan(source('a,0.5,1\nb,-0.25,2\nc,0.5,3')))
        self.assertEqual([r['id'] for r in result['datasets']['ordered']['rows']], [1, 3, 2])

    def test_empty_valid_table(self):
        result = run_plan(self.plan(source('')))
        self.assertEqual(result['datasets']['ordered']['rows'], [])
        self.assertEqual(list(result['datasets']['ordered']['schema']), ['label', 'k', 'id'])

    def test_reports_are_immutable_snapshots(self):
        text = (producer() + 'title "before"; proc print data=raw; run;\n'
                + 'proc sort data=raw out=ordered; by descending k; run;\n'
                + 'title "after"; proc print data=ordered; run; title;')
        result = run_plan(self.plan(text))
        self.assertIn('1 "b" 1 1\n', result['reports']['print_01.txt'])
        self.assertIn('1 "a" 2 2\n', result['reports']['print_02.txt'])
        self.assertTrue(result['reports']['print_01.txt'].startswith('TITLE: before\n'))

    def test_sort_trace_observes_exactly_actual_steps(self):
        p = self.plan(source(tail='proc sort data=ordered out=unique_rows nodupkey; by k; run;'))
        trace = []
        with patch.object(sorts, 'execute_sort', wraps=sorts.execute_sort) as execute:
            sorts.run_program(p, trace=trace)
            self.assertEqual(execute.call_count, 2)
        events = [event for event in trace if isinstance(event, dict) and event.get('event') == 'sort']
        self.assertEqual([event['source_ordinals'] for event in events], [[2, 3, 1], [3, 1, 2]])
        self.assertEqual(events[1]['kept_ordinals'], [3, 1])

    def test_preflight_executes_no_sort_engine(self):
        p = self.plan()
        with patch.object(sorts, 'execute_sort', side_effect=AssertionError('must not execute')):
            self.assertIsNotNone(sorts.validate_program(p))

    def test_runtime_and_emitted_results_agree(self):
        text = source(tail='proc print data=ordered; run;')
        emitted = translate(text)
        self.assertFalse(emitted.blocked)
        namespace = {}
        exec(emitted.code, namespace)
        self.assertEqual(namespace['result'], run_plan(emitted.plan))

    def test_legacy_plans_unchanged(self):
        for text in [producer(), producer() + 'proc sort data=raw out=ordered nodupkey; by k; run;',
                     'data x; a=1; output; run;', 'proc sort data=x out=y; by descending k; run;']:
            with self.subTest(text=text):
                self.assertEqual(compile_plan(text).to_dict(), _compile_before_sort_options(text).to_dict())

    def test_matched_applications_retain_source_order_with_legacy_sort(self):
        text = (producer() + 'proc sort data=raw out=first; by k; run;\n'
                + 'proc sort data=first out=last; by descending k; run;')
        p = self.plan(text)
        self.assertEqual([match[2] for match in p['matched']], sorted(match[2] for match in p['matched']))
        self.assertEqual(sum(match[0] == 'sort' for match in p['matched']), 1)
        self.assertEqual(sum(match[0] == 'directed-sort' for match in p['matched']), 3)

    def test_numeric_only_descending_source_still_refuses(self):
        self.blocked('data raw; input k; datalines;\n1\n;\nrun; proc sort data=raw out=ordered; by descending k; run;')

    def test_literals_comments_and_opaque_payload_do_not_select(self):
        text = producer('by descending,1,1', 'label :$20. k id') + 'title "by _all_"; proc print data=raw; run; /* by descending k */'
        self.assertEqual(compile_plan(text).to_dict(), _compile_before_sort_options(text).to_dict())
        self.assertNotIn(sorts.KIND, [step.kind for step in compile_plan(text).steps])

    def test_new_sort_requires_prior_genuine_producer(self):
        self.blocked('proc sort data=raw out=ordered; by descending k; run;' + producer())
        self.blocked(source().replace('label :$2.', 'label'))

    def test_fresh_destination_even_empty(self):
        self.blocked(source('').replace('out=ordered', 'out=raw'))
        self.blocked(source('').replace('out=ordered', ''))
        self.blocked(source('') + 'proc sort data=raw out=ordered; by descending k; run;')

    def test_source_direction_grammar_refusals(self):
        for by in ['k descending', 'descending descending k', 'descending k k',
                   'descending _all_', '_all_ k', '_all_ _all_', 'descending absent',
                   'descending k notsorted', 'descending k missing']:
            with self.subTest(by=by):
                self.blocked(source(by=by))

    def test_source_header_options_refuse(self):
        for option in [' noequalS', ' dupout=removed', ' sortseq=linguistic', ' noduprecs', ' nodup', ' equals']:
            with self.subTest(option=option):
                self.blocked(source(options=option))
        self.blocked(source().replace('data=raw', 'data=raw(keep=k)'))

    def test_all_requires_nodupkey_and_sole_special_list(self):
        self.blocked(source(by='_all_'))
        self.blocked(source(by='_all_ label', options=' nodupkey'))

    def test_semicolon_and_statement_consumption(self):
        for text in [source()[:-2], source().replace('by descending k;', 'by descending k'),
                     source().replace('run;\n', 'output; run;\n', 1),
                     source() + 'unknown;']:
            with self.subTest(text=text):
                self.blocked(text)

    def test_portable_shape_and_provenance_refusals(self):
        for change in [lambda s: s.update(kind='sort'), lambda s: s.update(by=['k']),
                       lambda s: s.update(nodupkey=True), lambda s: s.update(where={}),
                       lambda s: s.update(retained={'k': 0}), lambda s: s.update(line=True),
                       lambda s: s['operations'][0].update(line=0),
                       lambda s: s['operations'][0]['args'].update(extra=True),
                       lambda s: s['operations'][0]['args'].update(source_lines=[1, 0]),
                       lambda s: s['operations'][0]['args'].update(source_lines=[True, 20])]:
            p = self.plan(); change(p['steps'][1])
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                sorts.validate_program(p)

    def test_portable_key_refusals(self):
        for keys in [[], [{'name': 'k', 'descending': False}], [{'name': 'k', 'descending': 1}],
                     [{'name': 'K', 'descending': True}], [{'name': 'absent', 'descending': True}],
                     [{'name': 'k', 'descending': True}, {'name': 'k', 'descending': False}],
                     [{'name': 'k', 'descending': True, 'extra': 0}]]:
            p = self.plan(); p['steps'][1]['operations'][0]['args']['keys'] = keys
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                sorts.validate_program(p)

    def test_hidden_operations_and_profiles_refuse_in_legacy(self):
        for hidden in [{'kind': sorts.KIND}, {'profile': sorts.DIRECTED_PROFILE}, {'profile': sorts.ALL_PROFILE}]:
            p = compile_plan('data x; a=1; output; run;').to_dict()
            p['steps'][0]['operations'][0]['args']['hidden'] = hidden
            with self.subTest(hidden=hidden), self.assertRaises(ValueError):
                run_plan(p)

    def test_cyclic_portable_containers_refuse(self):
        p = self.plan(); p['matched'].append(p)
        with self.assertRaises(ValueError):
            sorts.validate_program(p)
        legacy = compile_plan('data x; a=1; run;').to_dict()
        legacy['steps'][0]['retained']['cycle'] = legacy
        with self.assertRaises(ValueError):
            run_plan(legacy)

    def test_portable_requires_exact_version_and_empty_catalog(self):
        for version in [True, 1, 2.0, 3]:
            p = self.plan(); p['version'] = version
            with self.subTest(version=version), self.assertRaises(ValueError):
                sorts.validate_program(p)
        for catalog in [[], {'unrelated': {}}]:
            with self.subTest(catalog=catalog), self.assertRaises(ValueError):
                sorts.validate_program(self.plan(), catalog)

    def test_empty_table_still_validates_descriptor_and_key(self):
        p = self.plan(source('')); step = p['steps'][1]
        schema = {'label': {'type': 'character', 'length': 2}, 'k': {'type': 'number', 'length': 8}}
        for change in [lambda s: s['k'].update(length=4), lambda s: s['label'].update(label='x'),
                       lambda s: s.pop('k')]:
            table = {'schema': deepcopy(schema), 'rows': []}; change(table['schema'])
            with self.subTest(change=change), self.assertRaises(ValueError):
                sorts.execute_sort(step, {'raw': table})

    def test_invalid_rows_validate_even_if_dedup_would_discard(self):
        p = self.plan(source(options=' nodupkey'))
        table = sorts.run_program(self.plan())['datasets']['raw']
        for bad in [True, float('nan'), float('inf'), {'missing': 'A'}, 0.1, 1e-20, 2147483648]:
            altered = deepcopy(table); altered['rows'][1]['id'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                sorts.execute_sort(p['steps'][1], {'raw': altered})

    def test_table_row_and_character_shapes(self):
        table = sorts.run_program(self.plan())['datasets']['raw']
        for change in [lambda t: t['rows'][0].pop('id'), lambda t: t['rows'][0].update(label='a'),
                       lambda t: t['rows'][0].update(label='é '), lambda t: t.update(label='extra')]:
            altered = deepcopy(table); change(altered)
            with self.subTest(change=change), self.assertRaises(ValueError):
                sorts.execute_sort(self.plan()['steps'][1], {'raw': altered})

    def test_resource_row_and_step_bounds(self):
        p = self.plan(); table = sorts.run_program(p)['datasets']['raw']
        table['rows'] = [table['rows'][0]] * 1001
        with self.assertRaises(ValueError):
            sorts.execute_sort(p['steps'][1], {'raw': table})
        p['steps'].extend([p['steps'][0]] * 64)
        with self.assertRaises(ValueError):
            sorts.validate_program(p)

    def test_report_and_title_caps_remain(self):
        self.blocked(source(tail='proc print data=raw; run;' * 3))
        self.blocked(source(tail='title "x";' * 33))

    def test_late_actual_print_failure_after_sorts_keeps_private_state(self):
        text = source('a,0.5,1\nb,1,2', tail='proc sort data=ordered out=unique_rows nodupkey; by label; run; proc print data=unique_rows; run;')
        p = self.plan(text)
        before = deepcopy(p)
        trace = []
        with self.assertRaises(ValueError):
            sorts.run_program(p, trace=trace)
        self.assertEqual(p, before)
        self.assertEqual(len([event for event in trace if isinstance(event, dict) and event.get('event') == 'sort']), 2)

    def test_injected_late_sort_failure_after_report_returns_no_result(self):
        p = self.plan(source(tail='proc print data=ordered; run; proc sort data=ordered out=last; by descending id; run;'))
        real = sorts.execute_sort
        calls = []
        def fail_second(step, tables, version=2, *, trace=None):
            calls.append(step['name'])
            if len(calls) == 2:
                raise ValueError('injected late SORT failure')
            return real(step, tables, version, trace=trace)
        trace = []
        with patch.object(sorts, 'execute_sort', fail_second), self.assertRaisesRegex(ValueError, 'late SORT'):
            sorts.run_program(p, trace=trace)
        self.assertTrue(any(isinstance(event, str) and event.startswith('mixed-print|output|') for event in trace))
        self.assertEqual(calls, ['ordered', 'last'])

    def test_direct_execute_rejects_wrong_kind_and_version(self):
        p = self.plan(); table = sorts.run_program(p)['datasets']['raw']
        step = deepcopy(p['steps'][1]); step['kind'] = 'data'
        with self.assertRaises(ValueError):
            sorts.execute_sort(step, {'raw': table})
        with self.assertRaises(ValueError):
            sorts.execute_sort(p['steps'][1], {'raw': table}, version=True)


if __name__ == '__main__':
    unittest.main()
