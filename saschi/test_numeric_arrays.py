"""DS-039 original source execution and refusal evidence, no live SAS."""
from copy import deepcopy
import json
import unittest

from .compare import table_equal
from .emit_cpp import translate as cpp
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import execute, job_with_inputs
from sas_semantics import sas_numeric_array_add, sas_numeric_array_sum


def catalog(rows, spec='number'):
    return {'raw': {'schema': {'x': spec}, 'rows': [{'x': x} for x in rows]}}


class NumericArrayTests(unittest.TestCase):
    def run_source(self, body, inputs=None):
        return execute('data d; ' + body + ' run;', inputs)[0]['datasets']['d']

    def blocked(self, body):
        p = compile_plan('data d; ' + body + ' run;')
        self.assertTrue(p.blocked, body)
        return p

    def test_array_operation_seam_and_rule(self):
        p = compile_plan('data d; array A{0:1} X Y; a[0]=7; z=sum(of a{*}); run;')
        self.assertFalse(p.blocked, p.tickets)
        ops = p.to_dict()['steps'][0]['operations']
        self.assertEqual(ops[0]['args'], {'name': 'a', 'lower': 0, 'names': ['x', 'y']})
        self.assertEqual(ops[1]['kind'], 'array_set')
        self.assertEqual(ops[2]['args']['value'], {'kind': 'array_sum', 'name': 'a'})
        self.assertIn(('numeric-arrays', 'DS-039', 1), p.matched)

    def test_aliasing_both_directions(self):
        t = self.run_source('array a{2} x y; x=3; r=a[1]; a{2}=7; s=y;')
        self.assertEqual(t['rows'], [{'x': 3., 'y': 7., 'r': 3., 's': 7.}])

    def test_overlapping_arrays_share_current_bindings(self):
        t = self.run_source('array a[2] x y; array b[*] y x; b[1]=9; a[1]=2; r=b[2];')
        self.assertEqual(t['rows'], [{'x': 2., 'y': 9., 'r': 2.}])

    def test_explicit_and_inferred_declaration_forms(self):
        for decl in ('array a{3} x1-x3', 'array a[3] x1 x2 x3', 'array a(3) x1-x3',
                     'array a{*} x1-x3', 'array a x1-x3'):
            with self.subTest(decl=decl):
                t = self.run_source(decl + '; a{3}=4;')
                self.assertEqual(t['rows'], [{'x1': None, 'x2': None, 'x3': 4.}])

    def test_generated_names_and_custom_bounds(self):
        for controls, index in (('3', 3), ('0:2', 2), ('-2:0', 0), ('1990:1992', 1992)):
            t = self.run_source(f'array a{{{controls}}}; a[{index}]=8;')
            self.assertEqual(t['rows'], [{'a1': None, 'a2': None, 'a3': 8.}])

    def test_computed_indices_and_nested_reads(self):
        t = self.run_source('array a[3] x y z; i=0; a[i+1]=2; a[a[1]]=7; r=a[(i+1)+1];')
        self.assertEqual(t['rows'][0]['r'], 7.)

    def test_sum_missing_and_exact_fractional_values(self):
        t = self.run_source('array a[3] x y z; before=sum(of a[*]); x=.5; z=-.25; after=sum(of a{*});')
        self.assertIsNone(t['rows'][0]['before'])
        self.assertEqual(t['rows'][0]['after'], .25)
        self.assertIsNone(sas_numeric_array_sum([None, None]))

    def test_sum_and_sum_statement_remain_distinct(self):
        t = self.run_source('array a[2] x y; s=sum(of a[*]); total+sum(of a[*]);')
        self.assertIsNone(t['rows'][0]['s'])
        self.assertEqual(t['rows'][0]['total'], 0.)

    def test_array_sum_composed_in_exact_arithmetic(self):
        t = self.run_source('array a[2] x y; x=2; y=5; z=sum(of a[*])+a[2]-1;')
        self.assertEqual(t['rows'][0]['z'], 11.)

    def test_missing_arithmetic_propagates(self):
        t = self.run_source('array a[2] x y; a[1]=a[2]+1; r=a[1];')
        self.assertIsNone(t['rows'][0]['r'])

    def test_output_snapshots_include_future_descriptors(self):
        t = self.run_source('array a[2] x y; a[1]=3; output; a[2]=7; later=sum(of a[*]); output;')
        self.assertEqual(list(t['schema']), ['x', 'y', 'later'])
        self.assertEqual(t['rows'], [{'x': 3., 'y': None, 'later': None}, {'x': 3., 'y': 7., 'later': 10.}])

    def test_counted_body_and_index_output_scheduling(self):
        t = self.run_source('array a[3] x1-x3; do i=1 to 3; a[i]=i+2; output; end;')
        self.assertEqual([r['i'] for r in t['rows']], [1., 2., 3.])
        self.assertEqual(t['rows'][0]['x3'], None)
        self.assertEqual(t['rows'][-1]['x3'], 5.)

    def test_until_and_while_compositions(self):
        for control in ('while(i<=2)', 'until(i>2)'):
            t = self.run_source(f'array a[2] x y; i=1; do {control}; a[i]=i; i=i+1; end;')
            self.assertEqual(t['rows'], [{'x': 1., 'y': 2., 'i': 3.}])
        t = self.run_source('array a[1] x; x=0; do until(a[1]=3); a[1]=a[1]+1; end;')
        self.assertEqual(t['rows'], [{'x': 3.}])

    def test_conditional_writes_and_character_predicate_locality(self):
        t = self.run_source("array a[2] x y; c='Y'; if c='Y' then a[1]=4; else a[2]=9; if a[1]=4 then a[2]=5;")
        self.assertEqual(t['rows'][0], {'x': 4., 'y': 5., 'c': 'Y'})

    def test_scratch_elements_reset_per_input_row(self):
        t = self.run_source('set raw; array a[2] x scratch; if _n_=1 then a[2]=9; total=sum(of a[*]);', catalog([2, 3]))
        self.assertEqual([r['scratch'] for r in t['rows']], [9., None])
        self.assertEqual([r['total'] for r in t['rows']], [11., 3.])

    def test_inherited_descriptors_and_input_immutability(self):
        inputs = catalog([3], {'type': 'number', 'length': 8, 'label': 'Input value', 'format': 'BEST12.'})
        before = deepcopy(inputs)
        for body in ('array a[1] x; set raw; a[1]=4;', 'set raw; array a[1] x; a[1]=4;'):
            t = self.run_source(body, inputs)
            self.assertEqual(t['schema']['x'], inputs['raw']['schema']['x'])
        self.assertEqual(inputs, before)

    def test_empty_filtered_and_zero_trip_descriptors(self):
        for body, inputs in (('set raw; array a[2] x y;', catalog([])),
                             ('set raw; where 0; array a[2] x y;', catalog([2])),
                             ('array a[2] x y; do i=2 to 1; a[i]=7; end;', None)):
            t = self.run_source(body, inputs)
            self.assertIn('x', t['schema']); self.assertIn('y', t['schema'])
        t = self.run_source('array a[1] x; if 0 then output;')
        self.assertEqual(t['rows'], [])

    def test_array_name_never_becomes_a_column(self):
        t = self.run_source('array a[2]; a[1]=1;')
        self.assertNotIn('a', t['schema'])

    def test_maximum_step_extent_and_combined_declaration_budget(self):
        t = self.run_source('array a[1024]; a[1024]=7;')
        self.assertEqual(len(t['schema']), 1024)
        self.assertEqual(t['rows'][0]['a1024'], 7.)
        self.blocked('array a[600]; array b[600];')

    def test_index_evaluates_before_an_aliased_assignment(self):
        t = self.run_source('array a[2] x y; x=1; y=2; a[a[1]]=a[2];')
        self.assertEqual(t['rows'], [{'x': 2., 'y': 2.}])

    def test_false_dynamic_read_and_zero_trip_are_lazy(self):
        for body in ('if 0 then r=a[i];', 'do j=2 to 1; r=a[i]; end;', 'do while(0); r=a[i]; end;'):
            t = self.run_source('array a[1] x; i=2; '+body)
            self.assertIsNone(t['rows'][0]['r'])

    def test_dynamic_read_errors_have_source_lines_and_no_emitted_prefix(self):
        import contextlib
        import io
        from .emit_py import translate
        src='data d; array a[1] x; i=2; put "before"; output; r=a[i]; run;'
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream), self.assertRaisesRegex(ValueError, 'SAS line 1.*subscript'):
            exec(translate(src).code, {})
        self.assertEqual(stream.getvalue(), '')

    def test_old_fractional_and_wide_scalar_arithmetic_stays_local(self):
        t = self.run_source('array a[1] x; x=2; scalar=.1+.2; wide=2147483647+1; r=a[1];')
        self.assertEqual(t['rows'][0]['scalar'], .1+.2)
        self.assertEqual(t['rows'][0]['wide'], 2147483648.)

    def test_repeated_runs_and_steps_have_separate_bindings(self):
        p = compile_plan('data d; array a[1] x; x=2; run; data e; array a[1] y; r=a[1]; run;').to_dict()
        before = deepcopy(p)
        self.assertEqual(run_plan(p), run_plan(p))
        self.assertIsNone(run_plan(p)['datasets']['e']['rows'][0]['r'])
        self.assertEqual(p, before)

    def test_numeric_put_keeps_its_existing_contract(self):
        result, stdout = execute('data d; array a[2] x y; a[1]=3; put x y; run;')
        self.assertEqual(result['log'], ['3 . ']); self.assertEqual(stdout, '3 . \n')
        job = job_with_inputs('data d; array a[1] x; x=.5; put x; run;', {})
        self.assertEqual(job.code, 1); self.assertIsNone(job.result)

    def test_undefined_and_forward_array_references_refuse(self):
        for body in ('x=a[1];', 'x=sum(of a[*]);', 'a[1]=2; array a[1] x;'):
            self.blocked(body)

    def test_declaration_refusal_matrix(self):
        for decl in ('array a[0]', 'array a[1025]', 'array a[*]', 'array a[2] x',
                     'array a[2] x x', 'array a[2] a x', 'array a[2,2] x1-x4',
                     'array a[2] $ x y', 'array a[2] _temporary_', 'array a[2] x y (1 2)',
                     'array a[2] x--y', 'array a[2] x01-x02', 'array a[2] x2-x1',
                     'array a[2] x1-y2', 'array a[n] x y', 'array sum[2] x y',
                     'array a[2147483647:2147483648] x y', 'array a[2] _n_ x'):
            with self.subTest(decl=decl): self.blocked(decl + ';')

    def test_array_identifier_is_never_split_into_extra_elements(self):
        name = 'q' * 32
        t = self.run_source(f'array {name}[1] x; {name}[1]=7;')
        self.assertEqual(t['rows'], [{'x': 7.}])
        for size in (33, 34, 63):
            with self.subTest(size=size):
                self.blocked('array ' + 'q' * size + ' x;')

    def test_declarations_in_bodies_and_duplicate_arrays_refuse(self):
        for body in ('do i=1 to 2; array a[1] x; end;', 'if 0 then array a[1] x;',
                     'array a[1] x; array a[1] y;', 'array a[1] b; array b[1] x;'):
            self.blocked(body)

    def test_literal_indices_refuse_even_when_skipped(self):
        for index in ('0', '3', '.5', '.', '.A', "'1'", '1+2', '2147483648'):
            self.blocked(f'array a[2] x y; if 0 then a[{index}]=1;')

    def test_bad_dynamic_indices_are_lazy_and_atomic(self):
        for index in (0, 3, .5, None, {'missing': 'A'}):
            source = 'data d; set raw; array a[2] y z; put "before"; output; a[x]=1; run;'
            job = job_with_inputs(source, catalog([index]))
            self.assertEqual(job.code, 1); self.assertIsNone(job.result); self.assertFalse(job.receipt['accepted'])
            self.assertIn('subscript' if index != {'missing': 'A'} else 'numeric', str(job.receipt))
            t = self.run_source('set raw; array a[2] y z; if 0 then a[x]=1;', catalog([index]))
            self.assertEqual(len(t['rows']), 1)

    def test_empty_dynamic_type_errors_are_eager(self):
        for values in ([], ['X']):
            with self.assertRaisesRegex(ValueError, 'numeric|character'):
                self.run_source('set raw; array a[1] y; if 0 then y=a[x];', catalog(values, {'type': 'character', 'length': 1}))
        with self.assertRaisesRegex(ValueError, 'numeric'):
            self.run_source('set raw; array a[1] x;', catalog([], {'type': 'character', 'length': 1}))

    def test_alias_storage_refuses_tags_and_wide_values(self):
        for value in ('.A', '2147483648'):
            with self.assertRaises(ValueError): self.run_source(f'array a[1] x; x={value};')
        with self.assertRaises(ValueError): self.run_source('set raw; array a[1] x;', catalog([{'missing': 'A'}]))

    def test_new_arithmetic_refuses_rounding_and_wider_partials(self):
        for values in ([.1, .2], [2147483647, 1, -1], [2147483647, 1e-300, -2147483647]):
            with self.assertRaises(ValueError): sas_numeric_array_sum(values)
        with self.assertRaises(ValueError): sas_numeric_array_add(.1, .2)
        with self.assertRaises(ValueError): self.run_source('array a[2] x y; x=.1; y=.2; s=sum(of a[*]);')

    def test_name_and_state_conflicts_refuse(self):
        for body in ('array a[1] x; a=3;', 'array a[1] x; y=a;', 'array a[1] x; put a=;',
                     'array a[1] x; retain x 0;', 'array a[1] x; x+1;',
                     'array a[1] i; do i=1 to 2; end;'):
            self.blocked(body)

    def test_later_profiles_remain_refused(self):
        for body in ('array a[1] x; do over a; a=3; end;',
                     'array a[1] x; y=a(1);', 'array a[1] x; y=dim(a);',
                     'array a[1] x; y=int(a[1]);', 'array a[1] x; y=a[1]/2;',
                     'array a[1] x; a[1]=int(3);', 'array a[1] x; put _all_;',
                     'set raw; array a[1] x; where a[1]>0;'):
            self.blocked(body)
        self.assertTrue(cpp('data _null_; array a[1] x; a[1]=1; run;').blocked)

    def test_unrelated_function_calls_keep_old_refusal_route(self):
        p = compile_plan('data d; x=sqrt(7); run;')
        self.assertEqual(p.tickets[0].construct, 'assignment')

    def test_calls_can_use_a_stored_scalar_without_global_quarantine(self):
        t = self.run_source('array a[1] x; x=4; r=a[1]; q=int(r/2);')
        self.assertEqual(t['rows'][0]['q'], 2.)

    def test_source_node_budget_and_recursive_index_depth(self):
        self.blocked('array a[1] x; r=' + '+'.join(['a[1]'] * 130) + ';')
        self.blocked('array a[1] x; r=' + 'a[' * 34 + '1' + ']' * 34 + ';')

    def test_serialized_plan_cannot_bypass_declaration_guards(self):
        p = compile_plan('data d; array a[2] x y; a[1]=7; run;').to_dict()
        mutations = [lambda q: q.update(version=1),
                     lambda q: q['steps'][0]['operations'][0]['args'].update(lower=True),
                     lambda q: q['steps'][0]['operations'][0]['args'].update(names=['x', 'x']),
                     lambda q: q['steps'][0]['operations'][0]['args'].update(extra=1),
                     lambda q: q['steps'][0]['operations'][1]['args'].update(name='other'),
                     lambda q: q['steps'][0]['operations'][1]['args'].update(extra=1),
                     lambda q: q['steps'][0]['operations'][1]['args']['value'].update(kind='character', value='7')]
        for mutate in mutations:
            q = deepcopy(p); mutate(q)
            with self.subTest(plan=q), self.assertRaises(ValueError): run_plan(q)

    def test_runtime_checks_skipped_forged_index(self):
        p = compile_plan('data d; array a[1] x; if 0 then x=a[1]; run;').to_dict()
        p['steps'][0]['operations'][1]['args']['operation']['args']['value']['index']['value'] = 2
        with self.assertRaises(ValueError): run_plan(p)

    def test_comparator_catches_schema_and_value_loss(self):
        t = self.run_source('array a[2] x y; a[1]=3;')
        wrong = deepcopy(t); wrong['rows'][0]['x'] = None
        self.assertFalse(table_equal(t, wrong))
        wrong = deepcopy(t); del wrong['schema']['y']
        self.assertFalse(table_equal(t, wrong))


if __name__ == '__main__':
    unittest.main()
