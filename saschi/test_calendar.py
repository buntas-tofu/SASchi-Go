"""DS-033 translated calendar and complete-program evidence, no live SAS."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from examples.verify_calendar import program_records
from sas_semantics import SAS_CALENDAR_MIN_DAY, SAS_CALENDAR_MAX_DAY, sas_calendar
from .emit_py import translate
from .functions import FUNCTIONS
from .job import build_job
from .plan import compile_plan
from .rules import route_function
from .runtime import run_plan
from .test_parser import ROKU_CORPUS

SOURCE_SHA = '4bcce862221b4089d579f178c0a32df845aa2c16655d93388e7c34635c65b667'
STDOUT_SHA = '75bcb72828de55e59f759978c1751631b89241fa302042f7394e3965a5f12f3b'
RESULT_SHA = 'c6fedd1f08f38ce8c67ad2cdbac5b823398560f5df8a3cc56634c41a87be279a'
YEARS = [2011, 2016, 2022, 2033, 2039, 2044, 2050, 2061, 2067,
         2072, 2078, 2089, 2095, 2101, 2107, 2112, 2118]


def execute(source, inputs=None):
    translated = translate(source)
    if translated.blocked:
        raise AssertionError(translated.tickets)
    namespace = {'inputs': inputs or {}}
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        exec(translated.code, namespace)
    return namespace['result'], printed.getvalue()


class CalendarTests(unittest.TestCase):
    def test_registry_routing_and_function_provenance(self):
        for name, arity in (('mdy', 3), ('weekday', 1)):
            self.assertEqual(route_function(name.upper() + '('), ('calendar', 'DS-033'))
            spec = FUNCTIONS[name]
            self.assertEqual((spec.min_args, spec.max_args, spec.returns), (arity, arity, 'number'))
            self.assertEqual(spec.gate, 'examples/verify_calendar.py')
        self.assertEqual(route_function("x='MDY(1,1,2000)'"), ('unknown', ''))

    def test_nested_calls_arithmetic_arguments_and_case(self):
        source = 'data d; d=MDY(1,1,1960); w=WeekDay(d); z=weekday(mdy(1,1,1960)-1); run;'
        result, printed = execute(source)
        self.assertEqual(result['datasets']['d']['rows'], [{'d': 0., 'w': 6., 'z': 5.}])
        self.assertEqual(printed, '')
        self.assertEqual(result, run_plan(compile_plan(source).to_dict()))

    def test_gregorian_century_and_leap_boundaries(self):
        source = ('data d; a=mdy(2,28,1900); b=mdy(3,1,1900); '
                  'c=mdy(2,28,2000); e=mdy(3,1,2000); first=b-a; second=e-c; run;')
        row = execute(source)[0]['datasets']['d']['rows'][0]
        self.assertEqual((row['first'], row['second']), (1., 2.))

    def test_all_weekdays_and_negative_epoch_values(self):
        inputs = {'raw': {'schema': {'day': 'number'}, 'rows': [{'day': day} for day in range(-7, 7)]}}
        rows = execute('data d; set raw; w=weekday(day); run;', inputs)[0]['datasets']['d']['rows']
        self.assertEqual([r['w'] for r in rows], [6., 7., 1., 2., 3., 4., 5.] * 2)

    def test_boundary_years_and_integral_day_limits(self):
        row = execute('data d; a=mdy(1,1,1753); b=mdy(12,31,3999); x=weekday(a); y=weekday(b); run;')[0]['datasets']['d']['rows'][0]
        self.assertEqual((row['a'], row['b']), (SAS_CALENDAR_MIN_DAY, SAS_CALENDAR_MAX_DAY))
        self.assertIn(row['x'], range(1, 8))
        self.assertIn(row['y'], range(1, 8))

    def test_if_else_predicates_and_loop_dispatch(self):
        source = ('data d; do y=2000 to 2002; d=mdy(1,1,y); '
                  'if weekday(d)=7 then code=1; else if weekday(d)=2 then code=2; else code=3; output; end; run;')
        result, _ = execute(source)
        self.assertEqual([r['code'] for r in result['datasets']['d']['rows']], [1., 2., 3.])
        matches = compile_plan(source).matched
        self.assertTrue(any(c == 'calendar' and r == 'DS-033' for c, r, _ in matches))

    def test_where_calls_filter_using_driving_descriptors(self):
        inputs = {'raw': {'schema': {'day': 'number'}, 'rows': [{'day': x} for x in (0, 1, 2)]}}
        rows = execute('data d; set raw; where weekday(day)=1; w=weekday(day); run;', inputs)[0]['datasets']['d']['rows']
        self.assertEqual(rows, [{'day': 2., 'w': 1.}])

    def test_filtered_dynamic_invalid_values_do_not_execute(self):
        inputs = {'raw': {'schema': {'day': 'number'}, 'rows': [{'day': None}, {'day': 0}]}}
        rows = execute('data d; set raw; where day>=0; w=weekday(day); run;', inputs)[0]['datasets']['d']['rows']
        self.assertEqual(rows, [{'day': 0., 'w': 6.}])

    def test_unselected_dynamic_call_is_lazy(self):
        result, _ = execute('data d; n=.; if 0 then x=weekday(n); else x=7; run;')
        self.assertEqual(result['datasets']['d']['rows'], [{'n': None, 'x': 7.}])

    def test_invalid_literals_refuse_even_in_skipped_branches_and_zero_trip(self):
        for expression in ('mdy(2,29,1900)', 'mdy(2,30,2000)', 'mdy(1,1,20)',
                           'mdy(1,1,4000)', 'weekday(.)', 'weekday(.A)', 'weekday(.5)'):
            for body in (f'if 0 then x={expression};', f'do i=2 to 1; x={expression}; end;'):
                with self.subTest(expression=expression, body=body):
                    with self.assertRaisesRegex(ValueError, 'calendar'):
                        execute('data d; ' + body + ' run;')

    def test_character_descriptors_refuse_on_empty_and_filtered_input(self):
        for rows in ([], [{'day': '0'}]):
            inputs = {'raw': {'schema': {'day': {'type': 'character', 'length': 1}}, 'rows': rows}}
            for body in ('where 0; w=weekday(day);', 'where weekday(day)=1;',
                         'if 0 then w=weekday(day);'):
                with self.subTest(rows=rows, body=body):
                    with self.assertRaisesRegex(ValueError, 'calendar'):
                        execute('data d; set raw; ' + body + ' run;', inputs)

    def test_later_character_assignment_keeps_source_order_type_refusal(self):
        with self.assertRaisesRegex(ValueError, 'implicit assignment type conversion'):
            execute("data d; if 0 then x=weekday(c); c='x'; run;")

    def test_input_metadata_and_schema_order_survive(self):
        inputs = {'raw': {'schema': {'day': {'type': 'number', 'label': 'SAS day'}}, 'rows': [{'day': 0}]}}
        table = execute('data d; set raw; w=weekday(day); run;', inputs)[0]['datasets']['d']
        self.assertEqual(list(table['schema']), ['day', 'w'])
        self.assertEqual(table['schema']['day'], {'type': 'number', 'label': 'SAS day'})
        self.assertEqual(table['rows'], [{'day': 0., 'w': 6.}])

    def test_wrong_arity_unwired_functions_and_cpp_remain_blocked(self):
        for expression in ('mdy(1,1)', 'mdy(1,1,2000,1)', 'weekday()', 'weekday(0,1)', 'year(0)'):
            self.assertTrue(compile_plan('data d; x=' + expression + '; run;').blocked)
        job = build_job('data _null_; d=mdy(1,1,1960); run;', target='cpp')
        self.assertEqual(job.code, 2)
        self.assertIsNone(job.result)

    def test_helper_refuses_boolean_and_wider_calendar(self):
        for name, values in (('weekday', (True,)), ('mdy', (1, 1, 10000)),
                             ('weekday', (SAS_CALENDAR_MAX_DAY + 1,)), ('mdy', (1, 1, 1752))):
            with self.assertRaisesRegex(ValueError, 'calendar'):
                sas_calendar(name, *values)

    def test_forged_call_arguments_and_literals_cannot_bypass_runtime_checks(self):
        original = compile_plan('data d; x=weekday(0); run;').to_dict()
        for args in ([], [None], [{'kind': 'number', 'value': True}],
                     [{'kind': 'number', 'value': 0}, {'kind': 'number', 'value': 0}], 'bad'):
            plan = deepcopy(original)
            plan['steps'][0]['operations'][0]['args']['value']['args'] = args
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, 'calendar'):
                run_plan(plan, allow_partial=True)

    def test_late_invalid_value_cannot_publish_any_records(self):
        source = 'data prior; put "earlier"; run; data d; set raw; w=weekday(day); put w; run;'
        inputs = {'raw': {'schema': {'day': 'number'}, 'rows': [{'day': 0}, {'day': .5}]}}
        translated = translate(source)
        self.assertFalse(translated.blocked, translated.tickets)
        output = io.StringIO()
        namespace = {'inputs': inputs}
        with contextlib.redirect_stdout(output), self.assertRaisesRegex(ValueError, 'calendar'):
            exec(translated.code, namespace)
        self.assertEqual(output.getvalue(), '')
        self.assertNotIn('result', namespace)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'inputs.json'
            path.write_text(json.dumps(inputs))
            job = build_job(source, path)
        self.assertEqual(job.code, 1)
        self.assertFalse(job.receipt['accepted'])
        self.assertIsNone(job.result)

    def test_put_all_calendar_composition_remains_deferred(self):
        job = build_job('data _null_; d=mdy(1,1,1960); put _all_; run;')
        self.assertEqual(job.code, 1)
        self.assertIsNone(job.result)
        self.assertIn('error-flag review', job.receipt['error'])

    def test_receipt_comparator_controls_keep_observed_results(self):
        source = 'data d; x=mdy(1,1,1960); w=weekday(x); run;'
        table = {'schema': {'x': 'number', 'w': 'number'}, 'rows': [{'x': 0., 'w': 6.}]}
        changes = []
        changed = deepcopy(table); changed['rows'][0]['w'] = 5.; changes.append(changed)
        changed = deepcopy(table); changed['rows'].append(dict(changed['rows'][0])); changes.append(changed)
        changed = deepcopy(table); changed['schema'] = {'w': 'number', 'x': 'number'}; changes.append(changed)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'expected.json'
            path.write_text(json.dumps({'d': table}))
            positive = build_job(source, expect=path)
            self.assertTrue(positive.receipt['accepted'])
            self.assertEqual(positive.receipt['comparison'], 'passed')
            for changed in changes:
                path.write_text(json.dumps({'d': changed}))
                job = build_job(source, expect=path)
                self.assertEqual(job.code, 1)
                self.assertFalse(job.receipt['accepted'])
                self.assertEqual(job.receipt['comparison'], 'failed')
                self.assertEqual(job.result['datasets']['d'], table)


class CalendarProgramTests(unittest.TestCase):
    def test_unmodified_external_program_complete_proof(self):
        path = ROKU_CORPUS / 'day_of_the_week.sas'
        if not path.is_file(): self.skipTest('Roku corpus not present')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), SOURCE_SHA)
        result, printed = execute(path.read_text())
        expected = {'datasets': {}, 'log': [str(year) + ' ' for year in YEARS]}
        self.assertEqual(result, expected)
        self.assertEqual(hashlib.sha256(printed.encode()).hexdigest(), STDOUT_SHA)
        self.assertEqual(hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':')).encode()).hexdigest(), RESULT_SHA)
        independent, final_index = program_records(path)
        self.assertEqual(result['log'], independent)
        self.assertEqual(final_index, 2122)
        self.assertEqual(len(independent), 17)
        job = build_job(path.read_text())
        self.assertEqual(job.code, 0)
        self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.receipt['source_sha256'], SOURCE_SHA)
        self.assertEqual(job.receipt['tickets'], [])
        self.assertEqual(job.result, result)
        print('VERIFIED corpus: day_of_the_week.sas; source/stdout/complete-result hashes, '
              'shared job and independent base R; no live SAS')


if __name__ == '__main__':
    unittest.main()
