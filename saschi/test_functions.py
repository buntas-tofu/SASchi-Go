"""Behavioral tests for the gate-backed scalar function slice.

Every function wired into the executable slice must name the fixture gate that
proves it, and a function with no gate must stay a ticket. These tests pin both
halves: the wired behavior and the refusal.
"""
import unittest
from datetime import date
from pathlib import Path

from .functions import FUNCTIONS, character_width
from .plan import compile_plan
from .runtime import run_plan

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