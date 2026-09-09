#!/usr/bin/env python3
"""verify_formats.py : the fixture gate for PROC FORMAT user formats
(quirk 18).

Pins inclusive-default endpoints with both exclusive syntaxes, LOW/HIGH open
ends, LOW EXCLUDING numeric missing (missing matches only an explicit '.'
entry or OTHER, else renders '.'), the fallthrough that renders an unmatched
value AS ITSELF (never blank), multi-value labels, byte-order character
ranges with the quirk-9 trailing-blank key, the overlap build error, and
formatted-value grouping (PROC FREQ pooling by label, the analysis-grain
change). Python/R agreement over the full case grid, row-count guarded.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import (HIGH, LOW, sas_format_def,  # noqa: E402
                           sas_freq_formatted, sas_put_fmt)

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

F_AB = ([((1.0, 5.0, True, True), "A"), ((5.0, 10.0, False, True), "B"),
         (("OTHER",), "other")],
        "R:1:5:1:1=A;R:5:10:0:1=B;O=other")
F_LOWHIGH = ([((LOW, 0.0, True, False), "neg"),
              ((0.0, HIGH, True, True), "nonneg")],
             "R:L:0:1:0=neg;R:0:H:1:1=nonneg")
F_PAIR = ([([1.0, 2.0], "pair")], "V:1,2=pair")
F_MISS = ([((".",), "unknown"), ((1.0, 9.0, True, True), "known")],
          "M=unknown;R:1:9:1:1=known")
F_CHR = ([(("A", "M", True, True), "front"), (("N", HIGH, True, True), "back")],
         "R:A:M:1:1=front;R:N:H:1:1=back")

CASES = [
    (F_AB, 1.0, "num"), (F_AB, 5.0, "num"), (F_AB, 5.5, "num"),
    (F_AB, 10.0, "num"), (F_AB, 11.0, "num"), (F_AB, None, "num"),
    (F_LOWHIGH, -5.0, "num"), (F_LOWHIGH, 0.0, "num"),
    (F_LOWHIGH, None, "num"),
    (F_PAIR, 2.0, "num"), (F_PAIR, 7.0, "num"),
    (F_MISS, None, "num"), (F_MISS, 3.0, "num"), (F_MISS, 99.0, "num"),
    (F_CHR, "B", "chr"), (F_CHR, "Q", "chr"), (F_CHR, "M ", "chr"),
]


def main() -> int:
    failed = 0

    print("1) endpoint, LOW/HIGH, missing, and fallthrough pins:")
    pins = [((F_AB, 5.0), "A"), ((F_AB, 5.5), "B"), ((F_AB, None), "other"),
            ((F_LOWHIGH, None), "."), ((F_MISS, None), "unknown"),
            ((F_MISS, 99.0), "99"), ((F_PAIR, 7.0), "7"),
            ((F_CHR, "M "), "front")]
    for (fx, v), want in pins:
        got = sas_put_fmt(v, sas_format_def(fx[0]))
        if got != want:
            failed += 1
            print(f"  FAIL put({v!r}) = {got!r} want {want!r}")
    print(f"  {len(pins)} pins (LOW excludes missing, fallthrough renders"
          " the value, blank-key char match)")

    print("2) the overlap temperament:")
    try:
        sas_format_def([((1.0, 5.0, True, True), "A"),
                        ((4.0, 8.0, True, True), "B")])
        failed += 1
        print("  FAIL overlap must error")
    except ValueError:
        pass
    print("  overlapping ranges refuse to build, as PROC FORMAT does")

    print("3) formatted-value grouping (the analysis-grain pin):")
    freq = sas_freq_formatted([1.0, 2.0, 5.5, 7.0, None],
                              sas_format_def(F_AB[0]))
    if freq != {"A": 2, "B": 2, "other": 1}:
        failed += 1
        print(f"  FAIL {freq}")
    print("  five raw values pool into three formatted cells")

    print("4) Python/R agreement, row-count guarded:")
    rows = []
    for (fx, dsl), v, typ in CASES:
        raw = "NA" if v is None else (f"{v:.17g}" if typ == "num" else v)
        rows.append(['"' + dsl + '"', '"' + raw + '"', '"' + typ + '"'])
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as f:
        f.write("fmt,value,type\n")
        for row in rows:
            f.write(",".join(row) + "\n")
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "formats.R"), path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    lines = [ln for ln in out.stdout.splitlines() if ln]
    if not lines[0].startswith("n=") or int(lines[0][2:]) != len(rows):
        raise RuntimeError("row-count guard failed")
    mism = 0
    for i, ((entries, _dsl), v, _typ) in enumerate(CASES):
        py = sas_put_fmt(v, sas_format_def(entries))
        if py != lines[1 + i]:
            mism += 1
            print(f"  MISMATCH case {i} ({v!r}): py {py!r} vs R "
                  f"{lines[1 + i]!r}")
    failed += mism
    print(f"  {len(CASES)} cases, {mism} mismatches")

    print()
    print("VERIFIED: PROC FORMAT user formats match the rule and agree "
          "Python/R" if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
