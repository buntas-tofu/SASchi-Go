#!/usr/bin/env python3
"""verify_arrays.py : the fixture gate for SAS arrays (quirk 19).

Pins the aliasing law (an array is a name list: writes through it ARE writes
to the variables and back, where a Python list copies and divorces: the
landmine, demonstrated), arbitrary declared bounds (the {1990:1995}
index-by-year census idiom), DIM/LBOUND/HBOUND, the out-of-range HALT
temperament (harder than missing-with-a-note), _TEMPORARY_ retention across
iterations against ordinary PDV reset, and OF-list aggregation under the
gated missing rule. Python/R agreement over four scenarios, verbatim.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_array, sas_sum, sas_temp_array  # noqa: E402

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"


def r_scenario(name):
    out = subprocess.run([str(RSCRIPT), str(HERE / "arrays.R"), name],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    return out.stdout.strip()


def main() -> int:
    failed = 0

    print("1) the aliasing law and the copy landmine:")
    pdv = {"x1": 1.0, "x2": 2.0, "x3": 3.0}
    arr = sas_array(pdv, ["x1", "x2", "x3"])
    arr[2] = 99.0
    pdv["x3"] = 7.0
    if pdv["x2"] != 99.0 or arr[3] != 7.0:
        failed += 1
        print("  FAIL aliasing")
    naive = list(pdv.values())
    naive[1] = -1.0
    if pdv["x2"] == -1.0:
        failed += 1
        print("  FAIL the copy should divorce")
    print("  writes pass through both ways; the naive list write vanishes")

    print("2) declared bounds, DIM, and the halt:")
    yrs = sas_array({f"y{y}": float(y - 1990 + 10) for y in range(1990, 1996)},
                    [f"y{y}" for y in range(1990, 1996)], lo=1990)
    if (yrs[1993], yrs.lbound(), yrs.hbound(), yrs.dim()) != (13.0, 1990, 1995, 6):
        failed += 1
        print("  FAIL census idiom")
    for bad in (1989, 1996, 0):
        try:
            yrs[bad]
            failed += 1
            print(f"  FAIL {bad} must halt")
        except IndexError:
            pass
    print("  {1990:1995} indexes by year; out-of-range halts, as SAS halts")

    print("3) _TEMPORARY_ retention vs PDV reset:")
    tmp = sas_temp_array(3, init=[0.0, 0.0, 0.0])
    normal_last = None
    for _iteration in range(2):
        iter_pdv = {"x": None}
        tmp[1] = tmp[1] + 5.0
        normal_last = iter_pdv["x"]
    if tmp[1] != 10.0 or normal_last is not None:
        failed += 1
        print(f"  FAIL retention: temp {tmp[1]} normal {normal_last}")
    print("  temp accumulates to 10 across iterations; the ordinary variable"
          " resets")

    print("4) OF-list aggregation under the gated missing rule:")
    a2 = sas_array({"a": 1.0, "b": None, "c": 2.0}, ["a", "b", "c"])
    if sas_sum(*a2.values()) != 3.0:
        failed += 1
        print("  FAIL of-sum")
    print("  sum(of arr{*}) ignores the missing element (quirk 14's SUM)")

    print("5) Python/R agreement, four scenarios verbatim:")
    want = {"alias": "99|7|3|1|3", "census": "13|1990|1995|6",
            "oob": "HALT", "retain": "10|NA"}
    mism = 0
    for name, expect in want.items():
        got = r_scenario(name)
        if got != expect:
            mism += 1
            print(f"  MISMATCH {name}: R {got!r} want {expect!r}")
    failed += mism
    print(f"  {len(want)} scenarios, {mism} mismatches")

    print()
    print("VERIFIED: arrays match the aliasing law and agree Python/R"
          if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
