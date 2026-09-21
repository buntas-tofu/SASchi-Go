"""Tests for saschi.pipeline: the end-to-end process.

The clean program must translate to complete with zero tickets; a ticketed
program must be blocked. Function recognition and string masking are pinned so
the census cannot quietly start counting literals as calls, and the catalog
round-trip proves the analysis persists what the report reads back.
"""

import tempfile
import unittest
from pathlib import Path

from saschi.pipeline import function_hits, run

CLEAN = (
    "data rounded_values;\n"
    "x = 0.125;\n"
    "y = round(x, 0.01);\n"
    "put x= y=;\n"
    "run;\n"
)

TICKETED = "proc sort data=in; by key; run;\n"


class PipelineTests(unittest.TestCase):
    def test_clean_program_is_complete(self):
        r = run(CLEAN, file="clean.sas")
        c = r.completeness
        self.assertTrue(c.complete)
        self.assertFalse(c.blocked)
        self.assertEqual(c.n_tickets, 0)
        self.assertEqual(c.n_statements, 5)
        self.assertAlmostEqual(c.coverage, 1.0)
        self.assertEqual(r.rule_count, 56)

    def test_function_recognition(self):
        r = run(CLEAN, file="clean.sas")
        self.assertEqual(len(r.functions), 1)
        self.assertEqual(r.functions[0].name, "ROUND")
        self.assertEqual(r.functions[0].construct, "round")
        self.assertEqual(r.functions[0].rule_id, "DS-012")

    def test_ticketed_program_is_blocked(self):
        r = run(TICKETED, file="tick.sas")
        c = r.completeness
        self.assertTrue(c.blocked)
        self.assertFalse(c.complete)
        self.assertGreater(c.n_tickets, 0)
        self.assertLess(c.coverage, 1.0)
        self.assertIn("sort", c.tickets_by_construct)

    def test_string_literal_is_not_a_function(self):
        self.assertEqual(function_hits('x = "round(y, 1)";', 1), [])
        hits = function_hits("x = round(y, 1);", 1)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].name, "ROUND")

    def test_allow_partial_flows_through(self):
        r = run(TICKETED, file="tick.sas", allow_partial=True)
        self.assertIn("PARTIAL", r.translation.code)

    def test_catalog_persists_and_matches(self):
        from saschi.catalog import Catalog
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "p.duckdb")
            r = run(CLEAN, file="clean.sas", catalog_path=path)
            self.assertTrue(r.completeness.complete)
            with Catalog(path) as cat:
                c = cat.completeness()
            self.assertEqual(c.n_statements, r.completeness.n_statements)
            self.assertEqual(c.n_tickets, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
