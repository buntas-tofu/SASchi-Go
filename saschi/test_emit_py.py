"""Tests for saschi.emit_py: translation slice one, the rounding program.

The translation test runs the emitted Python and requires its output to
match the semantics reference, then a frozen pin. A translated program is
accepted because it ran and its numbers matched.

Run: python -m unittest saschi.test_emit_py -v
"""

import contextlib
import io
import unittest
from pathlib import Path

from sas_semantics import sas_round
from saschi.emit_py import translate

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "examples" / "pgm" / "rounding_program.sas"
FROZEN_OUTPUT = "r1=0.30000000000000004 r2=10 r3=-3 r4=0.13"


def _run(code: str) -> str:
    namespace = {"__name__": "translated_program"}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, "translated_program.py", "exec"), namespace)
    return buf.getvalue().strip()


class RoundingProgramTests(unittest.TestCase):
    def setUp(self):
        self.translation = translate(FIXTURE.read_text(encoding="utf-8"))

    def test_translates_without_tickets(self):
        self.assertEqual([], self.translation.tickets)

    def test_round_rules_recorded(self):
        self.assertTrue(self.translation.matched)
        for construct, rule_id, _line in self.translation.matched:
            self.assertEqual(construct, "round")
            self.assertEqual(rule_id, "DS-012")
        lines = sorted(line for _c, _r, line in self.translation.matched)
        self.assertEqual(lines, [6, 8, 10, 12])

    def test_emitted_program_runs_and_matches_reference(self):
        reference = " ".join(
            f"r{i}={format(sas_round(x, u), '.17g')}"
            for i, (x, u) in enumerate(
                [(0.25, 0.1), (9.995, 0.01), (-2.5, 1.0), (0.125, 0.01)],
                start=1))
        # The pin guards the reference itself, then the emitted program
        # must equal both: numbers matched, not looked right.
        self.assertEqual(reference, FROZEN_OUTPUT)
        self.assertEqual(_run(self.translation.code), FROZEN_OUTPUT)

    def test_emitted_lines_trace_to_source_lines(self):
        for _c, _r, line in self.translation.matched:
            self.assertIn(f"# SAS line {line}", self.translation.code)


class TicketTests(unittest.TestCase):
    def test_unhandled_function_becomes_ticket_not_code(self):
        t = translate("data _null_; y = lag(x); run;")
        self.assertEqual(len(t.tickets), 1)
        self.assertEqual(t.tickets[0].construct, "lag-dif")
        self.assertIn("TICKET", t.code)
        self.assertNotIn("y =", t.code)

    def test_plain_assignment_emits(self):
        t = translate("data d; x = 1.5; run;")
        self.assertEqual([], t.tickets)
        self.assertIn("x = 1.5", t.code)

    def test_unroutable_statement_becomes_ticket(self):
        t = translate("data _null_; bogus nonsense here; run;")
        self.assertEqual(len(t.tickets), 1)
        self.assertIn("TICKET", t.code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
