"""DS-027 execution and refusal coverage. Repository evidence, no live SAS."""
import contextlib
import io
import unittest

from sas_semantics import sas_put_numeric_list
from .emit_py import translate
from .plan import Operation, compile_plan, contains_put, put_known_types
from .rules import CONSTRUCT_MAP, load_rulebook
from .runtime import run_plan
from .test_put_list import build_job


def numeric_catalog(rows, *, spec='number'):
    return {'raw': {'schema': {'n': spec}, 'rows': [{'n': value} for value in rows]}}


class NumericListPutTests(unittest.TestCase):
    def execute(self, source, inputs=None):
        translation = translate(source)
        self.assertFalse(translation.blocked, translation.tickets)
        namespace = {'inputs': inputs or {}}
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            exec(translation.code, namespace)
        return namespace['result'], captured.getvalue()

    def test_source_order_numeric_variables_and_terminal_separator(self):
        result, printed = self.execute('data d; A=7; b=-3; c=.; put A b c a; run;')
        self.assertEqual(result['log'], ['7 -3 . 7 '])
        self.assertEqual(printed, '7 -3 . 7 \n')
        self.assertEqual(result['datasets']['d']['rows'], [{'a': 7., 'b': -3., 'c': None}])

    def test_retained_numeric_declaration_and_ordinary_missing(self):
        result, _ = self.execute('data d; retain n .; put n; n=9; put n; run;')
        self.assertEqual(result['log'], ['. ', '9 '])
        self.assertEqual(result['datasets']['d']['rows'], [{'n': 9.}])

    def test_assigned_copy_functions_arithmetic_and_conditional_type(self):
        result, _ = self.execute("data _null_; a=7; b=a; c=length('ab'); d=b-3; if 0 then e=9; put b c d e; run;")
        self.assertEqual(result['log'], ['7 2 4 . '])
        result, _ = self.execute('data _null_; n=round(8,2); m=mod(-7,3); put n m; run;')
        self.assertEqual(result['log'], ['8 -1 '])

    def test_declared_index_interface_requires_no_do_implementation(self):
        self.assertEqual(put_known_types([Operation('declare', 1, {'name': 'i', 'spec': 'number'})]), {'i': 'number'})
        plan = compile_plan('data _null_; n=7; put n; run;').to_dict()
        plan['steps'][0]['operations'][0] = {'kind': 'declare', 'line': 1, 'args': {'name': 'n', 'spec': 'number'}}
        self.assertEqual(run_plan(plan)['log'], ['. '])

    def test_known_numeric_after_set_keeps_order_and_output(self):
        inputs = numeric_catalog([1, 2, None])
        result, printed = self.execute('data d; set raw; n=n+1; i=7; put i; output; run;', inputs)
        self.assertEqual(result['log'], ['7 ', '7 ', '7 '])
        self.assertEqual(printed, '7 \n7 \n7 \n')
        self.assertEqual(result['datasets']['d']['rows'], [{'n': 2., 'i': 7.}, {'n': 3., 'i': 7.}, {'n': None, 'i': 7.}])

    def test_declared_numeric_set_values_and_refusals(self):
        source = 'data _null_; retain n .; set raw; put n; run;'
        result, _ = self.execute(source, numeric_catalog([7, None, -3, -0., 99999999999]))
        self.assertEqual(result['log'], ['7 ', '. ', '-3 ', '0 ', '99999999999 '])
        self.assertEqual(self.execute(source, numeric_catalog([]))[0]['log'], [])
        for value in (1.25, 100000000000, {'missing': 'A'}, {'missing': '_'}):
            job = build_job(source, numeric_catalog([7, value]))
            self.assertEqual(job.code, 1, value)
            self.assertIsNone(job.result)
        for rows in ([], [7]):
            job = build_job(source, numeric_catalog(rows, spec={'type': 'number', 'format': 'BEST12.'}))
            self.assertEqual(job.code, 1)
            self.assertIn('unformatted numeric', str(job.receipt))

    def test_source_order_known_type_keeps_unknown_and_mixed_refusals(self):
        for source in ('data _null_; put n; n=7; run;',
                       'data _null_; n=7; put n unknown; run;',
                       "data _null_; n=7; c='A'; put n c; run;",
                       "data _null_; set raw; copy=n; put copy; run;"):
            job = build_job(source, numeric_catalog([7]))
            self.assertIn(job.code, (1, 2), source)
            self.assertIsNone(job.result)
        for values in ([], [7], [None], [{'missing': 'A'}]):
            job = build_job('data _null_; set raw; put n; run;', numeric_catalog(values))
            self.assertEqual(job.code, 1)
            self.assertIsNone(job.result)

    def test_former_mixed_literal_numeric_refusal_is_now_gated(self):
        source="data _null_; n=7; put '[' n ']'; run;"
        result,stdout=self.execute(source)
        self.assertEqual(result,{'datasets':{},'log':['[7 ]']})
        self.assertEqual(stdout,'[7 ]\n')
        self.assertEqual(build_job(source).code,0)

    def test_character_literal_named_and_existing_refusals_are_unchanged(self):
        result, _ = self.execute("data _null_; c=' A '; n=7; put c; put '[' c ']'; put 'hi'; put n=; put n; run;")
        self.assertEqual(result['log'], ['A ', '[A ]', 'hi', 'n=7', '7 '])
        for source in ("data _null_; n=7; put '41'n; run;",
                       "data _null_; n=7; put '41'/*c*/ n; run;"):
            self.assertEqual(build_job(source).code, 2)

    def test_numeric_bound_missing_zero_and_negative_zero(self):
        result, _ = self.execute('data _null_; a=99999999999; b=-99999999999; c=-0.; d=.; put a b c d; run;')
        self.assertEqual(result['log'], ['99999999999 -99999999999 0 . '])

    def test_numeric_values_refuse_atomically(self):
        for value in ('1.25', '100000000000', '-100000000000', '.A', '._'):
            source = f"data _null_; n=7; put n; n={value}; put n; run;"
            job = build_job(source)
            self.assertEqual(job.code, 1, value)
            self.assertIsNone(job.result)
            self.assertFalse(job.receipt['accepted'])
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured), self.assertRaises(ValueError):
                exec(translate(source).code, {'inputs': {}})
            self.assertEqual(captured.getvalue(), '')

    def test_source_program_guards_include_unused_and_prior_literals(self):
        for source in ('data _null_; n=7; put n; unused="&name"; run;',
                       'data _null_; unused="%call"; n=7; put n; run;',
                       'data prior; c="&name"; run; data _null_; n=7; put n; run;',
                       "data _null_; n=length('café'); put n; run;",
                       "data _null_; n=7; put n; unused='a\tb'; run;"):
            job = build_job(source)
            self.assertEqual(job.code, 2, source)
            self.assertIsNone(job.result)
        result, _ = self.execute("data _null_; n=length('&x'); put n; run;")
        self.assertEqual(result['log'], ['2 '])

    def test_guard_traversal_handles_serialized_nested_operations(self):
        body = [{'kind': 'put_numeric_list', 'line': 2, 'args': {'names': ['i']}}]
        self.assertTrue(contains_put([Operation('container', 1, {'body': body})], {'put_numeric_list'}))
        self.assertFalse(contains_put([Operation('container', 1, {'body': body})], {'put_all'}))

    def test_formats_are_rejected_even_empty_or_where_filtered(self):
        spec = {'type': 'number', 'format': 'BEST12.'}
        for rows in ([], [7]):
            for source in ('data _null_; set raw; n=7; put n; run;',
                           'data _null_; set raw; where n=0; n=7; put n; run;',
                           'data d; set raw; run; data _null_; set d; n=7; put n; run;'):
                job = build_job(source, numeric_catalog(rows, spec=spec))
                self.assertEqual(job.code, 1, (rows, source))
                self.assertIsNone(job.result)
                self.assertIn('unformatted numeric', str(job.receipt))

    def test_character_descriptor_rejected_even_without_rows(self):
        for rows in ([], ['A']):
            inputs = numeric_catalog(rows, spec={'type': 'character', 'length': 1})
            job = build_job('data _null_; set raw; n=7; put n; run;', inputs)
            self.assertEqual(job.code, 1)
            self.assertIsNone(job.result)

    def test_plain_numeric_copy_does_not_inherit_format(self):
        result, _ = self.execute('data _null_; set raw; n=7; copy=n; put copy; run;',
                                 numeric_catalog([9], spec={'type': 'number', 'format': 'COMMA12.'}))
        self.assertEqual(result['log'], ['7 '])

    def test_lookup_format_is_not_hidden_on_empty_inputs(self):
        for rows in ([], [7]):
            inputs = numeric_catalog(rows, spec={'type': 'number', 'format': 'BEST12.'})
            inputs['defaults'] = numeric_catalog([])['raw']
            job = build_job('data _null_; if _n_=1 then set defaults; set raw; n=7; put n; run;', inputs)
            self.assertEqual(job.code, 1)
            self.assertIsNone(job.result)
            self.assertIn('unformatted numeric', str(job.receipt))

    def test_record_width_and_minimum_record_prevalidation(self):
        source = 'data _null_; n=0; put ' + ' '.join(['n'] * 32) + '; run;'
        result, _ = self.execute(source)
        self.assertEqual(result['log'], ['0 ' * 32])
        self.assertEqual(build_job(source.replace('n=0', 'n=-1')).code, 1)
        source = 'data _null_; n=0; put ' + ' '.join(['n'] * 33) + '; run;'
        self.assertEqual(build_job(source).code, 2)

    def test_file_formats_controls_literals_and_conditional_put_refuse(self):
        for statement in ('put n best12.', 'put n : best12.', 'put n ~ best12.', 'put n @',
                          'put n @@', 'put @4 n', 'put n /', 'put n +2', 'put (n)',
                          'put n 7', 'put 7', 'put n*2', 'file log; put n'):
            job = build_job('data _null_; n=7; ' + statement + '; run;')
            self.assertEqual(job.code, 2, statement)
            self.assertIsNone(job.result)
        for name in ('_n_', '_error_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_', '_all_', '_numeric_', '_character_'):
            self.assertEqual(build_job('data _null_; ' + name + '=7; put ' + name + '; run;').code, 2)

    def test_former_conditional_numeric_put_refusal_is_now_gated(self):
        job=build_job('data _null_; n=7; if 1 then put n; run;')
        self.assertEqual(job.code,0)
        self.assertEqual(job.result['log'],['7 '])
        self.assertEqual(job.result['datasets'],{})

    def test_forged_plan_arguments_are_validated_without_rows(self):
        for args in ({'names': None}, {'names': []}, {'names': 'n'}, {'names': [1]},
                     {'names': ['N']}, {'names': ['_n_']}, {'names': ['unknown']},
                     {'names': ['n'], 'format': 'BEST12.'}):
            plan = compile_plan('data _null_; set raw; n=7; put n; run;').to_dict()
            plan['steps'][0]['operations'][-1]['args'] = args
            with self.subTest(args=args), self.assertRaises(ValueError):
                run_plan(plan, numeric_catalog([]))
        for values in (None, [], '7', [True], ['7'], [{'missing': 'A'}], [float('nan')], [float('inf')]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                sas_put_numeric_list(values)

    def test_source_line_operation_and_rulebook_provenance(self):
        plan = compile_plan('data _null_; n=7;\nput n; run;')
        self.assertEqual(plan.matched, [('put-numeric-list', 'DS-027', 2)])
        self.assertEqual(plan.steps[0].operations[-1], Operation('put_numeric_list', 2, {'names': ['n']}))
        self.assertEqual(CONSTRUCT_MAP['put-numeric-list'], 'DS-027')
        self.assertIn('verify_put_numeric.py', load_rulebook()['DS-027'].validation_test)
        job = build_job('data _null_; n=7;\nput n; run;')
        self.assertEqual(job.code, 0)
        self.assertTrue(job.receipt['accepted'])

    def test_cpp_refuses_new_operation(self):
        job = build_job('data _null_; n=7; put n; run;', target='cpp')
        self.assertEqual(job.code, 2)
        self.assertIsNone(job.result)
        self.assertFalse(job.receipt['accepted'])


if __name__ == '__main__':
    unittest.main()
