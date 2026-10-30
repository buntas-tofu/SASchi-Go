"""Projection timing, descriptors, source provenance and hostile portable plans."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from examples.verify_projection import (ORIGINAL, PINS, REFUSALS, original_expected,
                                        program_witness, naive_controls)
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .projection import declaration, name_list, selected_names, project_table
from .runtime import run_plan


def execute(source, catalog=None):
    plan = compile_plan(source)
    if plan.blocked:
        raise AssertionError(plan.tickets)
    return run_plan(plan.to_dict(), catalog)


def catalog(rows=True):
    return {'raw': {'encoding': 'latin-1', 'label': 'original dataset',
                    'schema': {'tag': {'type': 'character', 'length': 4, 'label': 'tag label'},
                               'a': {'type': 'number', 'length': 8, 'format': '8.', 'label': 'amount'},
                               'c': 'number'},
                    'rows': [{'tag': 'é', 'a': 1., 'c': 3.}, {'tag': 'b', 'a': 4., 'c': 6.}] if rows else []}}


class ProjectionTests(unittest.TestCase):
    def test_hand_pins_and_shared_refusals(self):
        for schema, mode, text, expected in PINS:
            self.assertEqual(selected_names(dict.fromkeys(schema, 'number'), declaration(mode + ' ' + text)), expected)
        for schema, mode, text in REFUSALS:
            with self.subTest(text=text), self.assertRaises(ValueError):
                selected_names(dict.fromkeys(schema, 'number'), declaration(mode + ' ' + text))

    def test_source_markers_and_case(self):
        for source, scope, rule, position in (
                ('data d;A=1;b=2;KEEP B;run;', 'statement', 'DS-047', 2),
                ('data d(DROP=B);A=1;b=2;run;', 'output', 'DS-048', 0),
                ('data d;SET RAW(KEEP=A);run;', 'input', 'DS-048', 0)):
            plan = compile_plan(source)
            self.assertFalse(plan.blocked, plan.tickets)
            op = plan.steps[0].operations[position]
            self.assertEqual(op.kind, 'projection')
            self.assertEqual(op.args['scope'], scope)
            self.assertEqual(op.args['names'], ['b'] if scope != 'input' else ['a'])
            self.assertTrue(any(item[1] == rule for item in plan.matched))

    def test_existing_plan_shape_is_unchanged(self):
        plan = compile_plan('data d;x=1;run;').to_dict()
        self.assertEqual(set(plan), {'steps', 'tickets', 'matched', 'version'})
        self.assertEqual(set(plan['steps'][0]), {'kind', 'name', 'line', 'inputs', 'by', 'operations',
                                                'nodupkey', 'where', 'retained', 'lengths', 'display_names'})
        self.assertEqual(plan['steps'][0]['operations'], [
            {'kind': 'assign', 'line': 1, 'args': {'name': 'x', 'value': {'kind': 'number', 'value': 1.}}}])
        plan['version'] = 1
        self.assertEqual(run_plan(plan)['datasets']['d']['rows'], [{'x': 1.}])

    def test_statement_selection_is_declarative_and_preserves_pdv_order(self):
        for statement in ('keep c a;', 'drop b;'):
            for position in range(4):
                body = ['a=1;', 'b=a+1;', 'c=b+1;']
                body.insert(position, statement)
                table = execute('data d;' + ''.join(body) + 'put b=;run;')
                self.assertEqual(table['datasets']['d'], {
                    'schema': {'a': 'number', 'c': 'number'}, 'rows': [{'a': 1., 'c': 3.}]})
                self.assertEqual(table['log'], ['b=2'])

    def test_early_snapshots_use_late_declarations_and_full_schema(self):
        result = execute('data d;a=1;output;if 0 then future=2;a=3;output;keep future a;run;')
        self.assertEqual(result['datasets']['d'], {'schema': {'a': 'number', 'future': 'number'},
                                                'rows': [{'a': 1., 'future': None}, {'a': 3., 'future': None}]})

    def test_skipped_output_still_suppresses_implicit_output(self):
        result = execute('data d;keep a;a=1;if 0 then output;run;')
        self.assertEqual(result['datasets']['d'], {'schema': {'a': 'number'}, 'rows': []})

    def test_output_options_keep_full_computation_and_log(self):
        for option in ('keep=a c', 'drop=b'):
            result = execute(f'data d({option});a=1;b=2;c=a+b;put b=;run;')
            self.assertEqual(result['datasets']['d']['rows'], [{'a': 1., 'c': 3.}])
            self.assertEqual(result['log'], ['b=2'])

    def test_input_projection_precedes_descriptors_and_state(self):
        source = 'data d;set raw(drop=c);before=c;c=7;keep tag a before c;run;'
        result = execute(source, catalog())['datasets']['d']
        self.assertEqual(list(result['schema']), ['tag', 'a', 'before', 'c'])
        self.assertEqual([r['before'] for r in result['rows']], [None, None])
        self.assertEqual([r['c'] for r in result['rows']], [7., 7.])
        self.assertEqual(result['schema']['a'], catalog()['raw']['schema']['a'])

    def test_input_projection_can_remove_character_descriptor_before_new_numeric_use(self):
        result = execute('data d;set raw(drop=tag);tag=7;run;', catalog())['datasets']['d']
        self.assertEqual(result['schema']['tag'], 'number')
        self.assertEqual([r['tag'] for r in result['rows']], [7., 7.])

    def test_input_and_output_choices_compose_independently(self):
        for output in ('data d(keep=z);', 'data d;keep z;'):
            result = execute(output + 'set raw(keep=a c);z=a+c;run;', catalog())['datasets']['d']
            self.assertEqual(result['schema'], {'z': 'number'})
            self.assertEqual(result['rows'], [{'z': 4.}, {'z': 10.}])

    def test_metadata_and_catalog_nonmutation_for_all_timings(self):
        for source in ('data d;set raw;keep a tag;run;', 'data d(keep=a tag);set raw;run;',
                       'data d;set raw(keep=a tag);run;'):
            supplied = catalog()
            before = deepcopy(supplied)
            result = execute(source, supplied)
            self.assertEqual(supplied, before)
            table = result['datasets']['d']
            self.assertEqual(table['encoding'], 'latin-1')
            self.assertEqual(table['label'], 'original dataset')
            self.assertEqual(list(table['schema']), ['tag', 'a'])
            self.assertEqual(table['schema'], {n: supplied['raw']['schema'][n] for n in ('tag', 'a')})
            self.assertEqual(table['rows'][0], {'tag': 'é   ', 'a': 1.})
            self.assertEqual(list(result['datasets']['raw']['schema']), ['tag', 'a', 'c'])

    def test_project_table_copies_descriptors_and_rows(self):
        raw = catalog()['raw']
        selected = project_table(raw, declaration('keep a tag'))
        selected['schema']['tag']['label'] = 'changed'
        selected['rows'][0]['tag'] = 'changed'
        self.assertEqual(raw['schema']['tag']['label'], 'tag label')
        self.assertEqual(raw['rows'][0]['tag'], 'é')

    def test_empty_input_preserves_projected_complete_schema(self):
        for source in ('data d;set raw;keep tag future;if 0 then future=7;run;',
                       'data d(keep=tag future);set raw;if 0 then future=7;run;',
                       'data d;set raw(keep=tag);if 0 then future=7;run;'):
            table = execute(source, catalog(False))['datasets']['d']
            self.assertEqual(list(table['schema']), ['tag', 'future'])
            self.assertEqual(table['rows'], [])

    def test_missing_names_and_empty_selections_refuse_on_empty_input(self):
        for text in ('keep missing', 'drop missing', 'drop tag a c'):
            for source in (f'data d;set raw;{text};run;',
                           f'data d({text.replace(" ", "=", 1)});set raw;run;',
                           f'data d;set raw({text.replace(" ", "=", 1)});run;'):
                for rows in (False, True):
                    with self.subTest(source=source, rows=rows), self.assertRaisesRegex(ValueError, 'projection'):
                        execute(source, catalog(rows))

    def test_input_selection_does_not_hide_invalid_catalog(self):
        for damage in ('descriptor', 'value', 'row', 'metadata'):
            supplied = catalog()
            if damage == 'descriptor': supplied['raw']['schema']['c'] = {'type': 'number', 'length': 4}
            elif damage == 'value': supplied['raw']['rows'][0]['c'] = 'bad'
            elif damage == 'row': supplied['raw']['rows'][0].pop('c')
            else: supplied['raw']['label'] = 123
            with self.subTest(damage=damage), self.assertRaises(ValueError):
                execute('data d;set raw(keep=a);run;', supplied)

    def test_inline_input_first_executable_contract_is_preserved(self):
        source = 'data d;keep b;input a b;datalines;\n1 2\n3 4\n;\nrun;'
        self.assertEqual(execute(source)['datasets']['d'], {
            'schema': {'b': 'number'}, 'rows': [{'b': 2.}, {'b': 4.}]})
        self.assertTrue(compile_plan(source.replace('keep b;', 'keep b;a=1;')).blocked)

    def test_projection_does_not_establish_variable_type_or_order(self):
        table = execute("data d;keep b a;length a $3;a='xy';b=1;run;")['datasets']['d']
        self.assertEqual(list(table['schema']), ['a', 'b'])
        self.assertEqual(table['rows'], [{'a': 'xy ', 'b': 1.}])
        self.assertEqual(execute('data d;keep=1;drop=2;keep keep;run;')['datasets']['d']['rows'], [{'keep': 1.}])

    def test_projection_with_arrays_counted_loops_and_retained_state(self):
        table = execute('data d;keep x1-x3;array a{3} x1-x3;do i=1 to 3;a{i}=i;end;run;')['datasets']['d']
        self.assertEqual(table['rows'], [{'x1': 1., 'x2': 2., 'x3': 3.}])
        table = execute('data d;keep total;retain total 0;set raw;total+c;run;', catalog())['datasets']['d']
        self.assertEqual(table['rows'], [{'total': 3.}, {'total': 9.}])

    def test_output_projection_retains_by_and_where_processing(self):
        supplied = {'raw': {'schema': {'g': 'number', 'x': 'number'},
                            'rows': [{'g': 1., 'x': 1.}, {'g': 1., 'x': 2.}, {'g': 2., 'x': 3.}]}}
        result = execute('data d;set raw;by g;where x>1;first=first.g;last=last.g;drop g;run;', supplied)['datasets']['d']
        self.assertEqual(result['rows'], [{'x': 2., 'first': 1., 'last': 1.}, {'x': 3., 'first': 1., 'last': 1.}])

    def test_all_option_text_is_consumed(self):
        for header in ('data d()', 'data d(keep=a drop=b)', 'data d(keep=a) extra',
                       'data d(keep=a)(drop=b)', 'data d(label="x")', 'data d(obs=1)',
                       'data d(keep=a,b)', 'data d(keep=(a))', 'data d(keep=a rename=(a=b))'):
            self.assertTrue(compile_plan(header + ';a=1;b=2;run;').blocked, header)
        for statement in ('set raw()', 'set raw(keep=a drop=c)', 'set raw(keep=a) other',
                          'set raw(keep=a) nobs=n', 'set raw(keep=a)(drop=c)', 'set raw(rename=(a=b))'):
            self.assertTrue(compile_plan('data d;' + statement + ';run;').blocked, statement)

    def test_input_frontier_and_conflicting_declarations_refuse(self):
        for source in ('data d;set raw(keep=a);by a;run;',
                       'data d;set raw(drop=c);where a>0;run;',
                       'data d;if _n_=1 then set cfg;set raw(keep=a);run;',
                       'data d;merge raw other;keep a;by a;run;',
                       'data d;keep a;drop b;a=1;b=2;run;',
                       'data d;keep a;keep a;a=1;run;',
                       'data d(keep=a);drop b;a=1;b=2;run;',
                       'data d;do i=1 to 0;keep a;end;a=1;run;',
                       'data d;a=1;if 0 then keep a;run;',
                       'data d;a=1;keep a;put _all_;run;'):
            self.assertTrue(compile_plan(source).blocked, source)

    def test_unsupported_source_lists_and_boundaries(self):
        for _, _, text in REFUSALS[:len(REFUSALS) - 3]:
            self.assertTrue(compile_plan('data d;a=1;keep ' + text + ';run;').blocked, text)
        for text in (' '.join('x' + str(i) for i in range(65)), 'x1-x64 extra'):
            with self.assertRaises(ValueError): name_list(text)
        self.assertEqual(len(name_list('x1-x64')), 64)
        self.assertEqual(name_list('x64-x64'), ['x64'])
        self.assertEqual(name_list('under_1-under_3'), ['under_1', 'under_2', 'under_3'])

    def test_forged_marker_metadata_rejected(self):
        template = compile_plan('data d;keep a;a=1;b=2;run;').to_dict()
        edits = [('mode', 'DROP'), ('mode', []), ('scope', 'other'), ('scope', []),
                 ('names', []), ('names', ['a', 'a']), ('names', ['A']), ('names', ['_n_']),
                 ('names', ['K']), ('names', ('a',)), ('names', [False]), ('extra', True)]
        for key, value in edits:
            plan = deepcopy(template)
            plan['steps'][0]['operations'][0]['args'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): run_plan(plan)
        for line in (False, 0, -1, '1', 1.0):
            plan = deepcopy(template); plan['steps'][0]['operations'][0]['line'] = line
            with self.subTest(line=line), self.assertRaises(ValueError): run_plan(plan)
        plan = deepcopy(template);plan['version'] = 1
        with self.assertRaises(ValueError): run_plan(plan)

    def test_forged_nested_and_duplicate_markers_rejected_even_when_skipped(self):
        template = compile_plan('data d;a=1;b=2;if 0 then output;run;').to_dict()
        projection = {'kind': 'projection', 'line': 1,
                      'args': {'mode': 'keep', 'names': ['a'], 'scope': 'statement'}}
        for container in ('if', 'unknown'):
            plan = deepcopy(template)
            if container == 'if': plan['steps'][0]['operations'][-1]['args']['operation'] = deepcopy(projection)
            else: plan['steps'][0]['operations'].append({'kind': 'unknown', 'line': 1, 'args': {'body': [deepcopy(projection)]}})
            with self.subTest(container=container), self.assertRaisesRegex(ValueError, 'projection'): run_plan(plan)
        plan = deepcopy(template);plan['steps'][0]['operations'].extend([deepcopy(projection), deepcopy(projection)])
        with self.assertRaisesRegex(ValueError, 'conflicting'): run_plan(plan)

    def test_forged_option_placement_and_context_rejected(self):
        template = compile_plan('data d;set raw(keep=a);run;').to_dict()
        for damage in ('by', 'where', 'input_count', 'read_names', 'read_line', 'adjacency', 'scope', 'kind', 'lookup'):
            plan = deepcopy(template);step = plan['steps'][0]
            if damage == 'by': step['by'] = ['a']
            elif damage == 'where': step['where'] = {'op': 'truth', 'left': {'kind': 'number', 'value': 0.}}
            elif damage == 'input_count': step['inputs'] = ['raw', 'other']
            elif damage == 'read_names': step['operations'][1]['args']['datasets'] = ['other']
            elif damage == 'read_line': step['operations'][1]['line'] = 2
            elif damage == 'adjacency': step['operations'].reverse()
            elif damage == 'scope': step['operations'][0]['args']['scope'] = 'output';step['operations'][0]['line'] = 2
            elif damage == 'kind': step['kind'] = 'merge'
            else: step['operations'].append({'kind': 'lookup', 'line': 1, 'args': {'dataset': 'cfg'}})
            with self.subTest(damage=damage), self.assertRaises(ValueError): run_plan(plan, catalog(False))
        plan = compile_plan('data d(keep=a);a=1;run;').to_dict()
        plan['steps'][0]['operations'].reverse()
        with self.assertRaisesRegex(ValueError, 'first'): run_plan(plan)

    def test_failed_projection_and_late_value_failure_publish_no_stdout(self):
        sources = ('data earlier;x=1;put x=;run;data d;keep missing;a=1;run;',
                   'data earlier;x=1;put x=;run;data d;keep a;a=1;put a=;a=1/3;run;')
        for source in sources:
            job = build_job(source)
            self.assertEqual(job.code, 1)
            self.assertFalse(job.receipt['accepted'])
            self.assertIsNone(job.result)
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream), self.assertRaises(ValueError): exec(translate(source).code, {})
            self.assertEqual(stream.getvalue(), '')

    def test_original_source_independent_R_emitted_job_and_cli(self):
        expected = original_expected()
        independent, count = program_witness()
        self.assertEqual(count, 25)
        self.assertEqual(independent, expected)
        source = ORIGINAL.read_text()
        self.assertEqual(execute(source), expected)
        stream = io.StringIO(); namespace = {}
        with contextlib.redirect_stdout(stream): exec(translate(source).code, namespace)
        self.assertEqual(namespace['result'], expected)
        self.assertEqual(stream.getvalue(), 'b=99 tag=seed\nb=99 tag=seed\n')
        self.assertTrue(build_job(source).receipt['accepted'])
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'result'
            result = subprocess.run([sys.executable, '-m', 'saschi', 'run', str(ORIGINAL), '--output', str(output)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads((output / 'result.json').read_text()), expected)
            receipt = json.loads((output / 'receipt.json').read_text())
            self.assertTrue(receipt['accepted'])
            self.assertEqual(receipt['source_sha256'], hashlib.sha256(ORIGINAL.read_bytes()).hexdigest())

    def test_four_wrong_interpretations_are_caught(self):
        self.assertEqual(naive_controls(), 4)

    def test_input_option_rejects_forged_executable_prefix_even_without_rows(self):
        prefixes = [
            {'kind':'assign','line':1,'args':{'name':'b','value':{'kind':'variable','value':'a'}}},
            {'kind':'put_literal','line':1,'args':{'literals':['early']}},
            {'kind':'output','line':1,'args':{'target':None}},
            {'kind':'subset','line':1,'args':{'condition':{'left':{'kind':'number','value':1.},'op':'truth'}}},
        ]
        for prefix in prefixes:
            for rows in ([], [{'a':1.}, {'a':3.}]):
                plan = compile_plan('data d;set raw(keep=a);b=a;run;').to_dict()
                plan['steps'][0]['operations'].insert(0, deepcopy(prefix))
                catalog = {'raw':{'schema':{'a':'number'},'rows':rows}}
                with self.subTest(prefix=prefix['kind'], rows=len(rows)), self.assertRaises(ValueError):
                    run_plan(plan, catalog)


if __name__ == '__main__':
    unittest.main()
