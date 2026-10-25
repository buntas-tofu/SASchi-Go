"""Quoted PUT integration and refusal gates. Repository evidence, no live SAS."""
import contextlib
import io
import unittest

from sas_semantics import sas_put_literals
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .rules import load_rulebook, route_statement
from .runtime import run_plan
from .test_parser import ROKU_CORPUS


class LiteralPutTests(unittest.TestCase):
    def execute(self, source, inputs=None):
        translation = translate(source)
        self.assertFalse(translation.blocked, translation.tickets)
        namespace = {'inputs': inputs or {}}
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            exec(translation.code, namespace)
        return namespace['result'], captured.getvalue()

    def test_emitted_spacing_quoting_and_records(self):
        source = '''data _null_;
          put 'Ready' " now";
          put 'O''Neil' ' says ' """go""";
          put ' left  ' ' right ';
          put '' "";
        run;'''
        result, printed = self.execute(source)
        self.assertEqual(result, {'datasets': {}, 'log': [
            'Ready now', 'O\'Neil says "go"', ' left   right ', "'\""]})
        self.assertEqual(printed, 'Ready now\nO\'Neil says "go"\n left   right \n\'"\n')

    def test_quoted_syntax_is_data(self):
        source = '''data _null_;
          put '_ALL_ _ERROR_ _NUMERIC_ _CHARACTER_';
          put 'a; /* no comment */' '&name %macro()';
          put 'a''b';
        run;'''
        result, _ = self.execute(source)
        self.assertEqual(result['log'], ['_ALL_ _ERROR_ _NUMERIC_ _CHARACTER_',
                                       'a; /* no comment */&name %macro()', "a'b"])

    def test_literals_add_no_pdv_variables(self):
        result, _ = self.execute("data d; x=7; put '_ALL_'; run;")
        self.assertEqual(result['datasets']['d']['schema'], {'x': 'number'})
        self.assertEqual(result['datasets']['d']['rows'], [{'x': 7.0}])

    def test_named_list_output_stays_separate_and_unchanged(self):
        result, printed = self.execute("data _null_; x=7; put 'value'; put x=; run;")
        self.assertEqual(result['log'], ['value', 'x=7'])
        self.assertEqual(printed, 'value\nx=7\n')

    def test_put_runs_in_iteration_order_and_respects_subsetting(self):
        inputs = {'raw': {'schema': {'keep': 'number'},
                          'rows': [{'keep': 0.0}, {'keep': 1.0}]}}
        result, _ = self.execute("data _null_; set raw; put 'before'; "
                                 "if keep; put 'after'; run;", inputs)
        self.assertEqual(result['log'], ['before', 'before', 'after'])
        inputs['raw']['rows'] = []
        result, _ = self.execute("data _null_; set raw; put 'unused'; run;", inputs)
        self.assertEqual(result['log'], [])

    def test_rule_provenance_and_source_line(self):
        source = "data _null_;\n/* fence */\nput 'Ready';\nrun;"
        plan = compile_plan(source)
        self.assertEqual(plan.matched, [('put-literal', 'DS-023', 3)])
        self.assertEqual(plan.steps[0].operations[0].line, 3)
        self.assertEqual(route_statement("put 'Ready'"), ('put-literal', 'DS-023'))
        self.assertIn('verify_put.py', load_rulebook()['DS-023'].validation_test)

    def test_non_literal_forms_still_block_the_whole_job(self):
        for statement in ("put 'value' x", "put x= 'suffix'", 'put x', 'put',
                          "put 'value' @", "put 'value' @@", "put @4 'value'",
                          "put 'value' / 'next'", "put 'value' +2 'next'",
                          "put 2*'value'", "put ('value')", "put 'value' $8.",
                          "put '41'x", "put '01JAN2020'd", "put _all_",
                          "if 1 then put 'value'", "file log; put 'value'"):
            with self.subTest(statement=statement):
                job = build_job("data _null_; put 'first'; " + statement + '; run;')
                self.assertEqual(job.code, 2)
                self.assertFalse(job.receipt['accepted'])
                self.assertIsNone(job.result)
                self.assertTrue(job.receipt['tickets'])

    def test_encoding_macro_and_line_size_refusals_are_compile_time_tickets(self):
        for literal in ("'café'", "'a\nb'", "'a\tb'", "'a\x00b'", '"&name"',
                        '"%macro()"', "'" + 'x' * 65 + "'"):
            with self.subTest(literal=literal):
                job = build_job('data _null_; put ' + literal + '; run;')
                self.assertEqual(job.code, 2)
                self.assertIsNone(job.result)
        self.assertFalse(compile_plan("data _null_; put '" + 'x' * 64 + "'; run;").blocked)

    def test_unterminated_literals_and_statements_stay_blocked(self):
        for source in ("data _null_; put 'open; run;", "data _null_; put 'closed'"):
            job = build_job(source)
            self.assertEqual(job.code, 2)
            self.assertIsNone(job.result)
            self.assertTrue(job.receipt['tickets'])
            if "'open" in source:
                self.assertEqual(job.receipt['completeness']['status'], 'unavailable')
                self.assertIn('unterminated string', job.receipt['completeness']['reason'])

    def test_runtime_revalidates_literal_plan_even_with_no_rows(self):
        plan = compile_plan("data _null_; set raw; put 'safe'; run;").to_dict()
        plan['steps'][0]['operations'][-1]['args']['literals'] = ['"&name"']
        with self.assertRaisesRegex(ValueError, 'macro review'):
            run_plan(plan, {'raw': {'schema': {}, 'rows': []}})
        for value in ([], None, 'not a token list', [7], [None]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sas_put_literals(value)

    def test_cpp_pilot_refuses_literal_put_instead_of_accepting_python_output(self):
        job = build_job("data _null_; put 'Ready'; run;", target='cpp')
        self.assertEqual(job.code, 2)
        self.assertIsNone(job.result)
        self.assertTrue(job.receipt['tickets'])
        self.assertFalse(job.receipt['accepted'])

    @unittest.skipUnless((ROKU_CORPUS / 'hello_world_text.sas').is_file(),
                         'sibling SASchi-Roku corpus is unavailable')
    def test_unchanged_roku_hello_world_clears_and_prints(self):
        source = (ROKU_CORPUS / 'hello_world_text.sas').read_text(encoding='utf-8')
        job = build_job(source)
        self.assertEqual(job.code, 0)
        self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.receipt['tickets'], [])
        self.assertEqual(job.result, {'datasets': {}, 'log': ['Hello world!']})
        result, printed = self.execute(source)
        self.assertEqual(result, job.result)
        self.assertEqual(printed, 'Hello world!\n')


if __name__ == '__main__':
    unittest.main()
