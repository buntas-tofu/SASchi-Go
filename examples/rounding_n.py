#!/usr/bin/env python3
"""rounding_n.py : gold-pair Python translation of the count-rounding ladder.

Source: a small-count disclosure-control rounding ladder. Translation map:
  %LET inputfile/outputfile/varlist  -> function parameters
  %MACRO round + %DO %WHILE %SCAN    -> for var in varlist
  DATA step ladder                   -> round_count via sas_semantics
  &var._r naming                     -> f"{var}_r" columns appended
SAS ROUND half-away-from-zero semantics come from sas_semantics.sas_round;
the host language's round() is never used. See verify_rounding.py.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sas_semantics import round_count  # noqa: E402


def round_counts(df: pd.DataFrame, varlist: list[str]) -> pd.DataFrame:
    out = df.copy()
    for var in varlist:
        out[f"{var}_r"] = out[var].map(round_count)
    return out


def main():
    if len(sys.argv) != 4:
        print("usage: rounding_n.py <input.csv> <output.csv> <var1,var2,...>")
        return 2
    inp, outp, varlist = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
    df = round_counts(pd.read_csv(inp), varlist)
    df.to_csv(outp, index=False)
    print(f"{len(df)} rows -> {outp} (rounded: {', '.join(varlist)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
