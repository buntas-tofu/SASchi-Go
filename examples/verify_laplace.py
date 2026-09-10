#!/usr/bin/env python3
"""verify_laplace.py : the fixture gate for the Laplace distribution
surface (rulebook ST-016, the noise lane).

The deterministic surface of the Laplace distribution is three closed
forms: the density f(x) = exp(-|x - m|/s) / (2s), the CDF (two branches,
0.5 exactly at the location), and the quantile, which is also the
inverse-CDF construction that turns a pinned uniform value into a draw.
SAS documents PDF/CDF/QUANTILE('LAPLACE', x, theta, lambda) with location
theta (default 0) and scale lambda (default 1), and the documentation's
own worked value for the single-argument form PDF('LAPLACE', 1) is
0.18393972058572117, pinned below.

Draw streams are incomparable across engines by construction, so nothing
here ever compares draws: the gate proves the distribution instead. The
landmines: a density is not a draw (the origin-era workaround added a
constant density value as its noise), the single-argument form means
x = 1 with the default parameters, never a lone scale, and swapping the
location and scale roles yields two well-formed but different numbers.

Pins were derived from the pure reference first; scipy 1.18 and R 4.3.3
were cross-checked before pinning. The R lane replicates the reference
arithmetic operation for operation, so its agreement is byte-level at 17
digits. scipy agrees byte-level on 24 of 26 pinned values; the remaining
two sit one unit in the last place apart at the log(1 - 2u) seam, so the
scipy lane is a 1e-15 relative check rather than byte-equality.
"""

import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import (  # noqa: E402
    sas_laplace_cdf,
    sas_laplace_pdf,
    sas_laplace_quantile,
)

import scipy.stats  # noqa: E402

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

PDF_CASES = [(1, 0, 1), (0, 0, 1), (-2.5, 0, 1), (1, 2, 3), (3.5, 0, 2),
             (7.25, 5, 2.5), (0.5, 0.5, 0.5), (2.0, 1.0, 1.0)]
CDF_CASES = [(1, 0, 1), (0, 0, 1), (-1, 0, 1), (2, 2, 3), (10, 5, 2),
             (-3.5, 0, 2), (0.25, 0.5, 0.5)]
QUANT_CASES = [(0.75, 0, 1), (0.5, 0, 1), (0.25, 0, 1), (0.5, 5, 2),
               (0.75, 0, 2), (0.9, 0, 1), (0.1, 0, 1), (0.95, 2, 3),
               (0.05, 2, 3), (0.75, 2, 0.5), (0.25, 2, 0.5)]
U_GRID = [(u, 0, 1) for u in (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)]

# Hand-pinned truth. The first entry is SAS's own documentation example
# value; the rest are the closed forms agreed reference/R byte-level and
# scipy to within 1e-15 at pinning time (2026-09-10).
PINS = {
    ("pdf", 1, 0, 1): "0.18393972058572117",
    ("pdf", 0, 0, 1): "0.5",
    ("pdf", -2.5, 0, 1): "0.0410424993119494",
    ("pdf", 1, 2, 3): "0.11942188509563155",
    ("pdf", 3.5, 0, 2): "0.043443485862611285",
    ("cdf", 1, 0, 1): "0.81606027941427883",
    ("cdf", 0, 0, 1): "0.5",
    ("cdf", -1, 0, 1): "0.18393972058572117",
    ("cdf", 2, 2, 3): "0.5",
    ("cdf", 10, 5, 2): "0.95895750068805063",
    ("quant", 0.75, 0, 1): "0.69314718055994529",
    ("quant", 0.5, 0, 1): "0",
    ("quant", 0.25, 0, 1): "-0.69314718055994529",
    ("quant", 0.5, 5, 2): "5",
    ("quant", 0.75, 0, 2): "1.3862943611198906",
    ("quant", 0.9, 0, 1): "1.6094379124341005",
    ("quant", 0.1, 0, 1): "-1.6094379124341005",
    ("quant", 0.75, 2, 0.5): "2.3465735902799727",
}

FUNCS = {"pdf": sas_laplace_pdf, "cdf": sas_laplace_cdf,
         "quant": sas_laplace_quantile}
SCIPY = {"pdf": scipy.stats.laplace.pdf, "cdf": scipy.stats.laplace.cdf,
         "quant": scipy.stats.laplace.ppf}


def r_lane(cmd, cases):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write("value,m,s\n")
        for row in cases:
            f.write(",".join(repr(float(v)) for v in row) + "\n")
        path = f.name
    out = subprocess.run(
        [str(RSCRIPT), str(HERE / "laplace.R"), cmd, path],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = out.stdout.splitlines()
    if not lines or not lines[0].startswith("n="):
        raise RuntimeError("laplace.R printed no row-count guard")
    if int(lines[0][2:]) != len(cases):
        raise RuntimeError("R loaded a different row count: harness defect")
    return [ln for ln in lines[1:] if ln != ""]


def main() -> int:
    failed = 0

    print("1) reference surface vs the R lane, byte-equal at 17 digits:")
    lanes = (("pdf", PDF_CASES), ("cdf", CDF_CASES), ("quant", QUANT_CASES))
    total = mism = 0
    for cmd, cases in lanes:
        r_out = r_lane(cmd, cases)
        py_out = [format(FUNCS[cmd](*row), ".17g") for row in cases]
        for row, r, p in zip(cases, r_out, py_out):
            total += 1
            if r != p:
                mism += 1
                print(f"  MISMATCH {cmd}{row}: R {r!r} py {p!r}")
    failed += mism
    print(f"  {total} cases across three lanes, {mism} mismatches")

    print("2) hand-pinned truth:")
    pin_fail = 0
    for (cmd, a, b, c), want in PINS.items():
        got = format(FUNCS[cmd](a, b, c), ".17g")
        if got != want:
            pin_fail += 1
            print(f"  FAIL {cmd}({a}, {b}, {c}) = {got!r} want {want!r}")
    failed += pin_fail
    print(f"  {len(PINS)} pins, {pin_fail} failures"
          " (first pin is SAS's own documentation example value)")

    print("3) scipy cross-check (1e-15 relative; byte count reported):")
    sc_mism = sc_bytes = sc_total = 0
    for cmd, cases in lanes:
        for row in cases:
            ref = FUNCS[cmd](*row)
            sp = SCIPY[cmd](row[0], loc=row[1], scale=row[2])
            sc_total += 1
            if format(sp, ".17g") == format(ref, ".17g"):
                sc_bytes += 1
            if sp != ref and abs(sp - ref) / abs(ref) > 1e-15:
                sc_mism += 1
                print(f"  MISMATCH {cmd}{row}: scipy {sp!r} ref {ref!r}")
    failed += sc_mism
    print(f"  {sc_total} values, {sc_bytes} byte-identical,"
          f" {sc_mism} outside 1e-15")

    print("4) roundtrip cdf(quantile(p)) = p:")
    rt_bytes = rt_bad = 0
    for row in U_GRID + [(0.5, 2, 3), (0.05, 2, 3), (0.95, 2, 3)]:
        back = sas_laplace_cdf(sas_laplace_quantile(*row), row[1], row[2])
        if back == row[0]:
            rt_bytes += 1
        if abs(back - row[0]) > 1e-15:
            rt_bad += 1
            print(f"  FAIL p={row[0]}: roundtrip {back!r}")
    failed += rt_bad
    print(f"  {len(U_GRID) + 3} probabilities, {rt_bytes} bit-exact,"
          f" {rt_bad} outside 1e-15")

    print("5) the inverse-CDF sampling construction, byte-equal both lanes")
    print("   on a pinned uniform grid (the only verifiable draw lane):")
    r_out = r_lane("quant", U_GRID)
    py_out = [format(sas_laplace_quantile(*row), ".17g") for row in U_GRID]
    sm_mism = sum(1 for r, p in zip(r_out, py_out) if r != p)
    failed += sm_mism
    print(f"  {len(U_GRID)} pinned uniforms, {sm_mism} mismatches")

    print("6) the landmines, demonstrated:")
    single = sas_laplace_pdf(1.0)
    misread = sas_laplace_pdf(0.0)
    ok = single == float(PINS[("pdf", 1, 0, 1)])
    failed += 0 if ok else 1
    print(f"  the single-argument form PDF('LAPLACE', 1) = {single!r}:")
    print(f"  x = 1 with the default parameters, never a lone scale."
          f" A translation that reads it as density at 0 gets {misread!r}.")
    swap_a = sas_laplace_quantile(0.75, 2.0, 0.5)
    swap_b = sas_laplace_quantile(0.75, 0.5, 2.0)
    swap_ok = (format(swap_a, ".17g") == "2.3465735902799727"
               and format(swap_b, ".17g") == "1.8862943611198906")
    failed += 0 if swap_ok else 1
    print(f"  swapping the roles: quantile(0.75, m=2, s=0.5) = {swap_a!r},"
          f" quantile(0.75, m=0.5, s=2) = {swap_b!r};")
    print("  both well-formed, both different: pin the roles explicitly.")
    c = single
    base = [1.0, 2.0, 3.0, 4.0, 5.0]
    shifted = [b + c for b in base]
    dm = math.fsum(shifted) / len(base) - math.fsum(base) / len(base)
    dsd = statistics.pstdev(shifted) - statistics.pstdev(base)
    shift_ok = abs(dm - c) < 1e-15 and abs(dsd) < 1e-12
    failed += 0 if shift_ok else 1
    print(f"  a density is not a draw: adding PDF('LAPLACE', 1) = {c!r}")
    print(f"  to every record shifts the mean by {dm!r} and leaves the"
          f" dispersion unchanged ({dsd!r}): a constant, not noise.")

    print()
    print("VERIFIED: the Laplace surface matches the rule and agrees"
          " reference/R byte-level, scipy within 1e-15" if failed == 0
          else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
