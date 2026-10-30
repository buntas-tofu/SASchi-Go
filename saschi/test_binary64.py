"""DS-049/050/051 scalar binary64 and independent-plan refusal controls."""
from copy import deepcopy
import contextlib
import io
import math
import sys
import unittest

from sas_semantics import sas_divide, sas_int, sas_multiply, sas_sum_statement
from .binary64 import (PROFILE, apply, arithmetic, evaluate, numeric,
                       render_numeric_list, validate_step)
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan


def atom(value):
    return {'kind': 'missing' if value is None else 'number', 'value': value}


def call(name, arg):
    return {'kind': 'call', 'name': name, 'args': [arg]}


def binary(op, left, right):
    return {'kind': 'arithmetic', 'op': op, 'left': left, 'right': right}


def operation(kind, args):
    return {'kind': kind, 'line': 1, 'args': args}


def step(value=None):
    return {'kind': 'data', 'name': 'd', 'line': 1, 'inputs': [], 'by': [],
            'where': None, 'nodupkey': False, 'retained': {}, 'lengths': {},
            'display_names': {}, 'operations': [
                operation('numeric_profile', {'name': PROFILE}),
                operation('assign', {'name': 'x', 'value': value or call('atan', atom(1))})]}


class Binary64Tests(unittest.TestCase):
    def test_automatic_iteration_name_display_metadata_matches_expression_scope(self):
        for source, values in (
            ('data d;t=atan(1);x=_n_;run;', {'x':1.}),
            ('data d;t=atan(1);if _n_=1 then x=2;run;', {'x':2.}),
            ('data d;t=atan(1);total+_n_;run;', {'total':1.}),
        ):
            plan = compile_plan(source)
            self.assertFalse(plan.blocked, plan.tickets)
            row = run_plan(plan.to_dict())['datasets']['d']['rows'][0]
            for name, value in values.items():
                self.assertEqual(row[name], value)
            self.assertNotIn('_n_', row)

    def test_numeric_domain_and_zero_normalization(self):
        for value in (None, 0, -0., 1, -1., 2147483647, -2147483647, sys.float_info.min):
            with self.subTest(value=value):
                self.assertEqual(numeric(value), value)
        self.assertEqual(math.copysign(1, numeric(-0.)), 1)
        for value in (True, '1', {'missing': 'A'}, math.nan, math.inf, -math.inf,
                      2147483648, 10 ** 1000, math.ulp(0.), sys.float_info.min / 2):
            with self.subTest(value=str(value)[:40]), self.assertRaises(ValueError):
                numeric(value)

    def test_rounded_arithmetic_has_explicit_separate_helpers(self):
        self.assertEqual(arithmetic('/', 1, 3), 1 / 3)
        self.assertEqual(arithmetic('*', 1.1, 1.1), 1.1 * 1.1)
        self.assertEqual(arithmetic('+', .1, .2), .1 + .2)
        self.assertEqual(arithmetic('-', .3, .2), .3 - .2)
        for helper, args in ((sas_divide, (1, 3)), (sas_multiply, (1.1, 1.1))):
            with self.assertRaises(ValueError):
                helper(*args)

    def test_power_bounds_and_domains(self):
        for left, right, want in ((2, 3, 8.), (-2, 3, -8.), (-2, 2, 4.),
                                  (3, 0, 1.), (0, 1, 0.), (2, 30, 1073741824.)):
            self.assertEqual(arithmetic('**', left, right), want)
        for left, right in ((0, 0), (1, -1), (1, 33), (4, .5), (2, 31), (1e-10, 32)):
            with self.subTest(left=left, right=right), self.assertRaises(ValueError):
                arithmetic('**', left, right)

    def test_invalid_operands_cannot_hide_behind_missing_or_zero(self):
        for op in ('+', '-', '*', '/', '**'):
            self.assertIsNone(arithmetic(op, None, 2))
            self.assertIsNone(arithmetic(op, 2, None))
            for left, right in ((None, 2147483648), (2147483648, None),
                                (0, True), ('1', 0), ({'missing': 'A'}, None)):
                with self.subTest(op=op, left=left, right=right), self.assertRaises(ValueError):
                    arithmetic(op, left, right)
        for left, right in ((1, 0), (None, 0), (0, 0)):
            with self.assertRaises(ValueError):
                arithmetic('/', left, right)
        with self.assertRaises(ValueError):
            arithmetic('**', None, .5)

    def test_overflow_subnormal_and_nonzero_underflow_refuse(self):
        for op, left, right in (('+', 2147483647, 1), ('*', 46341, 46341),
                                ('/', 2147483647, .5), ('*', sys.float_info.min, .5),
                                ('/', sys.float_info.min, 2147483647),
                                ('*', sys.float_info.min, sys.float_info.min)):
            with self.subTest(op=op), self.assertRaises(ValueError):
                arithmetic(op, left, right)
        self.assertEqual(arithmetic('-', sys.float_info.min, sys.float_info.min), 0.)

    def test_constant_trig_and_legacy_int_contracts(self):
        for value in ('pi', 'PI', 'Pi'):
            self.assertEqual(apply('constant', [value]), math.pi)
        for name, value, want in (('sin', math.pi / 6, .5), ('cos', 0, 1),
                                  ('tan', math.pi / 4, 1), ('arsin', 1, math.pi / 2),
                                  ('arcos', -1, math.pi), ('atan', 1, math.pi / 4)):
            self.assertAlmostEqual(apply(name, [value]), want, places=15)
            self.assertIsNone(apply(name, [None]))
        self.assertEqual(apply('int', [2.5]), sas_int(2.5))
        for name, values in (('constant', ['e']), ('constant', [None]), ('constant', ['pi ']),
                             ('sin', [math.nextafter(math.pi, math.inf)]), ('cos', [-4]),
                             ('tan', [math.pi / 2]), ('arsin', [1.001]), ('arcos', [-1.001]),
                             ('int', [1.0000000000001]), ('int', [None]), ('atan', [True]),
                             ('sum', [1]), ('atan', []), ('atan', [1, 2]), ([], [1])):
            with self.subTest(name=name, values=values), self.assertRaises(ValueError):
                apply(name, values)

    def test_retained_rounded_series_and_expression_evaluation(self):
        expr = binary('/', atom(1), binary('**', {'kind': 'variable', 'value': 'n'}, atom(2)))
        total = 0.
        for n in range(1, 1001):
            total = numeric(sas_sum_statement(total, evaluate(expr, {'n': float(n)})))
        self.assertEqual(total, 1.6439345666815615)
        error = arithmetic('-', total, arithmetic('/', arithmetic('**', math.pi, 2), 6))
        self.assertEqual(error, -0.0009995001666649461)
        self.assertEqual(render_numeric_list([total, error]), '1.6439345667 -0.0009995 ')

    def test_fixed_decimal_records_and_legacy_integer_fields(self):
        self.assertEqual(render_numeric_list([None, -0., 99999999999]), '. 0 99999999999 ')
        self.assertEqual(render_numeric_list([.5, -.25, math.pi]), '0.5 -0.25 3.1415926536 ')
        self.assertEqual(render_numeric_list([1e-4, -1e-4]), '0.0001 -0.0001 ')
        self.assertEqual(render_numeric_list([0] * 32), '0 ' * 32)
        for values in ([], [True], ['1'], [{'missing': 'A'}], [math.nan], [math.inf],
                       [1e-5], [1e9 + .25], [1e12], [9.99999999999], [0] * 33):
            with self.subTest(values=str(values)[:50]), self.assertRaises(ValueError):
                render_numeric_list(values)

    def test_decimal_midpoints_and_guard_neighborhood_refuse(self):
        midpoint = 1.23456789005
        for value in (midpoint, math.nextafter(midpoint, 0), math.nextafter(midpoint, math.inf)):
            with self.assertRaises(ValueError):
                render_numeric_list([value])
        safe = midpoint
        for _ in range(20):
            safe = math.nextafter(safe, math.inf)
        self.assertEqual(render_numeric_list([safe]), '1.2345678901 ')

    def test_exact_profile_declaration_and_old_unmarked_steps(self):
        self.assertTrue(validate_step(step()))
        original = step(atom(1))
        original['operations'].pop(0)
        self.assertFalse(validate_step(original))
        missing = step(); missing['operations'].pop(0)
        with self.assertRaises(ValueError):
            validate_step(missing)
        for version in (1, 3, '2'):
            with self.assertRaises(ValueError):
                validate_step(step(), version)
        for mutate in (
                lambda s: s['operations'][0]['args'].update(name='other'),
                lambda s: s['operations'][0].update(line=True),
                lambda s: s['operations'].reverse(),
                lambda s: s['operations'].append(deepcopy(s['operations'][0])),
                lambda s: s['operations'][1]['args'].update(value=atom(1))):
            s = step(); mutate(s)
            with self.assertRaises(ValueError):
                validate_step(s)

    def test_static_dead_branch_and_dynamic_laziness(self):
        invalid = operation('assign', {'name': 'bad', 'value': binary('/', atom(1), atom(0))})
        s = step()
        s['operations'].append(operation('if', {'condition': {'op': 'truth', 'left': atom(0)}, 'operation': invalid}))
        with self.assertRaises(ValueError):
            validate_step(s)
        dynamic = binary('/', atom(1), {'kind': 'variable', 'value': 'denominator'})
        s['operations'][-1]['args']['operation']['args']['value'] = dynamic
        self.assertTrue(validate_step(s))
        with self.assertRaises(ValueError):
            evaluate(dynamic, {'denominator': 0.})
        self.assertTrue(validate_step(s, schema={'denominator': 'number'}))
        with self.assertRaises(ValueError):
            validate_step(s, schema={'denominator': {'type': 'character', 'length': 1}})

    def test_static_zero_trip_and_integer_controls(self):
        invalid = operation('assign', {'name': 'bad', 'value': call('arsin', atom(2))})
        loop = operation('do_counted', {'index': 'i', 'start': 1, 'stop': 0, 'by': 1, 'body': [invalid]})
        s = step(); s['operations'].append(loop)
        with self.assertRaises(ValueError):
            validate_step(s)
        loop['args']['body'][0]['args']['value'] = call('arsin', {'kind': 'variable', 'value': 'y'})
        self.assertTrue(validate_step(s))
        bounded = {'index': 'i', 'start': atom(1), 'stop': atom(3), 'by': atom(1), 'profile': 'bounded', 'body': []}
        s['operations'][-1]['args'] = bounded
        self.assertTrue(validate_step(s))
        bounded['stop'] = binary('**', atom(2), atom(2))
        with self.assertRaises(ValueError):
            validate_step(s)

    def test_profile_rejects_unproved_data_and_operation_compositions(self):
        for key, value in (('kind', 'merge'), ('inputs', ['raw']), ('lengths', {'c': 2}),
                           ('where', {'left': atom(1), 'op': 'truth'}), ('by', ['x'])):
            s = step(); s[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_step(s)
        for kind in ('put_all', 'put_mixed_numeric', 'put_literal', 'projection', 'do_while', 'array_set', 'lookup'):
            s = step(); s['operations'].append(operation(kind, {}))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validate_step(s)

    def test_forged_nodes_domains_metadata_and_budgets_refuse(self):
        values = [call('sum', atom(1)), call('constant', {'kind': 'variable', 'value': 'pi'}),
                  call('constant', {'kind': 'character', 'value': 'e'}),
                  {'kind': 'tagged_missing', 'value': {'missing': 'A'}},
                  {'kind': 'number', 'value': True}, {'kind': 'number', 'value': 5e-324},
                  {'kind': 'automatic', 'value': '_error_'}, {'kind': 'variable', 'value': '_n_'},
                  binary('^', atom(1), atom(2)), binary('**', {'kind': 'variable', 'value': 'a'}, atom(.5)),
                  call('atan', atom(1)) | {'extra': True}, call('atan', atom(1)) | {'name': []}]
        for expr in values:
            s = step(); s['operations'].append(operation('assign', {'name': 'y', 'value': expr}))
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                validate_step(s)
        s = step()
        for _ in range(129):
            s['operations'].append(operation('assign', {'name': 'a', 'value': call('atan', atom(1))}))
        with self.assertRaises(ValueError):
            validate_step(s)
        nested = atom(1)
        for _ in range(33):
            nested = binary('+', nested, atom(1))
        s = step(); s['operations'].append(operation('assign', {'name': 'y', 'value': nested}))
        with self.assertRaises(ValueError):
            validate_step(s)

    def test_cycles_nested_declarations_and_deep_forged_wrappers_refuse(self):
        s = step(); s['display_names']['cycle'] = s
        with self.assertRaises(ValueError):
            validate_step(s)
        s = step(); s['display_names']['nested'] = deepcopy(s['operations'][0])
        with self.assertRaises(ValueError):
            validate_step(s)
        s = step(); s['display_names']['nested'] = s['operations'][0]
        with self.assertRaises(ValueError):
            validate_step(s)
        wrapper = []
        for _ in range(260):
            wrapper = [wrapper]
        s = step(); s['display_names']['deep'] = wrapper
        with self.assertRaises(ValueError):
            validate_step(s)

    def test_plan_validation_does_not_mutate_plan_or_schema(self):
        s, schema = step(), {'x': {'type': 'number', 'length': 8}}
        before = deepcopy((s, schema))
        self.assertTrue(validate_step(s, schema=schema))
        self.assertEqual((s, schema), before)

    def test_source_power_precedence_and_new_profile_provenance(self):
        for text, want in (('2**3**2', 512.), ('-2**2', -4.), ('(-2)**2', 4.),
                           ('2*3**2', 18.), ('2**3*2', 16.), ('-2**2*2', -8.),
                           ('2**+2', 4.), ('2**2**0', 2.), ('2 ** 3 ** 2', 512.)):
            with self.subTest(text=text):
                plan = compile_plan('data d;x=' + text + ';run;')
                self.assertFalse(plan.blocked, plan.tickets)
                self.assertEqual(plan.to_dict()['steps'][0]['operations'][0],
                                 operation('numeric_profile', {'name': PROFILE}))
                self.assertEqual(run_plan(plan.to_dict())['datasets']['d']['rows'], [{'x': want}])
        for text in ('2***3', '2****3', '2//3', '2^3', '2**-1'):
            self.assertTrue(compile_plan('data d;x=' + text + ';run;').blocked)

    def test_legacy_plans_and_exact_refusals_remain_unmarked(self):
        rounded = compile_plan('data d;t=atan(1);x=1.1*1.1;y=1/3;run;')
        self.assertFalse(rounded.blocked, rounded.tickets)
        self.assertIn('DS-049', {rule for _, rule, _ in rounded.matched})
        self.assertFalse({'DS-036', 'DS-045'} & {rule for _, rule, _ in rounded.matched})
        for expr in ('8/2', '1/3', '1.1*1.1', 'int(1.0000000000001)'):
            plan = compile_plan('data d;x=' + expr + ';run;')
            self.assertNotIn('numeric_profile', [op.kind for op in plan.steps[0].operations])
            if expr != '8/2':
                with self.assertRaises(ValueError):
                    run_plan(plan.to_dict())
        self.assertEqual(compile_plan('data d;x=1;put x;run;').to_dict()['steps'][0]['operations'][-1]['args'],
                         {'names': ['x']})
        # Introducing callable names must not reserve previously admitted arrays.
        plan = compile_plan('data d;array sin a b;a=1;b=2;run;')
        self.assertFalse(plan.blocked, plan.tickets)

    def test_source_static_failures_even_when_skipped(self):
        for expr in ('1/0', 'arsin(2)', 'arcos(-2)', 'tan(2)', 'int(1.0000000000001)',
                     '0**0', '2**.5', "constant('e')", '1e-300*1e-100'):
            for body in ('bad=' + expr + ';', 'if 0 then bad=' + expr + ';',
                         'do i=1 to 0;bad=' + expr + ';end;'):
                with self.subTest(body=body):
                    plan = compile_plan('data d;t=atan(1);' + body + 'run;')
                    self.assertTrue(plan.blocked)

    def test_source_dynamic_laziness_and_counted_scheduling(self):
        source = ('data d;t=atan(1);x=2;if 0 then bad=arsin(x);'
                  'do i=1 to 0;other=arsin(x);end;output;run;')
        plan = compile_plan(source)
        self.assertFalse(plan.blocked, plan.tickets)
        row = run_plan(plan.to_dict())['datasets']['d']['rows'][0]
        self.assertEqual((row['bad'], row['other'], row['i']), (None, None, 1.))
        source = ('data d;t=atan(1);do i=1 to 3;total+1/i**2;'
                  'if i>1 then output;end;put total;run;')
        result = run_plan(compile_plan(source).to_dict())
        self.assertEqual([r['i'] for r in result['datasets']['d']['rows']], [2., 3.])
        self.assertEqual([r['total'] for r in result['datasets']['d']['rows']], [1.25, 1.3611111111111112])
        self.assertEqual(result['log'], ['1.3611111111 '])

    def test_source_conditions_missing_order_and_ordinary_missing_sum(self):
        source = ('data d;t=atan(1);m=.;if m<0 then x=sin(0.5);'
                  'if . then bad=1;else good=2;total+.;total+1/3;output;run;')
        plan = compile_plan(source)
        self.assertFalse(plan.blocked, plan.tickets)
        row = run_plan(plan.to_dict())['datasets']['d']['rows'][0]
        self.assertEqual((row['bad'], row['good'], row['total']), (None, 2., 1 / 3))
        self.assertEqual(row['x'], math.sin(.5))

    def test_runtime_failure_discards_prior_rows_and_buffered_stdout(self):
        prefix = 'data first;x=1;put x;run;'
        for suffix in ('data d;t=atan(1);x=0;y=1/x;run;',
                       'data d;t=atan(1);x=2;y=arsin(x);run;',
                       'data d;t=atan(1);x=2147483647;total+x;total+1;run;',
                       'data d;t=atan(1);x=0.00001;put x;run;'):
            source = prefix + suffix
            job = build_job(source)
            self.assertNotEqual(job.code, 0)
            self.assertFalse(job.receipt['accepted'])
            self.assertIsNone(job.result)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(ValueError):
                exec(translate(source).code, {})
            self.assertEqual(out.getvalue(), '')

    def test_forged_unmarked_stale_and_nested_profile_plans_refuse(self):
        source = 'data d;x=atan(1);run;'
        original = compile_plan(source).to_dict()
        for mutate in (
                lambda s: s['operations'].pop(0),
                lambda s: s['operations'][0]['args'].update(name='binary64-v2'),
                lambda s: s['operations'].append(deepcopy(s['operations'][0])),
                lambda s: s['operations'][1]['args'].update(value=atom(1))):
            p = deepcopy(original); mutate(p['steps'][0])
            with self.assertRaises(ValueError):
                run_plan(p, allow_partial=True)
        plan = compile_plan('data d;x=1*2;run;').to_dict()
        plan['steps'][0]['operations'][0]['args']['value']['op'] = '**'
        with self.assertRaises(ValueError):
            run_plan(plan)
        plan = compile_plan('data d;x=1/3;run;').to_dict()
        s = plan['steps'][0]
        s['operations'].insert(0, operation('numeric_profile', {'name': PROFILE}))
        s['display_names']['junk'] = call('atan', atom(1))
        with self.assertRaises(ValueError):
            run_plan(plan)
        s['display_names'].pop('junk')
        s['metadata'] = call('atan', atom(1))
        with self.assertRaises(ValueError):
            run_plan(plan)

    def test_deep_source_calls_ticket_before_recursion(self):
        source = 'data d;x=' + 'atan(' * 1000 + '1' + ')' * 1000 + ';run;'
        plan = compile_plan(source)
        self.assertTrue(plan.blocked)
        self.assertTrue(any('32' in ticket.reason for ticket in plan.tickets))

    def test_profile_and_legacy_steps_reset_without_input_mutation(self):
        source = ('data first;do i=1 to 2;total+1/i**2;end;put total;run;'
                  'data second;x=atan(1);put x;run;'
                  'data third;n=7;put n;run;')
        plan = compile_plan(source).to_dict(); before = deepcopy(plan)
        one = run_plan(plan)
        self.assertEqual(one, run_plan(plan))
        self.assertEqual(plan, before)
        self.assertEqual(one['log'], ['1.25 ', '0.7853981634 ', '7 '])


if __name__ == '__main__':
    unittest.main()
