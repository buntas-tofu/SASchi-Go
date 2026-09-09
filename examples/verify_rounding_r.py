#!/usr/bin/env python3
"""verify_rounding_r.py : the R half of the gold-pair gate.

Exercises the ACTUAL rounding_n.R file end to end: writes the fixture sweep to
CSV, runs the R translation through Rscript exactly as a user would, reads the
output back, and compares every rounded value against the sas_semantics
reference. Cross-language agreement is the oracle: when the Python and R
translations both match the reference on the full sweep, the pair ships.

Rscript resolution: $ROSETTA_RSCRIPT, then Rscript on PATH.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sas_semantics import round_count  # noqa: E402
from verify_rounding import HAND_PINNED  # noqa: E402

R_SCRIPT = Path(__file__).parent / "rounding_n.R"


def find_rscript() -> str | None:
    return os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript")


def main() -> int:
    rscript = find_rscript()
    if not rscript:
        print("SKIP: no Rscript available (set ROSETTA_RSCRIPT or add Rscript to "
              "PATH). The R translation stays marked unverified.")
        return 75

    sweep = [v for v, _ in HAND_PINNED] + list(range(0, 2_000_000, 7919))
    with tempfile.TemporaryDirectory() as td:
        fix = Path(td) / "fixtures.csv"
        out = Path(td) / "out.csv"
        pd.DataFrame({"samp_size1": sweep}).to_csv(fix, index=False)
        r = subprocess.run([rscript, str(R_SCRIPT), str(fix), str(out),
                            "samp_size1"], capture_output=True, text=True,
                           timeout=300)
        if r.returncode != 0:
            print(f"FAILED: Rscript exited {r.returncode}\n{r.stderr[:800]}")
            return 1
        got = pd.read_csv(out)

    mismatches = [(v, round_count(v), g) for v, g in
                  zip(sweep, got["samp_size1_r"]) if g != round_count(v)]
    for v, want, g in mismatches[:10]:
        print(f"  MISMATCH value {v}: R says {g}, reference says {want}")
    print(f"{len(sweep)} fixtures through Rscript ({rscript})")
    print("R VERIFIED: translation matches SAS semantics on all fixtures"
          if not mismatches else f"FAILED: {len(mismatches)} mismatches")
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
