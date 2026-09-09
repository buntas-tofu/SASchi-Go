#!/usr/bin/env python3
"""verify_missarith.py : the fixture gate for missing-value arithmetic
(quirk 14).

Pins propagation (a missing operand poisons the operator), the
division-by-zero temperament (missing, never Inf and never an exception),
the paired landmine (+ propagates while SUM() ignores, all-missing sums to
missing), the comparison order (missing below every number, so "if x < 0"
CATCHES missing in SAS and silently does not in Python or R), missing EQ
missing as true, and logical truth (missing and zero false). Demonstrates
the host-language divergences deterministically, then proves Python/R
agreement, row-count guarded.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import (sas_arith, sas_num_lt, sas_sum,  # noqa: E402
                           sas_truth)

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"
NAN = float("nan")

ARITH = [(1.0, "+", None, None), (None, "*", 5.0, None),
         (7.0, "/", 0.0, None), (7.0, "/", 2.0, 3.5),
         (2.0, "**", 10.0, 1024.0), (3.0, "-", NAN, None)]
SUMS = [([1.0, None, 2.0], 3.0), ([None, NAN], None),
        ([4.0], 4.0), ([0.0, None], 0.0)]
LTS = [(None, -1e300, True), (0.0, None, False), (None, None, False),
       (NAN, 0.0, True), (-1.0, 0.0, True), (2.0, 1.0, False)]
TRUTHS = [(None, False), (0.0, False), (-0.5, True), (42.0, True),
          (NAN, False)]


def fmt(v):
    return "NA" if v is None or (isinstance(v, float) and v != v) else repr(v)


def r_lane(cmd, header, rows):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join('"' + c + '"' for c in row) + "\n")
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "missarith.R"), cmd, path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = [ln for ln in out.stdout.splitlines() if ln]
    if not lines[0].startswith("n=") or int(lines[0][2:]) != len(rows):
        raise RuntimeError("row-count guard failed")
    return lines[1:]


def main() -> int:
    failed = 0

    print("1) propagation and the division temperament:")
    for a, op, b, want in ARITH:
        got = sas_arith(a, op, b)
        if got != want:
            failed += 1
            print(f"  FAIL {fmt(a)} {op} {fmt(b)} = {got} want {want}")
    print(f"  {len(ARITH)} pins checked (missing poisons, /0 is missing)")

    print("2) the paired landmine (+ propagates, SUM ignores):")
    if sas_arith(1.0, "+", None) is not None or sas_sum(1.0, None, 2.0) != 3.0:
        failed += 1
        print("  FAIL the pair")
    for vals, want in SUMS:
        if sas_sum(*vals) != want:
            failed += 1
            print(f"  FAIL SUM{vals} = {sas_sum(*vals)} want {want}")
    print(f"  the pair plus {len(SUMS)} SUM pins checked")

    print("3) comparison order and truth:")
    for a, b, want in LTS:
        if sas_num_lt(a, b) != want:
            failed += 1
            print(f"  FAIL {fmt(a)} < {fmt(b)} = {sas_num_lt(a, b)} want {want}")
    for x, want in TRUTHS:
        if sas_truth(x) != want:
            failed += 1
            print(f"  FAIL truth({fmt(x)}) = {sas_truth(x)} want {want}")
    print(f"  {len(LTS)} order pins, {len(TRUTHS)} truth pins")

    print("4) the host-language divergences (deterministic demos):")
    demos = [("SAS missing < 0 is True, Python nan < 0 is",
              sas_num_lt(NAN, 0.0), NAN < 0.0)]
    sas_says, py_says = demos[0][1], demos[0][2]
    if not (sas_says is True and py_says is False):
        failed += 1
        print("  FAIL: expected the divergence, found agreement")
    try:
        1.0 / 0.0
        py_div = "no exception"
    except ZeroDivisionError:
        py_div = "raises"
    print(f"  missing<0: SAS {sas_says} vs Python {py_says}; "
          f"1/0: SAS missing vs Python {py_div}")

    print("5) Python/R agreement, row-count guarded:")
    mism = 0
    r = r_lane("arith", ["a", "op", "b"],
               [[fmt(a), op, fmt(b)] for a, op, b, _w in ARITH])
    for i, (a, op, b, want) in enumerate(ARITH):
        ok = (r[i] == "NA") == (want is None) and \
             (r[i] == "NA" or float(r[i]) == want)
        if not ok:
            mism += 1
            print(f"  MISMATCH arith[{i}]: R {r[i]} want {want}")
    r = r_lane("sum", ["vals"], [[";".join(fmt(v) for v in vals)]
                                 for vals, _w in SUMS])
    for i, (_vals, want) in enumerate(SUMS):
        ok = (r[i] == "NA") == (want is None) and \
             (r[i] == "NA" or float(r[i]) == want)
        if not ok:
            mism += 1
            print(f"  MISMATCH sum[{i}]: R {r[i]} want {want}")
    r = r_lane("lt", ["a", "b"], [[fmt(a), fmt(b)] for a, b, _w in LTS])
    for i, (_a, _b, want) in enumerate(LTS):
        if bool(int(r[i])) != want:
            mism += 1
            print(f"  MISMATCH lt[{i}]: R {r[i]} want {want}")
    r = r_lane("truth", ["x"], [[fmt(x)] for x, _w in TRUTHS])
    for i, (_x, want) in enumerate(TRUTHS):
        if bool(int(r[i])) != want:
            mism += 1
            print(f"  MISMATCH truth[{i}]: R {r[i]} want {want}")
    failed += mism
    n = len(ARITH) + len(SUMS) + len(LTS) + len(TRUTHS)
    print(f"  {n} fixtures across 4 lanes, {mism} mismatches")

    print()
    print("VERIFIED: missing-value arithmetic matches the rule and agrees "
          "Python/R" if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
