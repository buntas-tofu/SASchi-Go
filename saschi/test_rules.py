"""Tests for saschi.rules: loader, construct map, and statement routing.

Runs against the shipped rulebook (docs/sasconversionrulebook.yaml), so
any drift in the canonical file is caught here. Pure stdlib unittest.

Run: python -m unittest saschi.test_rules -v
"""

import unittest
from pathlib import Path

from saschi.rules import (
    CONSTRUCT_MAP,
    MERGE_MANY_TO_MANY_HINT,
    RulebookError,
    family_counts,
    load_rulebook,
    route_function,
    route_statement,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.rules = load_rulebook(REPO_ROOT / "docs" / "sasconversionrulebook.yaml")

    def test_rule_count_is_56(self):
        self.assertEqual(len(self.rules), 56)

    def test_rule_ids_unique(self):
        ids = list(self.rules)
        self.assertEqual(len(ids), len(set(ids)))

    def test_family_counts(self):
        counts = family_counts(self.rules)
        self.assertEqual(counts["DS"], 21)
        self.assertEqual(counts["SQL"], 3)
        self.assertEqual(counts["ST"], 16)
        self.assertEqual(counts["SV"], 6)
        self.assertEqual(counts["MC"], 9)
        self.assertEqual(counts["MX"], 1)

    def test_every_rule_has_core_fields(self):
        for rule in self.rules.values():
            self.assertTrue(rule.sas_pattern, rule.rule_id)
            self.assertTrue(rule.scope, rule.rule_id)
            self.assertTrue(rule.equivalence_class, rule.rule_id)

    def test_no_direct_equivalent_rules_are_tickets(self):
        for rule in self.rules.values():
            if rule.equivalence_class.startswith("NO-DIRECT-EQUIVALENT"):
                self.assertTrue(rule.is_ticket, rule.rule_id)

    def test_ticket_family_members(self):
        # The rules the frontier plan names as human-review routes.
        for rule_id in ("DS-003", "MC-004", "SQL-002", "SV-006"):
            self.assertTrue(self.rules[rule_id].is_ticket, rule_id)

    def test_gated_families_present(self):
        # Families with live fixture gates (Track A routes through them).
        for rule_id in ("DS-012", "DS-020", "DS-021", "ST-014", "ST-015", "ST-016", "MX-001"):
            self.assertIn(rule_id, self.rules)

    def test_missing_file_raises(self):
        with self.assertRaises(RulebookError):
            load_rulebook(REPO_ROOT / "docs" / "no-such-file.yaml")


class ConstructMapTests(unittest.TestCase):
    def setUp(self):
        self.rules = load_rulebook(REPO_ROOT / "docs" / "sasconversionrulebook.yaml")

    def test_every_construct_resolves(self):
        for construct, rule_id in CONSTRUCT_MAP.items():
            self.assertIn(rule_id, self.rules, f"{construct} -> {rule_id}")

    def test_gated_families_first(self):
        # The plan's gated-first list must be in the map.
        for construct in ("round", "date", "missing", "merge", "sort",
                          "char-funcs", "arrays", "formats", "by-group"):
            self.assertIn(construct, CONSTRUCT_MAP)


class RouterTests(unittest.TestCase):
    def test_merge_routes(self):
        construct, rule_id = route_statement("MERGE a b; BY key;")
        self.assertEqual(rule_id, "DS-002")

    def test_merge_many_to_many_is_runtime_not_statement(self):
        # DS-003 is a data property (per-key group-size cross-tab), never a
        # statement shape. MERGE+BY must always route to DS-002; the emitted
        # code raises the DS-003 ticket at runtime when the check fires.
        self.assertTrue(MERGE_MANY_TO_MANY_HINT.search("MERGE a b; BY key;"))
        construct, rule_id = route_statement("MERGE a b; BY key;")
        self.assertEqual(rule_id, "DS-002")

    def test_set_routes(self):
        construct, rule_id = route_statement("set have1 have2;")
        self.assertEqual(rule_id, "DS-001")

    def test_proc_sort_routes(self):
        construct, rule_id = route_statement("proc sort data=in; by key; run;")
        self.assertEqual(rule_id, "DS-008")

    def test_proc_transpose_routes(self):
        construct, rule_id = route_statement("proc transpose data=in out=out; run;")
        self.assertEqual(rule_id, "DS-009")

    def test_proc_freq_routes_to_stat_freq(self):
        construct, rule_id = route_statement("proc freq data=in; tables a b; run;")
        self.assertEqual(rule_id, "ST-015")

    def test_proc_sql_routes(self):
        construct, rule_id = route_statement("proc sql; select * from a; quit;")
        self.assertEqual(rule_id, "SQL-001")

    def test_proc_sql_into_routes(self):
        construct, rule_id = route_statement("proc sql; select sum(x) into :tot from a; quit;")
        self.assertEqual(rule_id, "SQL-003")

    def test_proc_glm_routes_to_ticket(self):
        construct, rule_id = route_statement("proc glm data=long; class trt; model y=trt; run;")
        self.assertEqual(rule_id, "ST-007")

    def test_macro_let_routes(self):
        construct, rule_id = route_statement("%let path=/data/in;")
        self.assertEqual(rule_id, "MC-001")

    def test_macro_def_routes(self):
        construct, rule_id = route_statement("%macro doit(x); %mend;")
        self.assertEqual(rule_id, "MC-002")

    def test_unknown_statement(self):
        construct, rule_id = route_statement("bogus nonsense here;")
        self.assertEqual(construct, "unknown")
        self.assertEqual(rule_id, "")

    def test_round_function_routes(self):
        construct, rule_id = route_function("y = round(x, 0.1);")
        self.assertEqual(rule_id, "DS-012")

    def test_intck_function_routes(self):
        construct, rule_id = route_function("d = intck('month', a, b);")
        self.assertEqual(rule_id, "DS-011")

    def test_lag_function_routes(self):
        construct, rule_id = route_function("prev = lag(x);")
        self.assertEqual(rule_id, "DS-007")

    def test_char_function_routes(self):
        construct, rule_id = route_function("w = tranwrd(s, 'a', 'b');")
        self.assertEqual(rule_id, "DS-015")

    def test_sum_function_routes(self):
        construct, rule_id = route_function("t = sum(a, b, c);")
        self.assertEqual(rule_id, "DS-014")

    def test_unknown_function(self):
        construct, rule_id = route_function("y = myfunc(x);")
        self.assertEqual(construct, "unknown")
        self.assertEqual(rule_id, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
