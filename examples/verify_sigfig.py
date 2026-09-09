#!/usr/bin/env python3
"""verify_sigfig.py : the fixture gate for significant-digit rendering and
rounding (rulebook DS-020, the four-sig-fig surface).

SAS has no %g-style significant-digit format. The four-significant-digit policy
is realized by rounding the value to an explicit power-of-ten unit with ROUND
(half away from zero, fuzzed), then rendering
with a normal format. R sprintf('%g') and Python '%g' formatting BOTH round
half to even, so a translation that reaches for %g or signif() to do SAS
sig-fig work disagrees exactly where the policy lives: 0.125 to two digits
is 0.13 in SAS and 0.12 in both open languages, and 9.995 to three digits
is 10.0 in SAS (the ROUND fuzz absorbs the representation error) and 9.99
in both.

The gate: five C-printf render modes byte-equal Python/R, the SAS-equivalent
unit computation byte-equal Python/R at 17 digits, and the signif half-even
divergence pinned as the landmine demonstration.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_sigfig_round  # noqa: E402

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

RENDER = [("plain", "%.4g"), ("prespace", "% .4g"), ("sign", "%+.4g"),
          ("sci_e", "%e"), ("sci_E", "%E")]
VALUES = [3.141592653589793, 123456.789, 123.456, 0.0000123456789,
          -0.0012345, 987654321.0, 12345.6789, 0.5, 1.0 / 3.0, -2.5,
          9.995, 0.125]
SAS_CASES = [(v, 4) for v in VALUES] + [(0.0, 4), (123.0, 4), (1.0, 3)]
SIGNIF_CASES = [(0.125, 2), (9.995, 3), (-2.5, 1), (0.5, 1),
                (3.141592653589793, 4), (123456.789, 4)]

# SAS-equivalent pins (unit then half-away): agreed R 4.3.3 and reference
# 2026-09-09. The landmine cases are the point: 0.125@2 and 9.995@3.
SAS_PINS = {
    (0.125, 2): "0.13",
    (9.995, 3): "10",
    (-2.5, 1): "-3",
}


def r_lane(cmd, rows, header):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join(str(v) for v in row) + "\n")
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "sigfig.R"), cmd, path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = out.stdout.splitlines()
    if not lines or not lines[0].startswith("n="):
        raise RuntimeError("sigfig.R printed no row-count guard")
    if int(lines[0][2:]) != len(rows):
        raise RuntimeError("R loaded a different row count: harness defect")
    return [ln for ln in lines[1:] if ln != ""]


def main() -> int:
    failed = 0

    print("1) C-printf render modes byte-equal Python/R (five modes,"
          f" {len(VALUES)} values):")
    mism = 0
    for mode, fmt in RENDER:
        r_out = r_lane("render", [(v, mode) for v in VALUES],
                       ["value", "mode"])
        py_out = [fmt % v for v in VALUES]
        for i, (r, p) in enumerate(zip(r_out, py_out)):
            if r != p:
                mism += 1
                print(f"  MISMATCH {mode}[{i}] ({VALUES[i]}): R {r!r}"
                      f" py {p!r}")
    failed += mism
    print(f"  {len(RENDER) * len(VALUES)} renderings, {mism} mismatches")

    print("2) SAS-equivalent unit rounding, byte-equal at 17 digits,"
          f" {len(SAS_CASES)} cases:")
    r_out = r_lane("sas", SAS_CASES, ["value", "n"])
    py_out = [format(sas_sigfig_round(v, n), ".17g") for v, n in SAS_CASES]
    mism = 0
    for i, (r, p) in enumerate(zip(r_out, py_out)):
        if r != p:
            mism += 1
            print(f"  MISMATCH sas[{i}] ({SAS_CASES[i]}): R {r!r}"
                  f" py {p!r}")
    failed += mism
    print(f"  {len(SAS_CASES)} cases, {mism} mismatches")

    print("3) hand-pinned SAS-equivalent values:")
    for (v, n), want in SAS_PINS.items():
        got = format(sas_sigfig_round(v, n), ".17g")
        if got != want:
            failed += 1
            print(f"  FAIL sas_sigfig_round({v}, {n}) = {got!r}"
                  f" want {want!r}")
    print(f"  {len(SAS_PINS)} pins (the half-away cases)")

    print("4) the landmine, demonstrated:")
    g = format(0.125, ".2g")
    if g != "0.12":
        failed += 1
        print(f"  FAIL: %g on 0.125@2 gave {g!r}, expected '0.12'")
    if format(9.995, ".3g") != "9.99":
        failed += 1
        print("  FAIL: %g on 9.995@3 did not give '9.99'")
    if sas_sigfig_round(0.125, 2) != 0.13 or sas_sigfig_round(9.995, 3) != 10.0:
        failed += 1
        print("  FAIL: SAS-equivalent half-away pins moved")
    print(f"  %g/signif half-even: 0.125 -> {g} and 9.995 -> 9.99;"
          " SAS ROUND half-away: 0.13 and 10.0")
    print("  Never emit %g/%.Ng/signif alone for SAS sig-fig work; round to")
    print("  the explicit power-of-ten unit first.")

    print()
    print("VERIFIED: sig-fig rendering and SAS-equivalent rounding match the"
          " rule and agree Python/R" if failed == 0
          else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
