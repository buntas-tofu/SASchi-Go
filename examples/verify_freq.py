#!/usr/bin/env python3
"""verify_freq.py : the fixture gate for PROC FREQ descriptive percents
(rulebook ST-015, the D.1-D.4 listing surface).

SAS computes three percentages for a two-way table: cell percent (count /
grand total of non-missing), row percent, and column percent, displayed
with one decimal. Missing levels are excluded from every denominator.
R prop.table and pandas crosstab normalize compute the same formulas, but
two landmines sit on the listing path: a zero-count level that a factor or
categorical materializes (R and pandas render NaN percents where SAS omits
the level entirely), and pandas crosstab margins combined with normalize,
which sums normalized values and never reproduces SAS totals.

The gate: the cross-tab rendered byte-equal in R and pandas, both checked
against the reference implementation (the SAS formulas), the one-way
listing with cumulative columns checked the same way, and the ghost-level
and margins traps pinned as demonstrations.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_freq_oneway, sas_freq_pcts  # noqa: E402

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

# 31 rows, the worked 2x2 shape: [[4, 21], [6, 0]]. The signed x B cell
# is a real zero (the level B occurs elsewhere), so every column and row
# total is positive and the only NaN surface is the ghost demo.
ROWS = ([("missed", "A")] * 4 + [("missed", "B")] * 21
        + [("signed", "A")] * 6)


def write_rows(rows):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                    newline="")
    f.write("status,heritage\n")
    for s, h in rows:
        f.write(f"{s},{h}\n")
    f.close()
    return f.name


def r_lane(cmd, csv_path, expect_rows):
    out = subprocess.run([str(RSCRIPT), str(HERE / "freq.R"), cmd, csv_path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = out.stdout.splitlines()
    if not lines or not lines[0].startswith("n="):
        raise RuntimeError("freq.R printed no row-count guard")
    if int(lines[0][2:]) != expect_rows:
        raise RuntimeError("R loaded a different row count: harness defect")
    return [ln for ln in lines[1:] if ln != ""]


def fmt_pct(v):
    return "MISSING" if v != v else f"{v:.1f}"


def render_tab(tab):
    total = tab.values.sum()
    out = []

    def pct(v, den):
        return float("nan") if den == 0 else 100.0 * v / den

    for r in tab.index:
        for c in tab.columns:
            v = int(tab.loc[r, c])
            out.append(f"{r}|{c} {v} {fmt_pct(pct(v, total))}"
                       f" {fmt_pct(pct(v, tab.loc[r].sum()))}"
                       f" {fmt_pct(pct(v, tab[c].sum()))}")
    return out


def py_tab_lines(df):
    # pandas 3 crosstab has no observed flag: unobserved categories of a
    # categorical are always omitted (the SAS behavior). Callers that want
    # them materialize with reindex.
    tab = pd.crosstab(df["status"], df["heritage"])
    return render_tab(tab)


def ref_lines():
    out = []
    cells = sas_freq_pcts(4, 21, 6, 0)
    for (r, c) in sorted(cells):
        v, p_all, p_row, p_col = cells[(r, c)]
        lvl_r = "missed" if r == 0 else "signed"
        lvl_c = "A" if c == 0 else "B"
        out.append(f"{lvl_r}|{lvl_c} {v} {fmt_pct(p_all)} {fmt_pct(p_row)}"
                   f" {fmt_pct(p_col)}")
    return out


def main() -> int:
    failed = 0
    path = write_rows(ROWS)

    print("1) two-way listing byte-equal R/pandas, against the reference:")
    r_lines = r_lane("tab", path, len(ROWS))
    df = pd.read_csv(path)
    py_lines = py_tab_lines(df)
    ref = ref_lines()
    mism = 0
    for i, (r, p) in enumerate(zip(r_lines, py_lines)):
        if r != p:
            mism += 1
            print(f"  MISMATCH R/py row {i}: {r!r} vs {p!r}")
    for i, (p, x) in enumerate(zip(py_lines, ref)):
        if p != x:
            mism += 1
            print(f"  MISMATCH ref row {i}: py {p!r} vs ref {x!r}")
    failed += mism
    print(f"  {len(ref)} cells byte-equal across R, pandas, and the"
          f" SAS-formula reference ({mism} mismatches)")
    for ln in ref:
        print(f"    {ln}")

    print("2) one-way listing with cumulative columns:")
    r_one = r_lane("oneway", path, len(ROWS))
    vc = df["status"].value_counts().sort_index()
    total = vc.sum()
    py_one, acc = [], 0
    for lvl, v in vc.items():
        acc += int(v)
        py_one.append(f"{lvl} {v} {fmt_pct(100.0 * v / total)} {acc}"
                      f" {fmt_pct(100.0 * acc / total)}")
    ref_one = [f"{lvl} {v} {fmt_pct(p)} {acc} {fmt_pct(cp)}"
               for (lvl, (v, p, acc, cp)) in
               zip(["missed", "signed"], sas_freq_oneway([25, 6]))]
    mism = 0
    for i, (r, p, x) in enumerate(zip(r_one, py_one, ref_one)):
        if r != p or p != x:
            mism += 1
            print(f"  MISMATCH oneway[{i}]: R {r!r} py {p!r} ref {x!r}")
    failed += mism
    print(f"  {len(ref_one)} rows byte-equal across all three ({mism}"
          " mismatches)")

    print("3) the ghost level, demonstrated:")
    # R factors with explicit levels materialize a zero-count row (NaN
    # percents). pandas 3 crosstab omits unobserved categories, matching
    # SAS, which never lists a level absent from the data. A listing
    # translation must pick one behavior explicitly: reindex to
    # materialize, or drop zero rows before rendering.
    r_ghost = r_lane("ghost", path, len(ROWS))
    ghost_r = [ln for ln in r_ghost if ln.startswith("ghost|")]
    if len(ghost_r) != 2 or not all("MISSING" in ln for ln in ghost_r):
        failed += 1
        print(f"  FAIL: R ghost lane wrong: {ghost_r!r}")
    print(f"  R factor with an unused level materializes the row:"
          f" {ghost_r[0] if ghost_r else 'none'}")
    df_g = pd.DataFrame({"status": pd.Categorical(
        df["status"], categories=["missed", "signed", "ghost"]),
        "heritage": df["heritage"]})
    py_default = py_tab_lines(df_g)
    if any(ln.startswith("ghost|") for ln in py_default):
        failed += 1
        print("  FAIL: pandas crosstab materialized the ghost row")
    print("  pandas 3 crosstab omits the unused category, like SAS.")
    # Materialize explicitly and prove byte-equality with R.
    tab = pd.crosstab(df["status"], df["heritage"])
    tab_g = tab.reindex(index=["missed", "signed", "ghost"], fill_value=0)
    py_ghost = render_tab(tab_g)
    mism = 0
    for i, (r, p) in enumerate(zip(r_ghost, py_ghost)):
        if r != p:
            mism += 1
            print(f"  MISMATCH ghost[{i}]: R {r!r} vs py {p!r}")
    failed += mism
    print(f"  explicit reindex lane byte-equal with R ({mism} mismatches)")
    print("  R materializes by default; pandas omits by default. Pin the")
    print("  choice; never rely on either default.")

    print("4) the margins trap, demonstrated:")
    m = pd.crosstab(df["status"], df["heritage"], margins=True,
                    normalize="index")
    if "All" not in m.index:
        failed += 1
        print(f"  FAIL: expected an 'All' margin row, got index {list(m.index)}")
    got = m.loc["All"] if "All" in m.index else None
    if got is None or abs(got.sum() - 1.0) > 1e-9:
        failed += 1
        print(f"  FAIL: normalized margin row does not sum to 1: {got}")
    print(f"  crosstab(margins=True, normalize='index') puts the margin in"
          f" the INDEX as an 'All' row of column means ({got.iloc[0]:.4f},"
          f" {got.iloc[1]:.4f}), never the SAS 100.0% row totals.")
    print("  Compute margins from counts; never from normalized values.")

    print()
    print("VERIFIED: FREQ descriptive percents match the SAS formulas and"
          " agree Python/R" if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
