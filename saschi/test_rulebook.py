"""Tests for the rulebook's targets: the examples execute, they are not prose.

The rulebook is published guidance, so its target patterns are load-bearing
text. Until 2026-09-14 nothing executed any of them. The structural checks in
test_rules.py confirmed every rule had its fields and every id was unique, and
no gate ran a single pandas or SQL target, so four rules stated contracts that
only running them exposes as wrong.

Each test below is the executable counterpart of one rule's pattern. The text
assertions keep the pattern and this file in step: if the guidance is reworded
back to the contract that was wrong, the assertion fails here rather than later,
in someone's program.

Run: python -m unittest saschi.test_rulebook -v
"""

import collections
import unittest
from pathlib import Path

import duckdb
import pandas as pd

from saschi.rules import Rule, load_rulebook

REPO_ROOT = Path(__file__).resolve().parent.parent
RULEBOOK = REPO_ROOT / "docs" / "sasconversionrulebook.json"


class RulebookTargetTests(unittest.TestCase):
    rules: dict[str, Rule]

    @classmethod
    def setUpClass(cls):
        cls.rules = load_rulebook(RULEBOOK)

    def pattern(self, rule_id: str) -> str:
        return self.rules[rule_id].python_target["pattern"]

    # ---- DS-006: FIRST./LAST./RETAIN, the sum statement ---------------------
    def test_ds006_runs_over_multiple_groups(self):
        """The pattern filled inside the aggregation, which pandas 3 removed.

        SeriesGroupBy.fillna raised AttributeError, so the published example did
        not run at all under the installed pandas. Filling the column before
        grouping does, and dropna=False keeps the missing BY group SAS keeps.
        """
        frame = pd.DataFrame(
            {"k": ["a", "a", None, "a", "b"], "x": [1.0, None, 5.0, 3.0, 2.0]}
        )
        keys = ["k"]
        frame = frame.sort_values(by=keys, kind="stable", na_position="first")
        g = frame.groupby(keys, dropna=False)
        frame["first"] = ~frame.duplicated(keys)
        frame["last"] = ~frame.duplicated(keys, keep="last")
        frame["run"] = (
            frame.assign(_x=frame["x"].fillna(0))
            .groupby(keys, dropna=False)["_x"]
            .cumsum()
        )
        frame["ctr"] = g.cumcount() + 1

        runs = frame.groupby(keys, dropna=False)["run"].max().to_dict()
        self.assertEqual(len(runs), 3, "dropna=False must keep the missing BY group")
        self.assertEqual(runs["a"], 4.0, "the missing increment counts as zero")
        self.assertEqual(runs["b"], 2.0)
        self.assertEqual(frame["first"].tolist(), [True, True, False, False, True])
        self.assertEqual(frame["ctr"].tolist(), [1, 1, 2, 3, 1])

    def test_ds006_pattern_states_the_pandas3_contract(self):
        p = self.pattern("DS-006")
        self.assertNotIn("g[c].fillna(0).cumsum()", p, "the removed idiom is back")
        self.assertIn("fillna(0)", p)
        self.assertIn("cumsum", p)
        self.assertIn("dropna=False", p)

    # ---- DS-007: LAG inside conditional logic ------------------------------
    def test_ds007_the_queue_is_not_a_column_shift(self):
        """The rule prescribed the shift, which answers a different question.

        With values 10, 20, 30, 40 and the LAG occurrence executed only on rows
        two and four, SAS returns missing and then 20: the queue advances where
        the call RUNS. A full-column shift returns 10 and 30.
        """
        values = [10, 20, 30, 40]
        invoked = [False, True, False, True]

        queue: collections.deque = collections.deque(maxlen=1)
        per_row = []
        for value, runs_here in zip(values, invoked):
            if runs_here:
                per_row.append(queue[0] if queue else pd.NA)
                queue.appendleft(value)
            else:
                per_row.append(pd.NA)
        returned = [v for v, runs_here in zip(per_row, invoked) if runs_here]

        self.assertTrue(pd.isna(returned[0]), "the first invocation has no history")
        self.assertEqual(returned[1], 20, "the second invocation sees the first one")

        shifted = pd.Series(values).shift(1)[invoked].tolist()
        self.assertEqual(shifted, [10.0, 30.0], "what the old rule produced")
        self.assertNotEqual(returned[1], shifted[1])

    def test_ds007_pattern_separates_the_two_cases(self):
        rule = self.rules["DS-007"]
        p = self.pattern("DS-007")
        self.assertIn("two cases", p)
        self.assertIn("INSIDE", p)
        self.assertTrue(rule.forbidden_patterns, "the wrong translation must be named")
        self.assertIn("CALL SITE", " ".join(rule.required_settings))

    # ---- DS-009: PROC TRANSPOSE, and what LET actually buys ----------------
    def test_ds009_let_keeps_last_and_no_let_still_fails(self):
        frame = pd.DataFrame(
            {"id": [1, 1, 2], "name": ["v", "v", "v"], "val": [10, 99, 5]}
        )
        with_let = frame.pivot_table(
            index="id", columns="name", values="val", aggfunc="last"
        )
        self.assertEqual(with_let["v"].to_dict(), {1: 99, 2: 5})

        default = frame.pivot_table(index="id", columns="name", values="val")
        self.assertEqual(
            default["v"].to_dict(), {1: 54.5, 2: 5.0},
            "the silent average the rule warns about",
        )

        with self.assertRaises(ValueError):
            self._transpose_without_let(frame)

    @staticmethod
    def _transpose_without_let(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.duplicated(["id", "name"], keep=False).any():
            raise ValueError(
                "a duplicate ID without LET is an error in SAS, so the port raises"
            )
        return frame.pivot_table(
            index="id", columns="name", values="val", aggfunc="first"
        )

    def test_ds009_settings_make_let_the_condition(self):
        rule = self.rules["DS-009"]
        self.assertIn("LET", " ".join(rule.required_settings))
        self.assertIn("raise", " ".join(rule.required_settings))
        self.assertIn("did not specify LET", " ".join(rule.forbidden_patterns))

    # ---- SQL-001: the SAS-only keyword ------------------------------------
    def test_sql001_calculated_is_rewritten_not_passed_through(self):
        """CALCULATED is SAS syntax and the engine does not know the keyword."""
        try:
            duckdb.sql("select 1 as x, calculated x + 1 as y").fetchall()
            self.fail("the engine accepted CALCULATED, so the rewrite is not needed")
        except Exception as exc:
            self.assertIn("Parser", type(exc).__name__)
        self.assertEqual(duckdb.sql("select 1 as x, x + 1 as y").fetchall(), [(1, 2)])

    def test_sql001_pattern_no_longer_claims_pass_through(self):
        rule = self.rules["SQL-001"]
        p = self.pattern("SQL-001")
        self.assertNotIn("usually work unchanged", p)
        self.assertIn("CALCULATED", p)
        self.assertIn("rewrit", p)
        self.assertTrue(rule.forbidden_patterns)


if __name__ == "__main__":
    unittest.main(verbosity=2)