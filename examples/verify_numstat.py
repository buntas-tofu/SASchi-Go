#!/usr/bin/env python3
"""verify_numstat.py : the fixture gate for statistical functions (quirk 12,
first half: probability/quantile functions and SAS moments).

Layer-1 pins are published statistical tables: the 3.841458821 chi-square
critical value, the 2.228138852 t critical value, the 1.959963985 normal
quantile. The moment estimators are pinned three ways: SAS formula vs scipy's
bias=False estimators vs the R hand-formula twin (base R has no skewness or
kurtosis, which is the trap). Domain violations read as missing (the SAS
runtime temperament), analysis variables drop missings first, and n-minimums
and zero-variance series return missing. Cross-language agreement at 1e-12,
row-count guarded.
"""

import statistics
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import (sas_cinv, sas_finv, sas_kurtosis,  # noqa: E402
                           sas_mean, sas_probchi, sas_probf, sas_probit,
                           sas_probnorm, sas_probt, sas_skewness, sas_std,
                           sas_tinv)

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"
NAN = float("nan")

PY_DIST = {"probnorm": lambda a, b, c: sas_probnorm(a),
           "probit": lambda a, b, c: sas_probit(a),
           "probchi": lambda a, b, c: sas_probchi(a, b),
           "cinv": lambda a, b, c: sas_cinv(a, b),
           "probt": lambda a, b, c: sas_probt(a, b),
           "tinv": lambda a, b, c: sas_tinv(a, b),
           "probf": lambda a, b, c: sas_probf(a, b, c),
           "finv": lambda a, b, c: sas_finv(a, b, c)}

DIST_CASES = [("probnorm", 1.959963985, 0, 0), ("probnorm", -1.0, 0, 0),
              ("probit", 0.975, 0, 0), ("probit", 1.5, 0, 0),
              ("probchi", 3.841458821, 1, 0), ("probchi", -1.0, 1, 0),
              ("cinv", 0.95, 1, 0), ("probt", 2.228138852, 10, 0),
              ("tinv", 0.975, 10, 0), ("tinv", 0.025, 10, 0),
              ("probf", 3.708265, 3, 10, ), ("finv", 0.95, 3, 10)]

MOM_SETS = [[2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0],
            [1.0, None, 2.0, NAN, 3.0],
            [5.0, 5.0, 5.0, 5.0],
            [1.0, 2.0]]


def r_lane(cmd, header, rows, n_expected):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join(row) + "\n")
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "numstat.R"), cmd, path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = [ln for ln in out.stdout.splitlines() if ln != ""]
    if not lines[0].startswith("n=") or int(lines[0][2:]) != n_expected:
        raise RuntimeError("row-count guard failed: harness defect")
    return lines[1:]


def close(a, b, tol=1e-12):
    if a is None:
        return b == "NA"
    if b == "NA":
        return False
    return abs(a - float(b)) <= tol * max(1.0, abs(a))


def main() -> int:
    failed = 0

    print("1) published-table pins (oracle layer 1):")
    pins = [(sas_probchi(3.841458821, 1), 0.95, 1e-9),
            (sas_cinv(0.95, 1), 3.841458821, 1e-8),
            (sas_tinv(0.975, 10), 2.228138852, 1e-8),
            (sas_probt(2.228138852, 10), 0.975, 1e-9),
            (sas_probnorm(1.959963985), 0.975, 1e-9),
            (sas_probit(0.975), 1.959963985, 1e-8),
            (sas_finv(0.95, 3, 10), 3.708265, 5e-6)]
    for got, want, tol in pins:
        if got is None or abs(got - want) > tol:
            failed += 1
            print(f"  FAIL {got} want {want} (tol {tol})")
    print(f"  {len(pins)} table pins checked")

    print("2) the SAS temperament (out of domain reads as missing):")
    dom = [sas_probchi(-1.0, 1), sas_probchi(1.0, 0), sas_tinv(1.5, 10),
           sas_probit(0.0), sas_finv(0.95, 0, 10)]
    bad = sum(1 for v in dom if v is not None)
    failed += bad
    print(f"  {len(dom)} violations, {bad} failed to read as missing")

    print("3) moments: SAS formula vs scipy bias=False vs edge rules:")
    import scipy.stats as st
    data = MOM_SETS[0]
    trio = [(sas_skewness(data), float(st.skew(data, bias=False))),
            (sas_kurtosis(data), float(st.kurtosis(data, bias=False)))]
    for ours, scipys in trio:
        if abs(ours - scipys) > 1e-12:
            failed += 1
            print(f"  FAIL formula {ours} vs scipy {scipys}")
    if abs(sas_std(data) - statistics.stdev(data)) > 1e-12:
        failed += 1
        print("  FAIL std(DF) vs statistics.stdev")
    missing_laden = MOM_SETS[1]
    if sas_mean(missing_laden) != 2.0 or sas_std(missing_laden) != 1.0:
        failed += 1
        print("  FAIL analysis variables must drop missings first")
    edges = [sas_skewness([1.0, 2.0]), sas_kurtosis([1.0, 2.0, 3.0]),
             sas_skewness([5.0, 5.0, 5.0]), sas_kurtosis(MOM_SETS[2])]
    bad = sum(1 for v in edges if v is not None)
    failed += bad
    print(f"  scipy agreement, missing-skip, {len(edges)} edge rules "
          f"({bad} failed)")

    print("4) Python/R agreement (base R distributions, hand-formula")
    print("   moments), row-count guarded:")
    rows = [[c[0], repr(float(c[1])), repr(float(c[2])),
             repr(float(c[3])) if len(c) > 3 else "0.0"] for c in DIST_CASES]
    r = r_lane("dist", ["fn", "a", "b", "c"],
               [['"' + row[0] + '"'] + row[1:] for row in rows],
               len(DIST_CASES))
    mism = 0
    for i, c in enumerate(DIST_CASES):
        py = PY_DIST[c[0]](float(c[1]), float(c[2]),
                           float(c[3]) if len(c) > 3 else 0.0)
        if not close(py, r[i]):
            mism += 1
            print(f"  MISMATCH dist[{i}] {c}: py {py!r} vs R {r[i]}")
    stats = ["mean", "std_df", "std_n", "skew", "kurt"]
    mrows, mpy = [], []
    for ds in MOM_SETS:
        joined = ";".join("NA" if v is None or v != v else repr(v)
                          for v in ds)
        for s in stats:
            mrows.append(['"' + s + '"', '"' + joined + '"'])
            mpy.append({"mean": sas_mean, "std_df": sas_std,
                        "std_n": lambda x: sas_std(x, "N"),
                        "skew": sas_skewness, "kurt": sas_kurtosis}[s](ds))
    r = r_lane("moments", ["stat", "data"], mrows, len(mrows))
    for i, (py, rv) in enumerate(zip(mpy, r)):
        if not close(py, rv):
            mism += 1
            print(f"  MISMATCH moments[{i}]: py {py!r} vs R {rv}")
    failed += mism
    print(f"  {len(DIST_CASES)} dist + {len(mrows)} moment fixtures, "
          f"{mism} mismatches")

    print()
    print("VERIFIED: statistical functions match the rule and agree Python/R"
          if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
