#!/usr/bin/env python3
"""verify_rounding.py : the fixture gate for the rounding-n gold pair.

Three duties:
1. Hand-pinned assertions: critical values with expected outputs computed by
   human arithmetic from the SAS rule text, so the reference implementation is
   itself checked against something that is not code.
2. Full-ladder fixtures through the Python translation (every branch, every
   half-unit boundary).
3. The landmine demonstration: the same ladder built on the host language's
   round() half-to-even, shown DIVERGING on the boundary fixtures. This is why
   translation without a verification gate ships silent numeric drift.
"""

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sas_semantics import round_count, sas_round  # noqa: E402
from rounding_n import round_counts  # noqa: E402

# (value, expected) pinned BY HAND from the SAS rule text, half-away semantics
HAND_PINNED = [
    (0, 10), (5, 10), (14, 10),            # the "<15" floor reports 10
    (15, 20),                              # 15/10 = 1.5, half away -> 20
    (25, 30),                              # 2.5 -> 3 -> 30 (banker's says 20)
    (99, 100),
    (105, 100),                            # under-1000 rung: unit 50, 2.1 -> 2 -> 100
                                           # (a first hand-pin said 110 via the wrong
                                           # rung; the gate caught the human, kept)
    (125, 150),                            # 125/50 = 2.5 -> 3 -> 150 (banker's 100)
    (975, 1000),                           # 19.5 -> 20 -> 1000 (banker's same)
    (1050, 1100),                          # 10.5 -> 11 -> 1100 (banker's 1000)
    (9950, 10000),
    (18250, 18500),                        # 36.5 -> 37 -> 18500 (banker's 18000)
    (101500, 102000),                      # 101.5 -> 102 -> 102000 (banker's same)
    (999500, 1000000),                     # 999.5 -> 1000 (banker's 1000000 too)
    (1234567, 1235000),                    # >= 1e6: four significant digits
    (98765432, 98770000),
]


def naive_ladder(x: float) -> float:
    """The translation a hurried migrator writes: same ladder, host round()."""
    if x < 15:
        return 10
    if x < 100:
        return round(x / 10) * 10
    if x < 1000:
        return round(x / 50) * 50
    if x < 10000:
        return round(x / 100) * 100
    if x < 100000:
        return round(x / 500) * 500
    if x < 1000000:
        return round(x / 1000) * 1000
    unit = 10 ** (math.floor(math.log10(x)) - 3)
    return round(x / unit) * unit


def main() -> int:
    failed = 0

    print("1) hand-pinned assertions (reference vs human arithmetic):")
    for value, want in HAND_PINNED:
        got = round_count(value)
        ok = got == want
        failed += not ok
        if not ok:
            print(f"  FAIL {value} -> {got} (want {want})")
    print(f"  {len(HAND_PINNED) - failed}/{len(HAND_PINNED)} pinned values pass")

    print("2) DataFrame translation over the full fixture sweep:")
    sweep = [v for v, _ in HAND_PINNED] + list(range(0, 2_000_000, 7919))
    df = pd.DataFrame({"samp_size1": sweep})
    out = round_counts(df, ["samp_size1"])
    mismatch = sum(1 for v, r in zip(sweep, out["samp_size1_r"])
                   if r != round_count(v))
    failed += mismatch
    print(f"  {len(sweep)} fixtures, {mismatch} mismatches between translation "
          "and reference")

    print("3) the landmine: naive host-language round() vs SAS semantics:")
    diverged = [(v, round_count(v), naive_ladder(v))
                for v, _ in HAND_PINNED if naive_ladder(v) != round_count(v)]
    for v, sas, naive in diverged:
        print(f"  value {v:>7}: SAS says {sas:>8.0f} | naive translation says "
              f"{naive:>8.0f}")
    print(f"  {len(diverged)} of {len(HAND_PINNED)} pinned fixtures diverge "
          "under the naive translation")
    if not diverged:
        failed += 1
        print("  FAIL: expected divergence, found none (landmine demo broken)")

    print()
    print("VERIFIED: translation matches SAS semantics on all fixtures"
          if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
