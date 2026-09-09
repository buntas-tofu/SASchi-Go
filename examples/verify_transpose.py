#!/usr/bin/env python3
"""verify_transpose.py : the fixture gate for PROC TRANSPOSE (quirk 16).

Pins the single-pass shape (one row per VAR per BY group; columns are the
union of mangled ID values in first-appearance order, ragged groups fill
missing), the name mangling (leading digits gain an underscore), the
numeric-only VAR default, PREFIX, and the duplicate-ID temperament: SAS
ERRORS by default and only LET makes it last-wins, while pandas pivot_table
silently AVERAGES the duplicates, demonstrated live. Python/R agreement over
the full fixture set, row-count guarded.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_transpose  # noqa: E402

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

RAGGED = [{"g": "A", "yr": 2020.0, "s": 1.0}, {"g": "A", "yr": 2021.0, "s": 2.0},
          {"g": "B", "yr": 2021.0, "s": 3.0}, {"g": "B", "yr": 2022.0, "s": 4.0}]
DUP = [{"g": "A", "yr": 2020.0, "s": 1.0}, {"g": "A", "yr": 2020.0, "s": 9.0}]
NOID = [{"x": 1.0, "y": 10.0, "c": "txt"}, {"x": 2.0, "y": 20.0, "c": "txt"}]
PFX = [{"g": "A", "yr": 2020.0, "s": 1.0}]


def fmt(v):
    if v is None:
        return "NA"
    if isinstance(v, float):
        return f"{v:.17g}"
    return str(v)


def py_render(rows, **kw):
    out, cols = sas_transpose(rows, **kw)
    lines = ["|".join(cols)]
    for rec in out:
        lines.append("|".join(fmt(rec[c]) for c in cols))
    return lines


def r_render(rows, by, id_var, var, prefix, let):
    cols = list(rows[0].keys())
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write(",".join(cols) + "\n")
        for rec in rows:
            f.write(",".join('"' + fmt(rec[c]) + '"' for c in cols) + "\n")
        path = f.name
    out = subprocess.run(
        [str(RSCRIPT), str(HERE / "transpose.R"), path,
         ",".join(by) if by else "-", id_var or "-",
         ",".join(var) if var else "-", prefix or "-", "1" if let else "0"],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = [ln for ln in out.stdout.splitlines() if ln]
    if not lines[0].startswith("n=") or int(lines[0][2:]) != len(rows):
        raise RuntimeError("row-count guard failed")
    return lines[1:]


def main() -> int:
    failed = 0

    print("1) ragged BY groups, ID union, leading-digit mangling:")
    out, cols = sas_transpose(RAGGED, by=["g"], id_var="yr")
    if cols != ["g", "_NAME_", "_2020", "_2021", "_2022"]:
        failed += 1
        print(f"  FAIL cols {cols}")
    if out[0]["_2022"] is not None or out[1]["_2020"] is not None:
        failed += 1
        print("  FAIL ragged cells must be missing")
    print(f"  cols {cols}, missing cells in place")

    print("2) the duplicate-ID temperament (error default, LET last-wins,")
    print("   pandas silently averages):")
    try:
        sas_transpose(DUP, by=["g"], id_var="yr")
        failed += 1
        print("  FAIL duplicate ID must error without LET")
    except ValueError:
        pass
    out, _cols = sas_transpose(DUP, by=["g"], id_var="yr", let=True)
    if out[0]["_2020"] != 9.0:
        failed += 1
        print(f"  FAIL LET last-wins: {out}")
    import pandas as pd
    piv = pd.DataFrame(DUP).pivot_table(index="g", columns="yr", values="s")
    silently = float(piv.iloc[0, 0])
    if silently != 5.0:
        failed += 1
        print(f"  FAIL expected pandas to average to 5.0, got {silently}")
    print(f"  SAS errors, LET keeps 9.0, pandas invents {silently}: pinned")

    print("3) numeric-only VAR default and PREFIX:")
    out, cols = sas_transpose(NOID)
    if cols != ["_NAME_", "COL1", "COL2"] or [r["_NAME_"] for r in out] != ["x", "y"]:
        failed += 1
        print(f"  FAIL default VAR: {cols} {[r['_NAME_'] for r in out]}")
    _out, cols = sas_transpose(PFX, by=["g"], id_var="yr", prefix="Y")
    if cols[-1] != "Y2020":
        failed += 1
        print(f"  FAIL prefix: {cols}")
    print("  char column excluded by default, PREFIX Y2020 clean (no mangle)")

    print("4) Python/R agreement, row-count guarded:")
    cases = [("ragged", RAGGED, dict(by=["g"], id_var="yr")),
             ("let", DUP, dict(by=["g"], id_var="yr", let=True)),
             ("noid", NOID, dict()),
             ("prefix", PFX, dict(by=["g"], id_var="yr", prefix="Y"))]
    mism = 0
    for name, rows, kw in cases:
        py = py_render(rows, **kw)
        rr = r_render(rows, kw.get("by", []), kw.get("id_var"),
                      kw.get("var"), kw.get("prefix"), kw.get("let", False))
        if py != rr:
            mism += 1
            print(f"  MISMATCH {name}:")
            for a, b in zip(py, rr):
                print(f"    py {a}   R {b}{'' if a == b else '   <-- differs'}")
    rr = r_render(DUP, ["g"], "yr", None, None, False)
    if rr != ["DUPLICATE-ID-ERROR"]:
        mism += 1
        print(f"  MISMATCH dup-error lane: {rr}")
    failed += mism
    print(f"  {len(cases)} fixtures plus the error lane, {mism} mismatches")

    print()
    print("VERIFIED: PROC TRANSPOSE matches the rule and agrees Python/R"
          if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
