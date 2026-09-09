#!/usr/bin/env python3
"""verify_sort.py : the fixture gate for PROC SORT ordering (quirk 9).

Proves missing-sorts-first (and reverses to last under DESCENDING), EQUALS
stability (the pin that settles the drafts' NOEQUALS/EQUALS dispute from the
documented spec), byte collation with blank-padding ties, NODUPKEY
first-occurrence, and the numeric-as-character lexical trap, against
hand-pins; demonstrates the naive missing-last landmine; sweeps a seeded
property loop; and proves Python/R agreement with a row-count guard on the R
harness (the quirk-7 lesson: check what the fixture loader actually loaded).
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
from sas_semantics import (is_sas_missing, sas_proc_sort,  # noqa: E402
                           sas_sort_key)

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"
NAN = float("nan")

# P1: numeric with missings and a negative; missing first, input order held.
P1_ROWS = [{"i": 0, "x": 5.0}, {"i": 1, "x": None}, {"i": 2, "x": -3.0},
           {"i": 3, "x": NAN}, {"i": 4, "x": 0.0}]
P1_PIN = [1, 3, 2, 4, 0]

# P2: EQUALS stability, the disputed pin: ties keep input order.
P2_ROWS = [{"i": 0, "k": 1.0, "m": "a"}, {"i": 1, "k": 2.0, "m": "b"},
           {"i": 2, "k": 1.0, "m": "c"}, {"i": 3, "k": 2.0, "m": "d"},
           {"i": 4, "k": 1.0, "m": "e"}]
P2_PIN = ["a", "c", "e", "b", "d"]

# P3: byte collation, blanks first ('' and ' ' tie via padding), "B" < "a".
P3_ROWS = [{"i": 0, "s": " "}, {"i": 1, "s": "apple"}, {"i": 2, "s": "B"},
           {"i": 3, "s": ""}, {"i": 4, "s": "a"}]
P3_PIN = [0, 3, 2, 4, 1]

# P4: trailing-blank tie is a duplicate to NODUPKEY; first occurrence kept.
P4_ROWS = [{"i": 0, "s": "a "}, {"i": 1, "s": "a"}, {"i": 2, "s": "b"}]
P4_PIN = [0, 2]

# P5: BY g ascending, x DESCENDING, with an x-tie (stability inside the
# reversal) and a missing x (lands LAST under descending, the SAS reversal).
P5_ROWS = [{"i": 0, "g": 1.0, "x": 1.0}, {"i": 1, "g": 2.0, "x": 5.0},
           {"i": 2, "g": 1.0, "x": 9.0}, {"i": 3, "g": 2.0, "x": 2.0},
           {"i": 4, "g": 1.0, "x": 9.0}, {"i": 5, "g": 2.0, "x": None}]
P5_BY = [("g", "ascending"), ("x", "descending")]
P5_PIN = [2, 4, 0, 1, 3, 5]

# P6: numeric-as-character sorts lexically by byte: the classic trap.
P6_ROWS = [{"i": 0, "s": "10"}, {"i": 1, "s": "2"}, {"i": 2, "s": "1"},
           {"i": 3, "s": "30"}]
P6_PIN = [2, 0, 1, 3]


def order_of(rows, by, nodupkey=False):
    return [int(r["i"]) for r in sas_proc_sort(rows, by, nodupkey=nodupkey)]


def r_order(rows, cols, byspec, nodupkey=False):
    """Run the R twin over the same fixture and return its marker order,
    guarding the row count so a fixture-eating loader can never mint a pin."""
    # Per-type CSV formatting, hand-rolled: R's scan() rejects QUOTED numeric
    # fields once colClasses pins the type, so numerics go bare (NA for
    # missing) and characters go quoted (preserving blanks, escaping quotes).
    types = {"i": "num", **dict(cols)}
    names = ["i"] + [c for c, _t in cols]

    def cell(r, k):
        v = r.get(k)
        if types[k] == "num":
            if v is None or (isinstance(v, float) and v != v):
                return "NA"
            return repr(float(v))
        return '"' + str(v).replace('"', '""') + '"'

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write(",".join(names) + "\n")
        for r in rows:
            f.write(",".join(cell(r, k) for k in names) + "\n")
        path = f.name
    colspec = ",".join(["i:num"] + [f"{c}:{t}" for c, t in cols])
    out = subprocess.run([str(RSCRIPT), str(HERE / "sort.R"), path, colspec,
                          byspec, "1" if nodupkey else "0"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("n="):
        raise RuntimeError("R twin printed no row-count guard")
    if int(lines[0][2:]) != len(rows):
        raise RuntimeError(f"R loaded {lines[0][2:]} rows, wrote {len(rows)}: "
                           "harness defect, no verdict")
    return [int(float(x)) for x in lines[1:]]


def main() -> int:
    failed = 0

    print("1) hand-pins (missing-first, stability, collation, nodupkey,")
    print("   descending reversal, lexical trap):")
    checks = [
        ("missing-first", order_of(P1_ROWS, ["x"]), P1_PIN),
        ("EQUALS stability",
         [r["m"] for r in sas_proc_sort(P2_ROWS, ["k"])], P2_PIN),
        ("byte collation", order_of(P3_ROWS, ["s"]), P3_PIN),
        ("nodupkey", order_of(P4_ROWS, ["s"], nodupkey=True), P4_PIN),
        ("desc + missing-last", order_of(P5_ROWS, P5_BY), P5_PIN),
        ("lexical '10'<'2'", order_of(P6_ROWS, ["s"]), P6_PIN),
    ]
    for name, got, want in checks:
        if got != want:
            failed += 1
            print(f"  FAIL {name}: {got} want {want}")
    print(f"  {len(checks)} pins checked")

    print("2) the landmine (naive missing-last sort, the pandas/R default):")
    naive = [r["i"] for r in sorted(
        P1_ROWS, key=lambda r: float("inf") if is_sas_missing(r["x"])
        else r["x"])]
    diverge = naive != P1_PIN
    print(f"  naive {naive} vs SAS {P1_PIN}: {'diverges' if diverge else 'AGREES'}")
    if not diverge:
        failed += 1
        print("  FAIL: expected the naive order to diverge")

    print("3) property sweep (seeded, 300 trials: stability, missing block,")
    print("   nodupkey first-occurrence):")
    rng = random.Random(19830715)
    bad = 0
    for _ in range(300):
        n = rng.randint(0, 12)
        recs = [{"i": i, "g": float(rng.randint(0, 2)),
                 "x": rng.choice([None, NAN, -3.0, -1.0, 0.0, 1.0, 2.0, 3.0])}
                for i in range(n)]
        xdir = rng.choice(["ascending", "descending"])
        by = [("g", "ascending"), ("x", xdir)]

        def fkey(r):
            return (repr(sas_sort_key(r["g"])), repr(sas_sort_key(r["x"])))

        out = sas_proc_sort(recs, by)
        for a, b in zip(out, out[1:]):
            if fkey(a) == fkey(b) and a["i"] > b["i"]:
                bad += 1  # tie left input order: EQUALS broken
        for a, b in zip(out, out[1:]):
            if a["g"] == b["g"]:
                am, bm = is_sas_missing(a["x"]), is_sas_missing(b["x"])
                if xdir == "ascending" and bm and not am:
                    bad += 1  # a missing after a value, ascending
                if xdir == "descending" and am and not bm:
                    bad += 1  # a missing before a value, descending
        nd = sas_proc_sort(recs, by, nodupkey=True)
        keys = [fkey(r) for r in nd]
        if len(set(keys)) != len(keys):
            bad += 1
        for r in nd:
            if r["i"] != min(q["i"] for q in recs if fkey(q) == fkey(r)):
                bad += 1
    failed += bad
    print(f"  300 trials, {bad} invariant violations")

    print("4) Python/R agreement (radix twin, row-count guarded):")
    pairs = [
        ("P1", order_of(P1_ROWS, ["x"]),
         r_order(P1_ROWS, [("x", "num")], "x:asc")),
        ("P3", order_of(P3_ROWS, ["s"]),
         r_order(P3_ROWS, [("s", "chr")], "s:asc")),
        ("P4", order_of(P4_ROWS, ["s"], nodupkey=True),
         r_order(P4_ROWS, [("s", "chr")], "s:asc", nodupkey=True)),
        ("P5", order_of(P5_ROWS, P5_BY),
         r_order(P5_ROWS, [("g", "num"), ("x", "num")], "g:asc,x:desc")),
        ("P6", order_of(P6_ROWS, ["s"]),
         r_order(P6_ROWS, [("s", "chr")], "s:asc")),
    ]
    for name, py, r in pairs:
        if py != r:
            failed += 1
            print(f"  FAIL {name}: python {py} vs R {r}")
    print(f"  {len(pairs)} fixtures compared, "
          f"{sum(1 for _n, a, b in pairs if a != b)} mismatches")

    print()
    print("VERIFIED: PROC SORT ordering matches the rule and agrees Python/R"
          if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
