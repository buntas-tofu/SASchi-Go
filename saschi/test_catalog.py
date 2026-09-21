"""Tests for saschi.catalog: the DuckDB analysis layer.

DuckDB is already in the gate set; these tests prove the catalog records what
the pipeline hands it and re-derives the completeness accounting as a query,
including the empty-insert edge case and the on-disk round trip.
"""

import tempfile
import unittest
from pathlib import Path

from saschi.catalog import Catalog


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
