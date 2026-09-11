#!/usr/bin/env python3
"""verify_matrix.py : the fixture gate for the IML matrix surface
(rulebook MX-001, the matrix appendix).

The 2018 matrix worked examples pin every value here: the 2x4 fill, the
horizontal and vertical joins, the transpose, the 3x2 times 2x2 product
[[50, 21], [24, 10], [101, 42]], and the 2x2 inverse [[3, -2], [-7, 5]].
The R lane replays the reference arithmetic (explicit loops, identical
summation order), so its agreement is byte-level at 17 digits. numpy
agrees byte-level on the integer fixtures: products, joins, and
transposes are exact there. One honest seam: the closed-form 2x2 inverse
is exact in the reference and R lanes, while numpy's LAPACK inverse runs
at a 1e-13 relative bar (documented here, not hidden).

The landmines are the point: SAS IML's '*' is matrix multiplication while
R and numpy read '*' as elementwise (the same source line, a valid and
silently different program), and base R fills matrices column-wise while
SAS fills row-wise (the same vector, a transposed matrix). A singular
matrix fails differently in every engine (ValueError raised here, the
token 'singular' from the R lane, LinAlgError from numpy): detection is
the portable part.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import (  # noqa: E402
    sas_iml_elemwise,
    sas_iml_hcat,
    sas_iml_inv2,
    sas_iml_matmul,
    sas_iml_shape,
    sas_iml_transpose,
    sas_iml_vcat,
)

import numpy as np  # noqa: E402

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

C = [[1, 2, 3, 4], [5, 6, 7, 8]]
D = [[9, 10, 11, 12], [13, 14, 15, 16]]
C6 = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16],
      [17, 18, 19, 20], [21, 22, 23, 24]]
B32 = [[3, 5], [2, 2], [9, 8]]
A22 = [[5, 2], [7, 3]]
D22 = [[1, 2], [3, 4]]


def mstr(m):
    return ";".join(" ".join(format(float(x), ".17g") for x in row) for row in m)


def r_lane(cmd, rows, header):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join(str(x) for x in row) + "\n")
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "matrix.R"), cmd, path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = out.stdout.splitlines()
    if not lines or not lines[0].startswith("n="):
        raise RuntimeError("matrix.R printed no row-count guard")
    if int(lines[0][2:]) != len(rows):
        raise RuntimeError("R loaded a different row count: harness defect")
    return [ln for ln in lines[1:] if ln != ""]


def main() -> int:
    failed = 0

    print("1) hand-pinned truth (the 2018 worked examples):")
    checks = [
        ("shape 2x4", mstr(sas_iml_shape(list(range(1, 9)), 2, 4)),
         "1 2 3 4;5 6 7 8"),
        ("transpose", mstr(sas_iml_transpose([[1, 2], [3, 4]])), "1 3;2 4"),
        ("transpose 2x4", mstr(sas_iml_transpose(C)), "1 5;2 6;3 7;4 8"),
        ("hcat", mstr(sas_iml_hcat(C, D)),
         "1 2 3 4 9 10 11 12;5 6 7 8 13 14 15 16"),
        ("vcat", mstr(sas_iml_vcat(C, C6)),
         "1 2 3 4;5 6 7 8;1 2 3 4;5 6 7 8;9 10 11 12;13 14 15 16;"
         "17 18 19 20;21 22 23 24"),
        ("product (guide pin)", mstr(sas_iml_matmul(B32, A22)),
         "50 21;24 10;101 42"),
        ("product 2x2", mstr(sas_iml_matmul(A22, D22)), "11 18;16 26"),
        ("elementwise", mstr(sas_iml_elemwise(A22, D22)), "5 4;21 12"),
        ("inverse (guide pin)", mstr(sas_iml_inv2(A22)), "3 -2;-7 5"),
    ]
    for name, got, want in checks:
        if got != want:
            failed += 1
            print(f"  FAIL {name}: {got!r} want {want!r}")
    print(f"  {len(checks)} pins, {failed} failures")

    print("2) reference surface vs the R lane, byte-equal at 17 digits:")
    lanes = [
        ("shape", [("1 2 3 4 5 6 7 8", "2", "4")], ["value", "n1", "n2"],
         [mstr(sas_iml_shape(list(range(1, 9)), 2, 4))]),
        ("trans", [("1 2;3 4",), ("1 2 3 4;5 6 7 8",)], ["a"],
         [mstr(sas_iml_transpose([[1, 2], [3, 4]])), mstr(sas_iml_transpose(C))]),
        ("hcat", [("1 2 3 4;5 6 7 8", "9 10 11 12;13 14 15 16")], ["a", "b"],
         [mstr(sas_iml_hcat(C, D))]),
        ("vcat", [("1 2 3 4;5 6 7 8",
                   "1 2 3 4;5 6 7 8;9 10 11 12;13 14 15 16;17 18 19 20;"
                   "21 22 23 24")], ["a", "b"], [mstr(sas_iml_vcat(C, C6))]),
        ("mul", [("3 5;2 2;9 8", "5 2;7 3"), ("5 2;7 3", "1 2;3 4")],
         ["a", "b"], [mstr(sas_iml_matmul(B32, A22)),
                      mstr(sas_iml_matmul(A22, D22))]),
        ("elem", [("5 2;7 3", "1 2;3 4")], ["a", "b"],
         [mstr(sas_iml_elemwise(A22, D22))]),
        ("inv2", [("5 2;7 3",)], ["a"], [mstr(sas_iml_inv2(A22))]),
    ]
    total = mism = 0
    for cmd, rows, header, expected in lanes:
        r_out = r_lane(cmd, rows, header)
        for r, want in zip(r_out, expected):
            total += 1
            if r != want:
                mism += 1
                print(f"  MISMATCH {cmd}: R {r!r} ref {want!r}")
    failed += mism
    print(f"  {total} cases across seven lanes, {mism} mismatches")

    print("3) numpy cross-check (byte on the exact lanes, 1e-13 on the")
    print("   LAPACK inverse):")
    np_checks = [
        ("mul (guide pin)", mstr(np.matmul(np.array(B32), np.array(A22)).tolist()),
         "50 21;24 10;101 42"),
        ("mul 2x2", mstr(np.matmul(np.array(A22), np.array(D22)).tolist()),
         "11 18;16 26"),
        ("elem", mstr((np.array(A22) * np.array(D22)).tolist()), "5 4;21 12"),
        ("hcat", mstr(np.hstack([np.array(C), np.array(D)]).tolist()),
         "1 2 3 4 9 10 11 12;5 6 7 8 13 14 15 16"),
        ("vcat", mstr(np.vstack([np.array(C), np.array(C6)]).tolist()),
         "1 2 3 4;5 6 7 8;1 2 3 4;5 6 7 8;9 10 11 12;13 14 15 16;"
         "17 18 19 20;21 22 23 24"),
    ]
    np_fail = 0
    for name, got, want in np_checks:
        if got != want:
            np_fail += 1
            print(f"  FAIL {name}: {got!r} want {want!r}")
    inv_ref = sas_iml_inv2(A22)
    inv_np = np.linalg.inv(np.array([[5.0, 2.0], [7.0, 3.0]])).tolist()
    worst = max(abs(x - y) / abs(y)
                for row_r, row_n in zip(inv_ref, inv_np)
                for x, y in zip(row_r, row_n))
    if worst > 1e-13:
        np_fail += 1
        print(f"  FAIL inv2: numpy rel err {worst:.3e}")
    failed += np_fail
    print(f"  {len(np_checks) + 1} checks, {np_fail} failures"
          f" (inverse at {worst:.2e} relative, LAPACK vs closed form)")

    print("4) the landmines, demonstrated:")
    prod = mstr(sas_iml_matmul(A22, D22))
    elem = mstr(sas_iml_elemwise(A22, D22))
    ok = prod == "11 18;16 26" and elem == "5 4;21 12" and prod != elem
    failed += 0 if ok else 1
    print(f"  the same star: SAS product {prod!r} vs R/numpy '*'" 
          f" elementwise {elem!r}: both valid, silently different.")
    fc = r_lane("fillcol", [("1 2 3 4 5 6 7 8", "2", "4")],
                ["value", "n1", "n2"])[0]
    fill_ok = fc == mstr(sas_iml_transpose(sas_iml_shape(
        list(range(1, 9)), 4, 2)))
    failed += 0 if fill_ok else 1
    print(f"  base R fills column-wise: the same 1:8 vector yields {fc!r}")
    print("  instead of '1 2 3 4;5 6 7 8'. R's default (r, c) fill equals")
    print("  the transpose of the SAS row-major fill of (c, r): byrow")
    print("  TRUE is mandatory for equivalent construction.")
    try:
        sas_iml_inv2([[1, 2], [2, 4]])
        failed += 1
        print("  FAIL: singular reference did not raise")
    except ValueError:
        pass
    sing_r = r_lane("inv2", [("1 2;2 4",)], ["a"])[0]
    if sing_r != "singular":
        failed += 1
        print(f"  FAIL: R lane singular token {sing_r!r}")
    try:
        np.linalg.inv(np.array([[1.0, 2.0], [2.0, 4.0]]))
        failed += 1
        print("  FAIL: singular numpy did not raise")
    except np.linalg.LinAlgError:
        pass
    print("  singular matrix: ValueError here, 'singular' from the R lane,")
    print("  LinAlgError from numpy. Detection is the portable part.")

    print()
    print("VERIFIED: the matrix surface matches the rule and agrees"
          " reference/R byte-level (numpy exact except the documented"
          " LAPACK inverse bar)" if failed == 0
          else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
