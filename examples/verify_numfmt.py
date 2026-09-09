#!/usr/bin/env python3
"""verify_numfmt.py : the fixture gate for numeric precision (quirk 10) and
PUT rendering (quirk 11).

Precision: the 2**53 integer cliff (a Python int survives where a SAS numeric
collapses), the LENGTH-truncation byte rule against the documented
largest-exact-integer table, FUZZ's 1e-12 window, and the decimal-math myth
pin (0.1 + 0.2 misses 0.3 identically everywhere). Rendering: w.d ties half
away from zero on the stored double (the 2.5 pin the drafts' naive formatters
fail), the 2.675 myth-buster, decimals-drop-to-fit, asterisk overflow,
missing as a right-justified period (both dossiers said blanks; the spec
says period), DATE9., and YYMMDD8. with the quirk-7 temperament (the pin
that corrects a dossier fixture's 19760 to the arithmetic's 23376). Then
Python/R agreement across every lane, row-count guarded.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import (SAS_MAX_EXACT_INT, sas_fuzz,  # noqa: E402
                           sas_input_yymmdd8, sas_num, sas_num_trunc,
                           sas_put_date9, sas_putn)

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

TRUNC_CASES = [(8193.0, 3), (8192.0, 3), (2097153.0, 4), (0.1, 4), (0.1, 8),
               (1.0 / 3.0, 5), (-8193.0, 3), (123456.789, 6)]
FUZZ_CASES = [1.000000000001, 1.00001, 0.9999999999995, -2.0000000000001,
              42.0, 0.5]
PUTN_CASES = [(2.5, 3, 0), (-2.5, 4, 0), (2.675, 4, 2), (123.456, 5, 1),
              (12345.678, 5, 2), (999999.0, 5, 0), (0.5, 3, 0),
              (None, 8, 0), (1.25, 6, 1), (-0.001, 6, 3)]
DATE9_CASES = [0, 23376, 21974, -365]
YYMMDD_CASES = ["20240101", "19600101", " 19600102", "2024013X", "20200229"]


def r_lane(cmd, header, rows, quoted=False):
    """Run one numfmt.R lane; return printed lines, row-count guarded."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join(row) + "\n")
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "numfmt.R"), cmd, path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = out.stdout.splitlines()
    if not lines or not lines[0].startswith("n="):
        raise RuntimeError("numfmt.R printed no row-count guard")
    if int(lines[0][2:]) != len(rows):
        raise RuntimeError("R loaded a different row count: harness defect")
    body = [ln for ln in lines[1:] if ln != ""]
    if quoted:
        body = [ln[1:-1] for ln in body]
    return body


def main() -> int:
    failed = 0

    print("1) the 2**53 integer cliff (Python int survives, SAS numeric")
    print("   collapses):")
    cliff = [(2 ** 53, 9007199254740992.0),
             (2 ** 53 + 1, 9007199254740992.0),
             (12345678901234567, 12345678901234568.0)]
    for raw, want in cliff:
        got = sas_num(raw)
        if got != want or (raw == 2 ** 53 + 1 and int(raw) == int(got)):
            failed += 1
            print(f"  FAIL sas_num({raw}) = {got!r} want {want!r}")
    print(f"  {len(cliff)} pins checked (and 2**53+1 != its stored double)")

    print("2) LENGTH truncation vs the documented exact-integer table:")
    bad = 0
    for length, mx in SAS_MAX_EXACT_INT.items():
        if sas_num_trunc(mx, length) != float(mx):
            bad += 1
            print(f"  FAIL max exact {mx} not preserved at length {length}")
        if length < 8 and sas_num_trunc(mx + 1.0, length) == mx + 1.0:
            bad += 1
            print(f"  FAIL {mx}+1 survived length {length} untruncated")
    if sas_num_trunc(8193.0, 3) != 8192.0:
        bad += 1
        print("  FAIL 8193 at length 3 should truncate to 8192")
    failed += bad
    print(f"  6 lengths checked, {bad} failures")

    print("3) FUZZ window and the decimal-math myth:")
    # The literal 1.000000000001 STORES as a double 1.0000000827e-12 from 1,
    # just OUTSIDE the 1e-12 window, so FUZZ leaves it alone; the dossier
    # fixture that fuzzed it to 1 measured decimal distance, not the stored
    # double. 1.0000000000005 (5e-13) is genuinely inside.
    fz = [(1.0000000000005, 1.0), (1.000000000001, 1.000000000001),
          (1.00001, 1.00001), (0.9999999999995, 1.0), (42.0, 42.0)]
    for x, want in fz:
        if sas_fuzz(x) != want:
            failed += 1
            print(f"  FAIL FUZZ({x}) = {sas_fuzz(x)} want {want}")
    if (0.1 + 0.2) == 0.3:
        failed += 1
        print("  FAIL: expected IEEE, found decimal arithmetic??")
    print(f"  {len(fz)} FUZZ pins; 0.1 + 0.2 != 0.3 holds (IEEE, as in SAS)")

    print("4) PUT w.d rendering pins:")
    pins = [((2.5, 3, 0), "  3"), ((-2.5, 4, 0), "  -3"),
            ((2.675, 4, 2), "2.67"), ((123.456, 5, 1), "123.5"),
            ((12345.678, 5, 2), "12346"), ((999999.0, 5, 0), "*****"),
            ((0.5, 3, 0), "  1"), ((None, 8, 0), "       ."),
            ((1.25, 6, 1), "   1.3"), ((-0.001, 6, 3), "-0.001")]
    for (v, w, d), want in pins:
        got = sas_putn(v, w, d)
        if got != want:
            failed += 1
            print(f"  FAIL putn{(v, w, d)} = {got!r} want {want!r}")
    print(f"  {len(pins)} pins checked (ties away, decimals drop, asterisks,")
    print("   missing prints '.')")

    print("5) DATE9. and YYMMDD8. pins:")
    dp = [(0, "01JAN1960"), (23376, "01JAN2024"), (21974, "29FEB2020"),
          (-365, "01JAN1959")]
    for days, want in dp:
        got = sas_put_date9(days)
        if got != want:
            failed += 1
            print(f"  FAIL date9({days}) = {got} want {want}")
    ip = [("20240101", 23376.0), ("19600101", 0.0), (" 19600102", 1.0),
          ("2024013X", None), ("20200229", 21974.0)]
    for s, want in ip:
        got = sas_input_yymmdd8(s)
        if got != want:
            failed += 1
            print(f"  FAIL yymmdd8({s!r}) = {got} want {want}")
    print(f"  {len(dp)} render pins, {len(ip)} input pins (23376, not the")
    print("   dossier's 19760; unparsable reads as missing)")

    print("6) Python/R agreement, all lanes, row-count guarded:")

    def lane(name, py_list, r_list, eq):
        m = 0
        for i, (a, b) in enumerate(zip(py_list, r_list)):
            if not eq(a, b):
                m += 1
                print(f"  MISMATCH {name}[{i}]: py {a!r} vs R {b!r}")
        return m

    mism = 0
    mism += lane("trunc",
                 [sas_num_trunc(v, length) for v, length in TRUNC_CASES],
                 r_lane("trunc", ["value", "len"],
                        [[repr(v), str(length)] for v, length in TRUNC_CASES]),
                 lambda a, b: float(b) == a)
    mism += lane("fuzz", [sas_fuzz(v) for v in FUZZ_CASES],
                 r_lane("fuzz", ["value"], [[repr(v)] for v in FUZZ_CASES]),
                 lambda a, b: float(b) == a)
    mism += lane("putn", [sas_putn(v, w, d) for v, w, d in PUTN_CASES],
                 r_lane("putn", ["value", "w", "d"],
                        [["NA" if v is None else repr(v), str(w), str(d)]
                         for v, w, d in PUTN_CASES], quoted=True),
                 lambda a, b: a == b)
    mism += lane("date9", [sas_put_date9(v) for v in DATE9_CASES],
                 r_lane("date9", ["days"], [[str(v)] for v in DATE9_CASES]),
                 lambda a, b: a == b)
    mism += lane("yymmdd", [sas_input_yymmdd8(s) for s in YYMMDD_CASES],
                 r_lane("yymmdd", ["s"], [['"' + s + '"'] for s in YYMMDD_CASES]),
                 lambda a, b: ((b == "NA") == (a is None)
                               and (b == "NA" or float(b) == a)))
    failed += mism
    n_cases = (len(TRUNC_CASES) + len(FUZZ_CASES) + len(PUTN_CASES)
               + len(DATE9_CASES) + len(YYMMDD_CASES))
    print(f"  {n_cases} fixtures across 5 lanes, {mism} mismatches")

    print()
    print("VERIFIED: numeric precision and PUT rendering match the rule and "
          "agree Python/R" if failed == 0
          else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
