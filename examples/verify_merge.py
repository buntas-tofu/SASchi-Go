#!/usr/bin/env python3
"""verify_merge.py : the fixture gate for MERGE BY (quirk 15).

Pins the PDV mechanics against hand-derived fixtures: max(nl, nr) rows per
group with carry-forward (the 2x3 trap: 3 rows where every SQL join yields
6, demonstrated live against pandas), the shared-variable exhaustion flip
(right's value while it reads, left's fresh reads after), unmatched groups
with the absent side missing, group-retained IN= flags, and missing BY keys
matching each other (quirk 14's comparison law, which every SQL NULL
violates). Seeded property sweep for the group-shape invariants, then
Python/R agreement with row-count guards.
"""

import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_merge_by  # noqa: E402

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

F1_L = [{"k": 1.0, "a": "A1", "x": "LX1"}, {"k": 2.0, "a": "A2", "x": "LX2"}]
F1_R = [{"k": 1.0, "b": "B1", "x": "RX1"}, {"k": 2.0, "b": "B2", "x": "RX2"}]

F2_L = [{"k": 1.0, "a": "A1", "x": "LX1"}, {"k": 1.0, "a": "A2", "x": "LX2"}]
F2_R = [{"k": 1.0, "b": "B1", "x": "RX1"}, {"k": 1.0, "b": "B2", "x": "RX2"},
        {"k": 1.0, "b": "B3", "x": "RX3"}]

F3_L = [{"k": 1.0, "x": "LX1"}, {"k": 1.0, "x": "LX2"}, {"k": 1.0, "x": "LX3"}]
F3_R = [{"k": 1.0, "x": "RX1"}]

F4_L = [{"k": 1.0, "a": "A1"}]
F4_R = [{"k": 2.0, "b": "B1"}]

F5_L = [{"k": None, "a": "AM"}]
F5_R = [{"k": None, "b": "BM"}]

F6_L = [{"k": 1.0, "a": "A1"}]
F6_R = [{"k": 1.0, "b": "B1"}, {"k": 1.0, "b": "B2"}, {"k": 1.0, "b": "B3"}]

FIXTURES = [("F1 1:1", F1_L, F1_R), ("F2 2x3", F2_L, F2_R),
            ("F3 flip", F3_L, F3_R), ("F4 unmatched", F4_L, F4_R),
            ("F5 missing-keys", F5_L, F5_R), ("F6 in-retain", F6_L, F6_R)]


def fmt(v):
    if v is None:
        return "NA"
    if isinstance(v, float):
        # match R's format(x, digits = 17): whole floats print bare
        return f"{v:.17g}" if v == v else "NA"
    return str(v)


def py_lines(L, R, by):
    rows, il, ir = sas_merge_by(L, R, by)
    cols = None
    out = []
    for rec, a, b in zip(rows, il, ir):
        if cols is None:
            lc = list(L[0].keys()) if L else []
            rc = list(R[0].keys()) if R else []
            shared = [c for c in lc if c in rc and c not in by]
            lonly = [c for c in lc if c not in rc and c not in by]
            ronly = [c for c in rc if c not in lc and c not in by]
            cols = by + lonly + ronly + shared
        out.append("|".join([fmt(rec[c]) for c in cols] + [str(a), str(b)]))
    return out


def r_lines(L, R, by):
    def write_side(rows):
        cols = list(rows[0].keys())
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                         newline="") as f:
            f.write(",".join(cols) + "\n")
            for rec in rows:
                f.write(",".join('"' + fmt(rec[c]) + '"' for c in cols) + "\n")
            return f.name, len(rows)

    lpath, nl = write_side(L)
    rpath, nr = write_side(R)
    out = subprocess.run([str(RSCRIPT), str(HERE / "merge.R"), lpath, rpath,
                          ",".join(by)], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = [ln for ln in out.stdout.splitlines() if ln]
    if lines[0] != f"n={nl}" or lines[1] != f"n={nr}":
        raise RuntimeError("row-count guard failed: harness defect")
    return lines[2:]


def main() -> int:
    failed = 0

    print("1) the 2x3 trap (rows and carry-forward, vs the SQL cartesian):")
    rows, _il, _ir = sas_merge_by(F2_L, F2_R, ["k"])
    want = [("A1", "B1", "RX1"), ("A2", "B2", "RX2"), ("A2", "B3", "RX3")]
    got = [(r["a"], r["b"], r["x"]) for r in rows]
    if got != want:
        failed += 1
        print(f"  FAIL {got}")
    import pandas as pd
    sql_rows = len(pd.DataFrame(F2_L).merge(pd.DataFrame(F2_R), on="k"))
    if sql_rows != 6 or len(rows) != 3:
        failed += 1
        print(f"  FAIL divergence: SAS {len(rows)} vs pandas {sql_rows}")
    print(f"  3 rows with A2 carried, pandas merge says {sql_rows}: divergence pinned")

    print("2) the exhaustion flip:")
    rows, _il, _ir = sas_merge_by(F3_L, F3_R, ["k"])
    got = [r["x"] for r in rows]
    if got != ["RX1", "LX2", "LX3"]:
        failed += 1
        print(f"  FAIL {got}")
    print(f"  shared x reads {got}: right while it lasts, left after")

    print("3) unmatched, missing-key match, IN retention:")
    rows, il, ir = sas_merge_by(F4_L, F4_R, ["k"])
    if [(r["a"], r["b"]) for r in rows] != [("A1", None), (None, "B1")] \
            or il != [1, 0] or ir != [0, 1]:
        failed += 1
        print(f"  FAIL unmatched: {rows} {il} {ir}")
    rows, il, ir = sas_merge_by(F5_L, F5_R, ["k"])
    if len(rows) != 1 or rows[0]["a"] != "AM" or rows[0]["b"] != "BM" \
            or il != [1] or ir != [1]:
        failed += 1
        print(f"  FAIL missing-key match: {rows}")
    rows, il, ir = sas_merge_by(F6_L, F6_R, ["k"])
    if il != [1, 1, 1] or ir != [1, 1, 1] or [r["a"] for r in rows] != ["A1"] * 3:
        failed += 1
        print(f"  FAIL IN retention: {il} {ir}")
    print("  3 rules checked (SQL NULL semantics refuted on the record)")

    print("4) property sweep (seeded, 200 trials: group shapes, flag")
    print("   constancy, key order):")
    rng = random.Random(19830715)
    bad = 0
    for _ in range(200):
        keys = [float(k) for k in range(rng.randint(0, 4))] + \
               ([None] if rng.random() < 0.3 else [])
        L, R = [], []
        for k in keys:
            for j in range(rng.randint(0, 3)):
                L.append({"k": k, "a": f"a{j}", "x": f"lx{j}"})
            for j in range(rng.randint(0, 3)):
                R.append({"k": k, "b": f"b{j}", "x": f"rx{j}"})
        if not L or not R:
            continue
        rows, il, ir = sas_merge_by(L, R, ["k"])
        from collections import Counter
        nl, nr = Counter(r["k"] for r in L), Counter(r["k"] for r in R)
        out = Counter(r["k"] for r in rows)
        for k in set(nl) | set(nr):
            if out[k] != max(nl.get(k, 0), nr.get(k, 0)):
                bad += 1
        flags = {}
        for rec, a, b in zip(rows, il, ir):
            flags.setdefault(rec["k"], set()).add((a, b))
        bad += sum(1 for s in flags.values() if len(s) != 1)
    failed += bad
    print(f"  200 trials, {bad} invariant violations")

    print("5) Python/R agreement, row-count guarded:")
    mism = 0
    for name, L, R in FIXTURES:
        py = py_lines(L, R, ["k"])
        rr = r_lines(L, R, ["k"])
        if py != rr:
            mism += 1
            print(f"  MISMATCH {name}:")
            for a, b in zip(py, rr):
                mark = "" if a == b else "   <-- differs"
                print(f"    py {a}   R {b}{mark}")
    failed += mism
    print(f"  {len(FIXTURES)} fixtures compared, {mism} mismatches")

    print()
    print("VERIFIED: MERGE BY matches the PDV rule and agrees Python/R"
          if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
