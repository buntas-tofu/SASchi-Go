#!/usr/bin/env python3
"""verify_fisher.py : the fixture gate for the Fisher exact test (rulebook
ST-014, the 2018-corpus family).

SAS PROC FREQ with an EXACT FISHER statement reports three p-values:
left-sided (XPL_FISH), right-sided (XPR_FISH), and two-sided (XP2_FISH).
R fisher.test and scipy.stats.fisher_exact both DEFAULT to two-sided, so a
translation that wants the SAS left column must pass alternative='less'
explicitly, and misreading XPL as XPR flips the tail silently. scipy also
does not report the conditional-MLE odds ratio or its interval; CI rows
route to R.

The reference implementation (sas_semantics.sas_fisher_exact) is pure
integer hypergeometric, which is the same algorithm R and scipy implement
for 2x2 tables. The gate pins four fixtures (including a zero cell and a
lopsided-margin table), checks the reference against hand-pinned truth,
then demands byte-equal %.4g agreement with the R lane, row-count guarded.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_fisher_exact  # noqa: E402

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

# (name, a, b, c, d) with table [[a, b], [c, d]]. T1 is the classic 2x2
# whose two-sided p pins at 0.1238; T3 has a zero top-left cell; T4 has
# lopsided margins that exercise the support bounds of the hypergeometric.
TABLES = [("T1", 4, 21, 6, 8),
          ("T2", 10, 3, 4, 12),
          ("T3_zero", 0, 5, 6, 2),
          ("T4_swap", 3, 5, 2, 1)]

# Hand-pinned truth in the gate's rendering (%.4g), agreed by R 4.3.3,
# scipy 1.18, and the reference on 2026-09-09.
PINS = {
    "T1":      ("0.1238", "0.07367"),
    "T2":      ("0.009221", "0.9994"),
    "T3_zero": ("0.02098", "0.01632"),
    "T4_swap": ("0.5455", "0.4242"),
}


def fmt(v):
    return format(v, ".4g")


def main() -> int:
    failed = 0

    print("1) reference pins (sas_fisher_exact vs hand-pinned truth):")
    for name, a, b, c, d in TABLES:
        got = (fmt(sas_fisher_exact(a, b, c, d, "two")),
               fmt(sas_fisher_exact(a, b, c, d, "less")))
        want = PINS[name]
        if got != want:
            failed += 1
            print(f"  FAIL {name}: got {got} want {want}")
    print(f"  {len(TABLES)} fixtures pinned (two-sided and left-sided)")

    print("2) R lane agreement, byte-equal %.4g, row-count guarded:")
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write("name,a,b,c,d\n")
        for row in TABLES:
            f.write(",".join(str(v) for v in row) + "\n")
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "fisher.R"), path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = out.stdout.splitlines()
    if not lines or not lines[0].startswith("n="):
        raise RuntimeError("fisher.R printed no row-count guard")
    if int(lines[0][2:]) != len(TABLES):
        raise RuntimeError("R loaded a different row count: harness defect")
    r_lines = [ln for ln in lines[1:] if ln != ""]
    py_lines = [f"{name} {fmt(sas_fisher_exact(a, b, c, d, 'two'))} "
                f"{fmt(sas_fisher_exact(a, b, c, d, 'less'))}"
                for name, a, b, c, d in TABLES]
    if r_lines != py_lines:
        failed += 1
        for i, (r, p) in enumerate(zip(r_lines, py_lines)):
            if r != p:
                print(f"  MISMATCH row {i}: R {r!r} vs py {p!r}")
    print(f"  {len(py_lines)} lines byte-equal Python/R")

    print("3) the default landmine, demonstrated:")
    # R and scipy default to two-sided. A translation that emits no
    # alternative to reproduce the SAS left column is wrong by
    # construction; show the default differs from the left pin on T1.
    if "0.1238" == PINS["T1"][1]:
        failed += 1
        print("  FAIL: default and left-sided p collided; fixture is bad")
    print("  R/scipy default two-sided (0.1238 on T1); SAS XPL_FISH needs"
          " alternative='less' (0.07367). Defaults do not match.")

    print()
    print("VERIFIED: Fisher exact p-values match the rule and agree"
          " Python/R" if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
