#!/usr/bin/env python3
"""verify_intck.py : the fixture gate for SAS INTCK (date-boundary counting).

Same three duties as the rounding gate, plus the oracle:
1. Hand-pinned assertions from the discrete-INTCK rule (human arithmetic).
2. The landmine: a naive elapsed-time translation diverging on the boundaries.
3. Cross-language agreement: the R translation (examples/intck.R) must match the
   Python reference on every fixture in a broad sweep. Agreement is the proof.
"""

import csv
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_intck  # noqa: E402

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"
D = datetime.date

# (interval, start, end, expected) pinned BY HAND from the discrete-INTCK rule
HAND_PINNED = [
    ("YEAR",  D(2020, 12, 31), D(2021, 1, 1), 1),    # one Jan-1 boundary, one day elapsed
    ("YEAR",  D(2020, 1, 1),   D(2020, 12, 31), 0),  # same year, no boundary
    ("YEAR",  D(2000, 6, 15),  D(2010, 6, 15), 10),
    ("MONTH", D(2021, 1, 31),  D(2021, 2, 1), 1),    # one month boundary, one day elapsed
    ("MONTH", D(2021, 1, 1),   D(2021, 1, 31), 0),
    ("MONTH", D(2020, 12, 1),  D(2021, 1, 1), 1),    # across the year boundary
    ("QTR",   D(2021, 3, 31),  D(2021, 4, 1), 1),    # Q1 -> Q2
    ("QTR",   D(2021, 1, 1),   D(2021, 3, 31), 0),
    ("DAY",   D(2021, 1, 1),   D(2021, 1, 10), 9),
    ("YEAR",  D(2021, 1, 1),   D(2020, 12, 31), -1),  # reversed, negative
]


def naive_intck(interval, start, end):
    """What a hurried migrator writes: whole elapsed intervals, not boundaries."""
    iv = interval.upper()
    if iv == "DAY":
        return (end - start).days
    if iv == "YEAR":
        yrs = end.year - start.year
        return yrs - (1 if (end.month, end.day) < (start.month, start.day) else 0)
    if iv == "MONTH":
        months = (end.year - start.year) * 12 + (end.month - start.month)
        return months - (1 if end.day < start.day else 0)
    if iv == "QTR":
        return naive_intck("MONTH", start, end) // 3
    return 0


def r_answers(fixtures):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["interval", "start", "end"])
        for iv, s, e in fixtures:
            w.writerow([iv, s.isoformat(), e.isoformat()])
        path = fh.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "intck.R"), path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"Rscript failed: {out.stderr.strip()}")
    return [int(x) for x in out.stdout.split()]


def main() -> int:
    failed = 0

    print("1) hand-pinned assertions (reference vs human arithmetic):")
    for iv, s, e, want in HAND_PINNED:
        got = sas_intck(iv, s, e)
        failed += got != want
        if got != want:
            print(f"  FAIL {iv} {s} {e} -> {got} (want {want})")
    print(f"  {len(HAND_PINNED) - failed}/{len(HAND_PINNED)} pinned values pass")

    print("2) the landmine: naive elapsed-time translation vs SAS boundaries:")
    diverged = [(iv, s, e, sas_intck(iv, s, e), naive_intck(iv, s, e))
                for iv, s, e, _ in HAND_PINNED
                if naive_intck(iv, s, e) != sas_intck(iv, s, e)]
    for iv, s, e, sas, naive in diverged:
        print(f"  {iv} {s} -> {e}: SAS says {sas}, naive says {naive}")
    print(f"  {len(diverged)} of {len(HAND_PINNED)} fixtures diverge under naive translation")
    failed += not diverged  # a gate that shows no landmine is a broken gate

    print("3) cross-language agreement (Python reference vs R translation):")
    base = D(2018, 1, 1)
    sweep = [(iv, base + datetime.timedelta(days=d1), base + datetime.timedelta(days=d2))
             for iv in ("YEAR", "MONTH", "QTR", "DAY")
             for d1 in range(0, 1500, 37)
             for d2 in range(0, 1500, 211)]
    py = [sas_intck(iv, s, e) for iv, s, e in sweep]
    r = r_answers(sweep)
    mismatch = sum(1 for a, b in zip(py, r) if a != b)
    failed += mismatch
    print(f"  {len(sweep)} fixtures, {mismatch} Python/R mismatches")

    print()
    print("VERIFIED: INTCK matches the discrete rule and agrees Python/R"
          if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
