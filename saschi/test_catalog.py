"""Tests for saschi.catalog: the DuckDB analysis layer.

Two layers of proof. The unit tests pin the catalog's accounting as a query,
including the empty-insert edge case and the on-disk round trip. The pass tests
drive the real path (parser, statement router, compiled plan) and require the
catalog's independent counts to agree with the plan's own verdict, so a
mis-recorded pass cannot look like agreement.
"""

import tempfile
import unittest
from pathlib import Path

from saschi.catalog import Catalog, record_pass
from saschi.plan import compile_plan
from saschi.parser import split_statements

REPO = Path(__file__).resolve().parent.parent


def _fill(cat: Catalog) -> None:
    cat.record_statements([
        (1, "data d", "data-step", "", True),
        (2, "x = round(x, 0.01)", "unknown", "", True),
        (3, "proc sort data=d", "sort", "DS-008", True),
    ])
    cat.record_functions([(2, "ROUND", "round", "DS-012")])
    cat.record_tickets([(3, "sort", "no emitter in slice one")])
    cat.record_run(file="t.sas", target="python", ts_utc="2026-01-01T00:00:00Z",
                   n_statements=3, n_functions=1, n_matched=0, n_tickets=1,
                   blocked=True, tool_git="abc1234")


class CatalogTests(unittest.TestCase):
    def test_completeness_counts(self):
        with Catalog() as cat:
            _fill(cat)
            c = cat.completeness()
        self.assertEqual(c.n_statements, 3)
        self.assertEqual(c.n_routed, 2)
        self.assertEqual(c.n_unrouted, 1)
        self.assertEqual(c.n_functions, 1)
        self.assertEqual(c.n_tickets, 1)
        self.assertEqual(c.n_matched, 0)
        self.assertTrue(c.blocked)
        self.assertEqual(c.tickets_by_construct, {"sort": 1})

    def test_complete_when_not_blocked(self):
        with Catalog() as cat:
            cat.record_run(file="t.sas", target="python",
                           ts_utc="2026-01-01T00:00:00Z", n_statements=0,
                           n_functions=0, n_matched=0, n_tickets=0,
                           blocked=False, tool_git="abc1234")
            c = cat.completeness()
        self.assertTrue(c.complete)
        self.assertFalse(c.blocked)

    def test_coverage_accounts_for_tickets(self):
        with Catalog() as cat:
            cat.record_statements([(1, "a", "unknown", "", True),
                                   (2, "b", "sort", "DS-008", True)])
            cat.record_tickets([(2, "sort", "no emitter")])
            cat.record_run(file="t", target="python", ts_utc="2026-01-01T00:00:00Z",
                           n_statements=2, n_functions=0, n_matched=0,
                           n_tickets=1, blocked=True, tool_git="abc1234")
            c = cat.completeness()
        self.assertAlmostEqual(c.coverage, 0.5)

    def test_empty_inserts_are_noops(self):
        with Catalog() as cat:
            cat.record_statements([])
            cat.record_functions([])
            cat.record_tickets([])
            cat.record_run(file="t", target="python", ts_utc="2026-01-01T00:00:00Z",
                           n_statements=0, n_functions=0, n_matched=0,
                           n_tickets=0, blocked=False, tool_git="abc1234")
            c = cat.completeness()
        self.assertEqual(c.n_statements, 0)
        self.assertEqual(c.n_functions, 0)
        self.assertFalse(c.blocked)

    def test_on_disk_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "catalog.duckdb"
            with Catalog(str(path)) as cat:
                _fill(cat)
            with Catalog(str(path)) as cat:
                c = cat.completeness()
            self.assertEqual(c.n_statements, 3)
            self.assertEqual(c.tickets_by_construct, {"sort": 1})


class PassTests(unittest.TestCase):
    """The catalog's counts against the plan's verdict, on real repo programs."""

    def test_statement_accounting_matches_the_parser(self):
        source = (REPO / "examples" / "workflow" / "job.sas").read_text(
            encoding="utf-8")
        plan = compile_plan(source)
        cat, c = record_pass(source, plan, file="job.sas", git="test")
        try:
            self.assertEqual(c.n_statements, len(split_statements(source)))
            self.assertGreater(c.n_statements, 0)
            self.assertEqual(c.n_tickets, len(plan.tickets))
            self.assertEqual(c.blocked, bool(plan.blocked))
            self.assertTrue(c.complete)
            self.assertAlmostEqual(c.coverage, 1.0)
        finally:
            cat.close()

    def test_blocked_program_reports_its_tickets_by_construct(self):
        source = "data d;\n  set raw;\n  d = count(x);\nrun;\n"
        plan = compile_plan(source)
        self.assertTrue(plan.blocked)
        cat, c = record_pass(source, plan, file="blocked.sas", git="test")
        try:
            self.assertFalse(c.complete)
            self.assertGreater(c.n_tickets, 0)
            self.assertNotEqual(c.coverage, 1.0)
            self.assertEqual(sum(c.tickets_by_construct.values()), c.n_tickets)
        finally:
            cat.close()

    def test_function_recognition_reads_code_not_strings(self):
        source = 'data d;\n  file report;\n  x = "ROUND(1.5)";\n  y = round(x, 1);\nrun;\n'
        plan = compile_plan(source)
        cat, c = record_pass(source, plan, file="strings.sas", git="test")
        try:
            names = cat.functions_seen()
            self.assertIn("ROUND", names)
            self.assertEqual(names.count("ROUND"), 1)
        finally:
            cat.close()

    def test_record_carries_a_status_line(self):
        source = (REPO / "examples" / "workflow" / "job.sas").read_text(
            encoding="utf-8")
        cat, c = record_pass(source, compile_plan(source), git="test")
        try:
            rec = c.as_record()
        finally:
            cat.close()
        self.assertEqual(rec["status"], "recorded")
        self.assertIn("not a live SAS comparison", rec["evidence"])
        for key in ("n_statements", "n_routed", "n_unrouted", "n_functions",
                    "n_tickets", "blocked", "coverage", "tickets_by_construct"):
            self.assertIn(key, rec)

    def test_job_receipt_carries_the_accounting(self):
        from saschi.job import build_job
        source = (REPO / "examples" / "workflow" / "job.sas").read_text(
            encoding="utf-8")
        job = build_job(source)
        block = job.receipt["completeness"]
        self.assertEqual(block["status"], "recorded")
        self.assertEqual(block["n_statements"], len(split_statements(source)))
        self.assertEqual(block["n_tickets"], len(job.plan.tickets))
        self.assertEqual(block["blocked"], job.plan.blocked)


if __name__ == "__main__":
    unittest.main(verbosity=2)
