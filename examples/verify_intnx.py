#!/usr/bin/env python3
"""verify_intnx.py : the fixture gate for INTNX alignment and INTCK WEEK
(quirk 17), closing the deferrals the dates section declared.

Pins the BEGINNING default (the landmine: month + 1 from the 15th lands on
the 1st, where every naive same-day idiom lands on the 15th, demonstrated
inline), SAME's end-clipping across leap and non-leap, END, the MIDDLE
floor-midpoint, Sunday-first weeks anchored to the epoch's own Friday, and
INTCK WEEK boundary counting. Then a 240-case grid agreement sweep across
intervals, alignments, and edge dates, Python against base R, row-count
guarded.
"""

import datetime
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import (date_to_sas, sas_date, sas_intck_week,  # noqa: E402
                           sas_intnx)

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"


def d(y, m, dd):
    return date_to_sas(datetime.date(y, m, dd))


PINS = [
    (("month", d(2020, 1, 15), 1, "B"), d(2020, 2, 1)),
    (("month", d(2020, 1, 31), 1, "SAME"), d(2020, 2, 29)),
    (("month", d(2021, 1, 31), 1, "S"), d(2021, 2, 28)),
    (("month", d(2020, 1, 15), 0, "E"), d(2020, 1, 31)),
    (("month", d(2020, 1, 1), 0, "M"), d(2020, 1, 16)),
    (("week", 0, 0, "B"), -5),
    (("week", 0, 0, "E"), 1),
    (("year", d(2020, 2, 29), 1, "SAME"), d(2021, 2, 28)),
    (("qtr", d(2020, 5, 20), 1, "B"), d(2020, 7, 1)),
    (("day", d(2020, 1, 15), 10, "B"), d(2020, 1, 25)),
]

WEEK_PINS = [((d(2020, 1, 4), d(2020, 1, 5)), 1),
             ((d(2020, 1, 5), d(2020, 1, 11)), 0),
             ((d(2020, 1, 5), d(2020, 1, 4)), -1)]


def r_lane(cmd, header, rows):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join(row) + "\n")
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "intnx.R"), cmd, path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = [ln for ln in out.stdout.splitlines() if ln]
    if not lines[0].startswith("n=") or int(lines[0][2:]) != len(rows):
        raise RuntimeError("row-count guard failed")
    return [int(x) for x in lines[1:]]


def main() -> int:
    failed = 0

    print("1) alignment pins (BEGINNING default, SAME clips, END, MIDDLE,")
    print("   Sunday weeks):")
    for (iv, days, inc, al), want in PINS:
        got = sas_intnx(iv, days, inc, al)
        if got != want:
            failed += 1
            print(f"  FAIL intnx({iv},{sas_date(days)},{inc},{al}) = "
                  f"{sas_date(got)} want {sas_date(want)}")
    print(f"  {len(PINS)} pins checked")

    print("2) the naive same-day landmine:")
    naive = d(2020, 2, 15)
    sas = sas_intnx("month", d(2020, 1, 15), 1)
    if sas == naive:
        failed += 1
        print("  FAIL expected divergence")
    print(f"  SAS default lands {sas_date(sas)}, same-day idioms land "
          f"{sas_date(naive)}: pinned apart")

    print("3) INTCK WEEK boundaries:")
    for (a, b), want in WEEK_PINS:
        if sas_intck_week(a, b) != want:
            failed += 1
            print(f"  FAIL week({sas_date(a)},{sas_date(b)})")
    print(f"  {len(WEEK_PINS)} pins (Saturday to Sunday counts, within-week"
          " does not, negative reverses)")

    print("4) Python/R agreement grid, row-count guarded:")
    dates = [d(2020, 1, 15), d(2020, 1, 31), d(2020, 2, 29), d(2021, 12, 31),
             d(1959, 6, 3), 0]
    grid = [(iv, dd, inc, al)
            for iv in ("day", "week", "month", "qtr", "year")
            for dd in dates
            for inc in (-1, 0, 1, 5)
            for al in ("B", "E")] + \
           [(iv, dd, 1, al)
            for iv in ("month", "year")
            for dd in dates
            for al in ("M", "SAME")]
    py = [sas_intnx(*case) for case in grid]
    rr = r_lane("intnx", ["interval", "days", "inc", "align"],
                [['"' + c[0] + '"', str(c[1]), str(c[2]), '"' + c[3] + '"']
                 for c in grid])
    mism = sum(1 for a, b in zip(py, rr) if a != b)
    for i, (a, b) in enumerate(zip(py, rr)):
        if a != b:
            print(f"  MISMATCH {grid[i]}: py {sas_date(a)} vs R {sas_date(b)}")
    wk = [(a, b) for (a, b), _w in WEEK_PINS]
    rw = r_lane("week", ["d1", "d2"], [[str(a), str(b)] for a, b in wk])
    mism += sum(1 for (a, b), r in zip(wk, rw) if sas_intck_week(a, b) != r)
    failed += mism
    print(f"  {len(grid)} grid cases plus {len(wk)} week cases, "
          f"{mism} mismatches")

    print()
    print("VERIFIED: INTNX alignment and INTCK WEEK match the rule and agree "
          "Python/R" if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
