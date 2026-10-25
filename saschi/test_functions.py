"""Behavioral tests for the gate-backed scalar function slice.

Every function wired into the executable slice must name the fixture gate that
proves it, and a function with no gate must stay a ticket. These tests pin both
halves: the wired behavior and the refusal.
"""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from .functions import FUNCTIONS, character_width
from .plan import compile_plan
from .runtime import run_plan
from .emit_py import translate
from .emit_cpp import translate as translate_cpp
from .job import build_job
from .rules import load_rulebook, route_function

REPO = Path(__file__).resolve().parent.parent


def execute(source, inputs=None):
    plan = compile_plan(source)
    if plan.blocked:
        raise AssertionError(plan.tickets)
    return run_plan(plan.to_dict(), inputs)


def one(source, inputs=None):
    return execute(source, inputs)["datasets"][
        "d" if "data d" in source.lower() else "e"]["rows"][0]


class RegistryProvenanceTests(unittest.TestCase):
    def test_every_wired_function_names_an_existing_gate(self):
        for name, spec in FUNCTIONS.items():
            with self.subTest(function=name):
                self.assertTrue(spec.gate, f"{name} has no gate named")
                self.assertTrue((REPO / spec.gate).is_file(), f"{name}: {spec.gate} missing")

    def test_registry_is_unique_and_lowercase(self):
        self.assertEqual(len(FUNCTIONS), len({k.lower() for k in FUNCTIONS}))


class CharacterFunctionTests(unittest.TestCase):
    def test_substr_is_one_based(self):
        row = one("data d; x=substr('abcde',2,3); run;")
        self.assertEqual(row["x"], "bcd")

    def test_substr_past_the_end_returns_what_exists(self):
        # SAS fixes the result width at the third argument and pads, so the
        # stored value carries the blanks and LENGTH() still reports 2.
        row = one("data d; x=substr('abcde',4,10); n=length(x); run;")
        self.assertEqual(row["x"], "de".ljust(10))
        self.assertEqual(row["n"], 2.0)

    def test_substr_declares_the_declared_width_not_the_source(self):
        plan = compile_plan("data d; x=substr('abcde',2,3); run;")
        self.assertEqual(character_width(plan.steps[0].operations[0].args["value"]), 3)

    def test_length_excludes_trailing_blanks_and_floors_at_one(self):
        row = one("data d; a=length('abc  '); b=length('   '); c=lengthn('   '); "
                  "e=lengthc('abc  '); run;")
        self.assertEqual((row["a"], row["b"], row["c"], row["e"]), (3.0, 1.0, 0.0, 5.0))

    def test_numeric_length_family_uses_right_justified_best12(self):
        row = one('data d; a=length(uninitialized); b=lengthn(.A); c=lengthc(3.125); run;')
        self.assertEqual(row, {'a': 12., 'uninitialized': None, 'b': 12., 'c': 12.})

    def test_put_numeric_format_is_gate_backed(self):
        row = one("data d; x=put(1.5,8.2); run;")
        self.assertEqual(row["x"], "1.50".rjust(8))

    def test_put_date9_from_a_sas_day_number(self):
        row = one("data d; x=put(0,date9.); run;")
        self.assertEqual(row["x"], "01JAN1960")

    def test_input_reads_character_to_numeric(self):
        row = one("data d; x=input('  42  '); run;")
        self.assertEqual(row["x"], 42.0)

    def test_input_yymmdd8_reads_a_sas_day_number(self):
        row = one("data d; x=input('20260101',yymmdd8.); run;")
        self.assertEqual(row["x"], float((date(2026, 1, 1) - date(1960, 1, 1)).days))


class CountFunctionTests(unittest.TestCase):
    def test_original_ticket_executes_in_emitted_python(self):
        source = "data _null_; x=count('abc','a'); run;"
        translation = translate(source)
        self.assertFalse(translation.blocked)
        namespace = {}
        exec(translation.code, namespace)
        self.assertEqual(namespace['result']['log'], [])
        row = one("data d; x=count('abc','a'); run;")
        self.assertEqual(row['x'], 1.0)
        job = build_job(source)
        self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.receipt['tickets'], [])

    def test_case_and_trimming_discriminators(self):
        row = one("data d; a=count('abc','A'); b=count('abc','A','i'); "
                  "c=count('abc','abc '); d=count('abc','abc ','T'); "
                  "e=count('ab ','b '); f=count('ab ','b ','T'); "
                  "g=count(' Ab AB ','ab ','It'); run;")
        self.assertEqual(tuple(row.values()), (0., 1., 0., 1., 1., 1., 2.))

    def test_typed_catalog_preserves_blanks_and_accepts_variable_modifiers(self):
        inputs = {'raw': {'schema': {'text': {'type': 'character', 'length': 2},
                                     'needle': {'type': 'character', 'length': 2},
                                     'mod': {'type': 'character', 'length': 1}},
                          'rows': [{'text': 'ab', 'needle': 'b', 'mod': 't'}]}}
        result = execute("data d; set raw; a=count(text,needle); "
                         "b=count(text,needle,mod); run;", inputs)
        row = result['datasets']['d']['rows'][0]
        self.assertEqual(row['needle'], 'b ')
        self.assertEqual((row['a'], row['b']), (0., 1.))

    def test_missing_character_variable_is_padded_not_numeric_missing(self):
        inputs = {'raw': {'schema': {'text': {'type': 'character', 'length': 3}},
                          'rows': [{'text': ''}]}}
        row = execute("data d; set raw; a=count(text,' '); b=count(text,'x'); run;",
                      inputs)['datasets']['d']['rows'][0]
        self.assertEqual((row['a'], row['b']), (3., 0.))

    def test_calls_compose_with_expressions_and_predicates(self):
        row = one("data d; a=count(substr('zabc',2,3),'a')+1; "
                  "b=max(count('abab','ab'),1); c=0; "
                  "if count('Aa','a','I')=2 then c=7; run;")
        self.assertEqual(tuple(row.values()), (2., 2., 7.))

    def test_overlap_and_ungated_inputs_fail_without_an_accepted_job(self):
        cases = [("count('aaa','aa')", 'overlapping'),
                 ("count('AaA','aa','I')", 'overlapping'),
                 ("count('abc','')", 'empty substring'),
                 ("count('abc',' ','T')", 'empty substring'),
                 ("count('','a')", 'zero-length string'),
                 ("count('abc','a','x')", 'unsupported modifier'),
                 ("count('café','é')", 'encoding review'),
                 ("count(123,'1')", 'character arguments'),
                 ("count(.,'a')", 'character arguments')]
        for expression, reason in cases:
            with self.subTest(expression=expression):
                job = build_job(f"data d; x={expression}; run;")
                self.assertFalse(job.receipt['accepted'])
                self.assertIsNone(job.result)
                self.assertIn(reason, job.receipt['error'])

    def test_dynamic_overlap_cannot_emit_a_partial_dataset(self):
        inputs = {'raw': {'schema': {'text': {'type': 'character', 'length': 3}},
                          'rows': [{'text': 'abc'}, {'text': 'aaa'}]}}
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            execute("data d; set raw; n=count(text,'aa'); output; run;", inputs)

    def test_wrong_arities_and_other_count_functions_remain_tickets(self):
        for call in ("count()", "count('a')", "count('a','a','i','t')",
                     "countc('abc','a')", "countw('a b')"):
            with self.subTest(call=call):
                self.assertTrue(compile_plan(f"data d; x={call}; run;").blocked)

    def test_rule_and_gate_provenance_are_specific_to_count(self):
        self.assertEqual(route_function("count('abc','a')"), ('count', 'DS-022'))
        self.assertEqual(route_function("'count(abc,a)'"), ('unknown', ''))
        self.assertEqual(FUNCTIONS['count'].gate, 'examples/verify_count.py')
        rule = load_rulebook()['DS-022']
        self.assertIn('sas_semantics.sas_count', rule.python_target['pattern'])
        self.assertIn('examples/verify_count.py', rule.validation_test)
        self.assertIn('undefined', ' '.join(rule.required_settings))

    def test_cpp_pilot_still_refuses_character_function_calls(self):
        source = "data _null_; x=count('abc','a'); run;"
        self.assertTrue(translate_cpp(source).blocked)
        job = build_job(source, target='cpp')
        self.assertFalse(job.receipt['accepted'])
        self.assertIsNone(job.result)
        self.assertTrue(job.plan.blocked)
        self.assertEqual(job.code, 2)
        self.assertTrue(any(t['construct'] == 'cpp-target' for t in job.receipt['tickets']))


class ModFunctionTests(unittest.TestCase):
    def test_signs_exact_division_and_boundary_execute_in_emitted_python(self):
        source = ("data d; a=mod(7,3); b=mod(-7,3); c=MOD(7,-3); d=mod(-7,-3); "
                  "e=mod(0,-3); f=mod(-12,3); g=mod(9007199254740992,3); "
                  "h=mod(-9007199254740992,3); i=mod(9007199254740991,9007199254740992); "
                  "j=mod(9007199254740992,9007199254740991); run;")
        translation = translate(source)
        self.assertFalse(translation.blocked)
        namespace = {}
        exec(translation.code, namespace)
        row = namespace['result']['datasets']['d']['rows'][0]
        self.assertEqual(tuple(row.values()),
                         (1., -1., 1., -1., 0., 0., 2., -2., 9007199254740991., 1.))
        job = build_job(source)
        self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.receipt['tickets'], [])
        self.assertEqual(job.result, namespace['result'])

    def test_calls_compose_with_expressions_predicates_and_variables(self):
        row = one("data d; a=-7; b=-3; x=mod(a,b)+2; "
                  "y=mod(max(7,2)+1,3); z=mod(mod(-20,7),4); "
                  "flag=0; if mod(a,b)=-1 then flag=1; run;")
        self.assertEqual((row['x'], row['y'], row['z'], row['flag']), (1., 2., -2., 1.))

    def test_typed_numeric_catalog_preserves_signs(self):
        inputs = {'raw': {'schema': {'a': 'number', 'b': 'number'},
                          'rows': [{'a': -7, 'b': 3}, {'a': 7, 'b': -3}]}}
        result = execute("data d; set raw; x=mod(a,b); run;", inputs)
        self.assertEqual([row['x'] for row in result['datasets']['d']['rows']], [-1., 1.])

    def test_unsupported_domain_does_not_accept_a_job(self):
        cases = [("mod(7,0)", 'zero divisor'), ("mod(0,0)", 'zero divisor'),
                 ("mod(7,-0)", 'zero divisor'), ("mod(.,3)", 'missing or structured'),
                 ("mod(7,.A)", 'missing or structured'), ("mod(._,3)", 'missing or structured'),
                 ("mod(7.5,3)", 'fractional'), ("mod(7,.5)", 'fractional'),
                 ("mod(.3,-.1)", 'fractional'), ("mod(.9,.3)", 'fractional'),
                 ("mod(9007199254740994,3)", 'exact-integer bound'),
                 ("mod(7,-9007199254740994)", 'exact-integer bound'),
                 ("mod('7',3)", 'numeric arguments'), ("mod(7,'3')", 'numeric arguments')]
        for expression, reason in cases:
            with self.subTest(expression=expression):
                job = build_job(f"data d; x={expression}; run;")
                self.assertFalse(job.receipt['accepted'])
                self.assertIsNone(job.result)
                self.assertEqual(job.code, 1)
                self.assertIn(reason, job.receipt['error'])

    def test_later_dynamic_refusal_cannot_accept_a_partial_dataset(self):
        source = "data d; set raw; x=mod(a,b); output; run;"
        for invalid in (0, 0.5, None, {'missing': 'A'}, 9007199254740994):
            with self.subTest(invalid=invalid):
                inputs = {'raw': {'schema': {'a': 'number', 'b': 'number'},
                                  'rows': [{'a': 7, 'b': 3}, {'a': 7, 'b': invalid}]}}
                with self.assertRaisesRegex(ValueError, 'MOD:'):
                    execute(source, inputs)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / 'inputs.json'
                    path.write_text(json.dumps(inputs))
                    job = build_job(source, inputs=path)
                self.assertFalse(job.receipt['accepted'])
                self.assertIsNone(job.result)
                self.assertEqual(job.code, 1)

    def test_wrong_arities_and_ungated_related_functions_remain_tickets(self):
        for call in ('mod()', 'mod(7)', 'mod(7,3,2)', 'int(-2.7)', 'modz(7,3)'):
            with self.subTest(call=call):
                self.assertTrue(compile_plan(f'data d; x={call}; run;').blocked)
        self.assertNotIn('int', FUNCTIONS)
        self.assertNotIn('modz', FUNCTIONS)

    def test_rule_and_gate_provenance_describe_only_bounded_mod(self):
        self.assertEqual(route_function('x=MOD(-7,3);'), ('mod-int', 'DS-013'))
        self.assertEqual(route_function("'mod(-7,3)'"), ('unknown', ''))
        self.assertEqual(FUNCTIONS['mod'].gate, 'examples/verify_mod.py')
        rule = load_rulebook()['DS-013']
        self.assertIn('sas_semantics.sas_mod', rule.python_target['pattern'])
        self.assertIn('examples/verify_mod.py', rule.validation_test)
        self.assertIn('2**53', ' '.join(rule.required_settings))
        self.assertIn('INT', ' '.join(rule.required_settings))

    def test_cpp_pilot_still_refuses_mod_calls(self):
        source = 'data _null_; x=mod(-7,3); put x=; run;'
        self.assertTrue(translate_cpp(source).blocked)
        job = build_job(source, target='cpp')
        self.assertFalse(job.receipt['accepted'])
        self.assertIsNone(job.result)
        self.assertTrue(job.plan.blocked)
        self.assertEqual(job.code, 2)
        self.assertTrue(any(t['construct'] == 'cpp-target' for t in job.receipt['tickets']))


class NumericFunctionTests(unittest.TestCase):
    def test_max_and_min_ignore_missing_arguments(self):
        inputs = {"d": {"schema": {"a": "number"}, "rows": [{"a": None}]}}
        row = one("data e; set d; y=max(a,7); z=min(a,7); run;", inputs)
        self.assertEqual((row["y"], row["z"]), (7.0, 7.0))

    def test_sum_function_ignores_missing_where_the_operator_propagates(self):
        inputs = {"d": {"schema": {"a": "number"}, "rows": [{"a": None}]}}
        row = one("data e; set d; y=sum(a,2); z=a+2; run;", inputs)
        self.assertEqual(row["y"], 2.0)
        self.assertIsNone(row["z"])

    def test_arithmetic_accepts_call_operands(self):
        row = one("data d; x=max(1,2)+3; run;")
        self.assertEqual(row["x"], 5.0)

    def test_calls_nest(self):
        row = one("data d; x=length(substr('abcdef',2,4)); run;")
        self.assertEqual(row["x"], 4.0)

    def test_calls_work_inside_a_predicate(self):
        row = one("data d; x=1; if length('ab  ')=2 then x=9; run;")
        self.assertEqual(row["x"], 9.0)

    def test_substr_without_a_length_literal_stays_a_ticket(self):
        plan = compile_plan("data d; x=substr('abcdef',2); run;")
        self.assertTrue(plan.blocked)
        self.assertIn(plan.tickets[0].construct, {"assignment", "char-funcs"})

    def test_format_outside_the_gated_set_stays_a_ticket(self):
        plan = compile_plan("data d; x=put(1.5,best12.); run;")
        self.assertTrue(plan.blocked)
        self.assertIn(plan.tickets[0].construct, {"assignment", "char-funcs"})

    def test_arities_are_enforced(self):
        for source in ("data d; x=max(); run;", "data d; x=substr('abc',2,3,4); run;",
                       "data d; x=put(1.5); run;"):
            with self.subTest(source=source):
                self.assertTrue(compile_plan(source).blocked)

    def test_function_without_a_gate_stays_a_ticket(self):
        plan = compile_plan("data d; x=upcase('a'); run;")
        self.assertTrue(plan.blocked)
        self.assertEqual(plan.tickets[0].construct, "assignment")
        self.assertIn("unsupported expression", plan.tickets[0].reason)


if __name__ == "__main__":
    unittest.main()
