"""Behavioral regressions for the plan and numeric dataset workflow."""
import contextlib
import io
import unittest
from .emit_py import translate
from .parser import ParseError, split_statements
from .plan import compile_plan
from .rules import route_statement, route_function
from .runtime import run_plan


def execute(source, inputs=None):
    plan = compile_plan(source)
    if plan.blocked:
        raise AssertionError(plan.tickets)
    return run_plan(plan.to_dict(), inputs)


def table(rows):
    return {"schema": {name: "number" for name in rows[0]}, "rows": rows}


class ScannerRegressionTests(unittest.TestCase):
    def test_macro_quote_preserves_text_and_next_statement(self):
        for quote in ("%str(a;b)", "%nrstr(a(b;c)d)", "%str(a%;b)", "%str(%(x)"):
            source = f"%let x = {quote}; y=1;"
            statements = split_statements(source)
            self.assertEqual([s.text for s in statements], [f"%let x = {quote}", "y=1"])
            self.assertTrue(all(s.terminated for s in statements))

    def test_unclosed_fences_raise_at_start_line(self):
        for source in ('\nx="oops', '\nx=\'oops', '\n%let x=%str(a;', '\n/* x'):
            with self.assertRaises(ParseError) as caught:
                split_statements(source)
            self.assertEqual(caught.exception.line, 2)

    def test_multiline_string_reports_start(self):
        self.assertEqual(split_statements('"a\nb";')[0].line, 1)

    def test_comment_after_comment(self):
        self.assertEqual([s.text for s in split_statements('x=1; /* c */ * ignored; y=2;')], ['x=1', 'y=2'])

    def test_inline_data_is_opaque(self):
        for declaration, end in [('datalines', ';'), ('datalines4', ';;;;')]:
            statements = split_statements(f'data d; {declaration};\nx=1; put x=;\n{end}\nrun;')
            self.assertEqual(len(statements), 4)
            self.assertTrue(statements[2].text.startswith('<inline-data>'))
            self.assertIn('x=1; put x=;', statements[2].text)

    def test_router_does_not_read_variables_or_literals_as_procs(self):
        for text in ('reg=1', 'x="CORR"', 'summary=1'):
            self.assertEqual(route_statement(text), ('unknown', ''))
        self.assertEqual(route_function('x="round(a,1)"'), ('unknown', ''))
        self.assertEqual(route_statement('select sum(x) from t', context='sql')[1], 'SQL-001')


class ScalarRegressionTests(unittest.TestCase):
    def test_identifiers_and_numeric_literals(self):
        result = execute('data _null_; X=01; class=X; sas_round=2; y=round(class,sas_round); put x= class= y=; run;')
        self.assertEqual(result['log'], ['x=1 class=1 y=2'])

    def test_binary64_values(self):
        result = execute('data d; x=9007199254740993; y=9007199254740992; run;')
        row = result['datasets']['d']['rows'][0]
        self.assertEqual(row['x'], row['y'])
        self.assertIsInstance(row['x'], float)

    def test_step_scope_and_missing(self):
        self.assertEqual(execute('data _null_; x=1; run; data _null_; put x=; run;')['log'], ['x=.'])

    def test_bad_units_and_missing_propagate(self):
        result = execute('data _null_; x=round(1,0); y=round(.,1); put x= y=; run;')
        self.assertEqual(result['log'], ['x=. y=.'])

    def test_statements_outside_steps_block(self):
        self.assertTrue(compile_plan('x=1;').blocked)

    def test_unsupported_unit_cannot_execute_or_print(self):
        translated = translate('data d; x=1; if 0 then do; x=2; end; put x=; run;')
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(RuntimeError):
            exec(translated.code, {})
        self.assertEqual(output.getvalue(), '')


class DatasetTests(unittest.TestCase):
    SOURCE = '''data rounded; set raw; amount=round(amount,1); run;
proc sort data=rounded out=ordered; by id; run;
proc sort data=lookup out=keys; by id; run;
data joined; merge ordered keys; by id; run;'''

    def inputs(self):
        return {'raw': table([{'id': 2, 'amount': 2.5}, {'id': 1, 'amount': -1.5}, {'id': 1, 'amount': 3.5}]),
                'lookup': table([{'id': 3, 'flag': 30}, {'id': 1, 'flag': 10}])}

    def test_complete_workflow(self):
        rows = execute(self.SOURCE, self.inputs())['datasets']['joined']['rows']
        self.assertEqual(rows, [{'id': 1., 'amount': -2., 'flag': 10.}, {'id': 1., 'amount': 4., 'flag': 10.},
                                {'id': 2., 'amount': 3., 'flag': None}, {'id': 3., 'amount': None, 'flag': 30.}])

    def test_generated_program_has_same_contract(self):
        namespace = {'inputs': self.inputs()}
        exec(translate(self.SOURCE).code, namespace)
        self.assertEqual(namespace['result'], execute(self.SOURCE, self.inputs()))

    def test_no_input_mutation(self):
        import copy
        inputs = self.inputs(); before = copy.deepcopy(inputs)
        execute(self.SOURCE, inputs)
        self.assertEqual(inputs, before)

    def test_many_to_many_refuses(self):
        inputs = self.inputs()
        inputs['lookup']['rows'].append({'id': 1, 'flag': 99})
        with self.assertRaisesRegex(ValueError, 'DS-003'):
            execute(self.SOURCE, inputs)

    def test_unsorted_merge_refuses(self):
        with self.assertRaisesRegex(ValueError, 'sorted'):
            execute('data d; merge raw lookup; by id; run;', self.inputs())

    def test_schema_and_case_collisions_refuse(self):
        for inputs in ({'a': {'schema': {'x':'number'}, 'rows':[{'x':'1'}]}},
                       {'a': {'schema': {'x':'number', 'X':'number'}, 'rows':[]}}):
            with self.assertRaises(ValueError):
                execute('data b; set a; run;', inputs)

    def test_empty_input_preserves_schema(self):
        result = execute('data b; set a; y=round(x,1); run;', {'a': {'schema': {'x':'number'}, 'rows':[]}})
        self.assertEqual(result['datasets']['b'], {'schema': {'x':'number','y':'number'}, 'rows':[]})

    def test_nodupkey_stable_with_missing(self):
        inputs = {'a': table([{'id':1,'v':10}, {'id':None,'v':20}, {'id':1,'v':30}])}
        result = execute('proc sort data=a out=b nodupkey; by id; run;', inputs)
        self.assertEqual(result['datasets']['b']['rows'], [{'id':None,'v':20.}, {'id':1.,'v':10.}])

    def test_unsupported_options_and_statement_order_block(self):
        for source in ('data b; x=1; set a; run;', 'data b; set a b; run;',
                       'proc sort data=a force; by x; run;', 'proc sort data=a; by descending x; run;',
                       'data b; merge a c; run;', 'proc sort data=a; run;'):
            self.assertTrue(compile_plan(source).blocked, source)


class ComposedFixtureTests(unittest.TestCase):
    def test_shipped_workflow_matches_pins_and_base_r(self):
        import csv
        import json
        import os
        import shutil
        import subprocess
        from pathlib import Path
        fixture = Path(__file__).resolve().parent.parent / 'examples' / 'workflow'
        expected = json.loads((fixture/'expected.json').read_text())['joined']
        actual = execute((fixture/'job.sas').read_text(), json.loads((fixture/'inputs.json').read_text()))['datasets']['joined']
        self.assertEqual(actual, expected)
        r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript')
        self.assertTrue(r, 'Rscript is required for the composed workflow gate')
        run = subprocess.run([r, str(fixture/'reference.R')], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode,0,run.stderr)
        rows = [{k: float(v) if v else None for k,v in row.items()} for row in csv.DictReader(io.StringIO(run.stdout))]
        self.assertEqual(rows,expected['rows'])
