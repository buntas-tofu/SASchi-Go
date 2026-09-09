#!/usr/bin/env python3
"""verify_csvimport.py : the fixture gate for CSV import type inference
(rulebook DS-021, the PROC IMPORT surface).

PROC IMPORT dbms=csv guesses column types from a window: the first
guessingrows values (default 20). A column that is clean inside the window
but contains a non-numeric value later is read NUMERIC by SAS, and the late
value becomes missing with a note. pandas and R infer from the WHOLE file,
so the same column reads character in both open languages. A translation
that trusts either side's default silently changes which values are
missing. Second landmine: leading-zero identifiers (zip codes, ids) are
stripped by ALL three defaults; identifiers must be read as character
explicitly. The gate pins both, and proves the explicit pinned read is
byte-equal Python/R.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_proc_import_guess  # noqa: E402

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

# The fixture: 24 rows. 'id' and 'zip' are leading-zero identifiers (all
# three engines strip them under default inference). 'score' is numeric for
# the first 20 rows, then carries 'abc' from row 21: the PROC IMPORT
# window (20) sees numeric, pandas and R see the whole file and read
# character. 'note' is plain character.
FIXTURE_HEADER = ["id", "score", "zip", "note"]
FIXTURE_ROWS = []
for i in range(24):
    score = "10.5" if i < 20 else "abc"
    FIXTURE_ROWS.append((f"{12 + i:04d}", score, f"02{i + 100:03d}",
                         f"row{i + 1}"))


def write_fixture():
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                    newline="")
    f.write(",".join(FIXTURE_HEADER) + "\n")
    for row in FIXTURE_ROWS:
        f.write(",".join(row) + "\n")
    f.close()
    return f.name


def r_lane(cmd, csv_path, expect_rows=None):
    if expect_rows is None:
        expect_rows = len(FIXTURE_ROWS)
    out = subprocess.run([str(RSCRIPT), str(HERE / "csvimport.R"), cmd,
                          csv_path], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = out.stdout.splitlines()
    if not lines or not lines[0].startswith("n="):
        raise RuntimeError("csvimport.R printed no row-count guard")
    if int(lines[0][2:]) != expect_rows:
        raise RuntimeError("R loaded a different row count: harness defect")
    return [ln for ln in lines[1:] if ln != ""]


def main() -> int:
    failed = 0
    path = write_fixture()

    print("1) default inference agrees Python/R (the naive lane):")
    r_types = r_lane("types", path)[0]
    import pandas as pd
    df = pd.read_csv(path)
    py_types = []
    for col in df.columns:
        dt = str(df[col].dtype)
        if dt.startswith("int"):
            py_types.append("INT")
        elif dt.startswith("float"):
            py_types.append("NUM")
        else:
            py_types.append("CHAR")
    py_types = ",".join(py_types)
    if r_types != py_types:
        failed += 1
        print(f"  MISMATCH: R [{r_types}] vs pandas [{py_types}]")
    print(f"  R and pandas both infer: {py_types}")

    print("2) the PROC IMPORT window, pinned:")
    sas_types = sas_proc_import_guess(FIXTURE_ROWS, guessingrows=20)
    print(f"  SAS window (20 rows) infers: {','.join(sas_types)}")
    if sas_types != ["NUM", "NUM", "NUM", "CHAR"]:
        failed += 1
        print(f"  FAIL: expected NUM,NUM,NUM,CHAR got {sas_types}")
    if py_types != "INT,CHAR,INT,CHAR":
        failed += 1
        print(f"  FAIL: expected INT,CHAR,INT,CHAR got {py_types}")
    print("  Landmine pinned: SAS says score is NUM (clean window);")
    print("  pandas/R say CHAR (full file). Both are right, and the")
    print("  missing-value sets differ. Never trust either default.")

    print("2b) the NA-token divergence, demonstrated:")
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write("v\n1.5\nN/A\n3\n")
        na_path = f.name
    pd_na = pd.read_csv(na_path)
    r_na = r_lane("types", na_path, expect_rows=3)[0]
    if str(pd_na["v"].dtype).startswith("float"):
        print("  pandas default na_values eats 'N/A' -> float64 (NUM)")
    else:
        failed += 1
        print("  FAIL: pandas did not treat 'N/A' as missing")
    if r_na != "CHAR":
        failed += 1
        print(f"  FAIL: R read the N/A column as {r_na}, expected CHAR")
    print("  R default na.strings is 'NA' only: 'N/A' stays a string"
          " (CHAR). Same CSV, different missing set.")

    print("3) leading-zero identifiers, demonstrated:")
    df = pd.read_csv(path, dtype=str)
    if df.loc[0, "id"] != "0012" or df.loc[0, "zip"] != "02100":
        failed += 1
        print(f"  FAIL: explicit str read lost leading zeros:"
              f" id={df.loc[0, 'id']!r} zip={df.loc[0, 'zip']!r}")
    print("  default inference strips 0012 -> 12 and 02100 -> 2100;")
    print("  explicit character reads preserve them")

    print("4) pinned reads byte-equal Python/R, every cell quoted:")
    r_pinned = r_lane("pinned", path)
    py_pinned = [",".join(f'"{v}"' for v in row) for row in FIXTURE_ROWS]
    mism = 0
    for i, (r, p) in enumerate(zip(r_pinned, py_pinned)):
        if r != p:
            mism += 1
            print(f"  MISMATCH row {i}: R {r!r} vs py {p!r}")
    failed += mism
    print(f"  {len(py_pinned)} rows byte-equal ({mism} mismatches)")

    print()
    print("VERIFIED: CSV import inference and the explicit pinned read"
          " match the rule and agree Python/R" if failed == 0
          else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
