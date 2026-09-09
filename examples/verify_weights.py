#!/usr/bin/env python3
"""verify_weights.py : the fixture gate for WEIGHT semantics (quirk 12,
second half).

Pins the exclusion rule (missing weight excludes; zero and negative weights
are INCLUDED by default, which is what the EXCLNPWGT option's existence
proves, settling the dossier conflict), the documented VARDEF divisor set
(DF n-1, N n, WDF sum(w)-1, WEIGHT sum(w), refuting the effective-df
hallucination), the zero-weight DF-divisor shift, the negative-CSS
pathology reading as missing, and PROC FREQ's weighted cells. Hand-computed
pins, then Python/R agreement, row-count guarded.
"""

import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import (sas_freq_weighted, sas_weighted_mean,  # noqa: E402
                           sas_weighted_std)

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"
NAN = float("nan")

BASE = [(1.0, 2.0), (2.0, 3.0), (3.0, 5.0)]           # sw=10, mean 2.3, css 6.1
ZERO = BASE + [(100.0, 0.0)]                          # n rises to 4, sums hold
MISSW = BASE + [(100.0, None)]                        # excluded entirely
NEG = [(1.0, 2.0), (5.0, -1.0)]                       # sw=1, css -32

WSTAT_CASES = [
    ("mean", 0, BASE), ("std_df", 0, BASE), ("std_n", 0, BASE),
    ("std_wdf", 0, BASE), ("std_weight", 0, BASE),
    ("mean", 0, MISSW), ("std_df", 0, ZERO), ("std_df", 1, ZERO),
    ("mean", 0, NEG), ("std_df", 0, NEG),
]

PY_STAT = {"mean": lambda p, e: sas_weighted_mean(p, excl_npwgt=e),
           "std_df": lambda p, e: sas_weighted_std(p, "DF", excl_npwgt=e),
           "std_n": lambda p, e: sas_weighted_std(p, "N", excl_npwgt=e),
           "std_wdf": lambda p, e: sas_weighted_std(p, "WDF", excl_npwgt=e),
           "std_weight": lambda p, e: sas_weighted_std(p, "WEIGHT", excl_npwgt=e)}


def main() -> int:
    failed = 0

    print("1) hand pins (mean 2.3, css 6.1 over the divisor set):")
    pins = [(sas_weighted_mean(BASE), 2.3),
            (sas_weighted_std(BASE, "DF"), math.sqrt(6.1 / 2)),
            (sas_weighted_std(BASE, "N"), math.sqrt(6.1 / 3)),
            (sas_weighted_std(BASE, "WDF"), math.sqrt(6.1 / 9)),
            (sas_weighted_std(BASE, "WEIGHT"), math.sqrt(6.1 / 10))]
    for got, want in pins:
        if abs(got - want) > 1e-12:
            failed += 1
            print(f"  FAIL {got} want {want}")
    print(f"  {len(pins)} pins checked")

    print("2) the exclusion rules (the dossier conflict, settled):")
    checks = [
        ("missing weight excludes", sas_weighted_mean(MISSW), 2.3),
        ("zero weight shifts the DF divisor",
         sas_weighted_std(ZERO, "DF"), math.sqrt(6.1 / 3)),
        ("EXCLNPWGT restores",
         sas_weighted_std(ZERO, "DF", excl_npwgt=True), math.sqrt(6.1 / 2)),
        ("negative weights compute the mean", sas_weighted_mean(NEG), -3.0),
    ]
    for name, got, want in checks:
        if got is None or abs(got - want) > 1e-12:
            failed += 1
            print(f"  FAIL {name}: {got} want {want}")
    if sas_weighted_std(NEG, "DF") is not None:
        failed += 1
        print("  FAIL negative CSS must read as missing")
    print(f"  {len(checks) + 1} rules checked")

    print("3) weighted FREQ cells:")
    freq = sas_freq_weighted([("a", 1.5), ("a", 2.0), ("b", 0.5),
                              ("c", None), ("d", 0.0)])
    if freq != {"a": 3.5, "b": 0.5}:
        failed += 1
        print(f"  FAIL {freq}")
    kept = sas_freq_weighted([("d", 0.0)], keep_zeros=True)
    if kept != {"d": 0.0}:
        failed += 1
        print(f"  FAIL ZEROS keeps zero-total levels: {kept}")
    print("  2 tables checked (missing dropped, zero-total dropped, ZEROS kept)")

    print("4) Python/R agreement, row-count guarded:")

    def join(vals):
        return ";".join("NA" if v is None or v != v else repr(v) for v in vals)

    rows = []
    for stat, excl, pairs in WSTAT_CASES:
        rows.append(['"' + stat + '"', str(excl),
                     '"' + join([x for x, _w in pairs]) + '"',
                     '"' + join([w for _x, w in pairs]) + '"'])
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write("stat,excl,x,w\n")
        for row in rows:
            f.write(",".join(row) + "\n")
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "weights.R"), "wstat", path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = [ln for ln in out.stdout.splitlines() if ln]
    if not lines[0].startswith("n=") or int(lines[0][2:]) != len(rows):
        raise RuntimeError("row-count guard failed")
    mism = 0
    for i, (stat, excl, pairs) in enumerate(WSTAT_CASES):
        py = PY_STAT[stat](pairs, bool(excl))
        rv = lines[1 + i]
        ok = (rv == "NA") == (py is None) and \
             (rv == "NA" or abs(py - float(rv)) <= 1e-12 * max(1.0, abs(py)))
        if not ok:
            mism += 1
            print(f"  MISMATCH wstat[{i}] {stat}: py {py!r} vs R {rv}")
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write("levels,w\n")
        f.write('"a;a;b;c;d","1.5;2.0;0.5;NA;0.0"\n')
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "weights.R"), "wfreq", path],
                         capture_output=True, text=True)
    lines = [ln for ln in out.stdout.splitlines() if ln]
    r_freq = dict(kv.split("=") for kv in lines[1].split(";"))
    if {k: float(v) for k, v in r_freq.items()} != {"a": 3.5, "b": 0.5}:
        mism += 1
        print(f"  MISMATCH wfreq: R {r_freq}")
    failed += mism
    print(f"  {len(WSTAT_CASES)} wstat + 1 wfreq fixtures, {mism} mismatches")

    print()
    print("VERIFIED: WEIGHT semantics match the rule and agree Python/R"
          if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
