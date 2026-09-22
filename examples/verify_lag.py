#!/usr/bin/env python3
"""verify_lag.py : the fixture gate for LAG/DIF queue semantics (DS-007).

The rule is the invocation queue. Each LAG<k> or DIF<k> OCCURRENCE carries its
own queue of length k; executing the call returns the front of the queue (the
value from k executions ago) and then stores the current argument. The first k
executions return missing. The queue advances where the CALL RUNS, not where
the row exists, so a conditional call site is not a column shift, and a missing
argument is still an execution.

Layer 1 is hand pins derived from the documented law, not from an engine. Layer
2 is an independent second implementation (index arithmetic over an explicit
slot array) that shares no code with the reference. Layer 3 is the landmine
demonstration: the shift model that a naive translation produces, shown
returning values SAS does not. Layer 4 is byte-equality at 17 digits against
the base-R twin, row-count guarded, which is the strongest cheap assertion
available because two values that render identically at 17 digits are the same
double.

The seven fixture designs come from the campaign review's LAG section. No live
SAS was used: the pins rest on the documented queue contract plus cross-engine
agreement, and the verifier says so on its face.
"""

import csv
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import (sas_dif_conditional, sas_lag_conditional,  # noqa: E402
                           sas_lag_occurrences, sas_lag_queue)

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

# cmd, label, values, invoked, depth, hand pin (None where the pin is the
# cross-language lane only). Rows where invoked is None mean every row runs.
SCENARIOS = [
    ("queue", "unconditional depth 1 over 10,20,30",
     [10.0, 20.0, 30.0], None, 1, [None, 10.0, 20.0]),
    ("queue", "LAG2 begins with two missing",
     [10.0, 20.0, 30.0, 40.0], None, 2, [None, None, 10.0, 20.0]),
    ("conditional", "invoked only on rows two and four",
     [10.0, 20.0, 30.0, 40.0], [False, True, False, True], 1,
     [None, None, None, 20.0]),
    ("conditional", "a skipped call does not advance the queue",
     [10.0, 20.0, 30.0], [True, False, True], 1, [None, None, 10.0]),
    ("conditional", "a missing argument still advances the queue",
     [10.0, None, 30.0], [True, True, True], 1, [None, 10.0, None]),
    ("conditional", "the next execution sees the stored missing",
     [10.0, None, 30.0, 40.0], [True, True, True, True], 1,
     [None, 10.0, None, 30.0]),
    ("dif", "DIF1 over three invocations",
     [10.0, 25.0, 31.0], [True, True, True], 1, [None, 15.0, 6.0]),
    ("dif", "DIF2 needs two executions of history",
     [10.0, 25.0, 31.0, 40.0], [True, True, True, True], 2,
     [None, None, 21.0, 15.0]),
    ("dif", "a conditional DIF differences against the last EXECUTION",
     [10.0, 25.0, 31.0], [True, False, True], 1, [None, None, 21.0]),
    ("queue", "decimal arguments render identically at 17 digits",
     [1.1, 2.3, 4.7], None, 1, None),
    ("dif", "decimal differences render identically at 17 digits",
     [1.1, 2.3, 4.7], None, 1, None),
]

OCCURRENCE_VALUES = [10.0, 20.0, 30.0]
OCCURRENCE_INV = [(True, True, True), (True, False, True)]


def tok(value):
    """The one missing token, and the 17-digit rendering of a stored double."""
    return "." if value is None else format(value, ".17g")


def reference(cmd, values, invoked, depth):
    runs = [True] * len(values) if invoked is None else invoked
    if cmd == "queue":
        return sas_lag_queue(values, depth)
    if cmd == "conditional":
        return sas_lag_conditional(values, runs, depth)
    if cmd == "dif":
        return sas_dif_conditional(values, runs, depth)
    raise AssertionError(cmd)


def independent(values, invoked, depth):
    """A second implementation with no shared code: an explicit slot array
    addressed by a counter, never a list used as a queue."""
    slots = [None] * depth
    filled = 0
    cursor = 0
    out = []
    for index, value in enumerate(values):
        if invoked is not None and not invoked[index]:
            out.append(None)
            continue
        if filled < depth:
            out.append(None)
        else:
            out.append(slots[cursor])
        slots[cursor] = value
        cursor = (cursor + 1) % depth
        filled = min(filled + 1, depth)
    return out


def shift_model(values, invoked):
    """What a naive translation emits: shift the full column, then apply the
    condition. This is the known-wrong model and the gate must reject it."""
    shifted = [None] + values[:-1]
    return [shifted[i] if invoked[i] else None for i in range(len(values))]


def r_lane(cmd, header, rows, n_expected):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="") as handle:
        handle.write(",".join(header) + "\n")
        for row in rows:
            handle.write(",".join(row) + "\n")
        path = handle.name
    run = subprocess.run([str(RSCRIPT), str(HERE / "lag.R"), cmd, path],
                         capture_output=True, text=True, timeout=30)
    if run.returncode != 0:
        raise RuntimeError(run.stderr)
    lines = [line for line in run.stdout.splitlines() if line != ""]
    if not lines[0].startswith("n=") or int(lines[0][2:]) != n_expected:
        raise RuntimeError("row-count guard failed: harness defect")
    return lines[1:]


def rows_for(cmd, values, invoked, depth):
    """Every row is one execution, in order, so the CSV is the DATA step. The
    conditional commands always carry an invoked column, all ones when the call
    site is unconditional: the R twin stays strict and the harness stays the
    only place the contract is spelled."""
    out = []
    conditional = cmd in ("conditional", "dif")
    for index, value in enumerate(values):
        cell = "NA" if value is None else repr(value)
        if conditional:
            runs = True if invoked is None else invoked[index]
            out.append([cell, "1" if runs else "0", str(depth)])
        else:
            out.append([cell, str(depth)])
    return out


def main() -> int:
    failed = 0

    print("1) hand pins from the documented queue contract:")
    checked = 0
    for cmd, label, values, invoked, depth, pin in SCENARIOS:
        if pin is None:
            continue
        got = reference(cmd, values, invoked, depth)
        checked += 1
        if got != pin:
            failed += 1
            print(f"  FAIL {label}: {got!r} want {pin!r}")
    print(f"  {checked} pins checked")

    print("2) an independent second implementation agrees:")
    mismatched = 0
    for cmd, label, values, invoked, depth, pin in SCENARIOS:
        got = reference(cmd, values, invoked, depth)
        lag_ind = independent(values, invoked, depth)
        if cmd == "dif":
            runs = [True] * len(values) if invoked is None else invoked
            want = [None if (not runs[i]) or lag_ind[i] is None
                    or values[i] is None else values[i] - lag_ind[i]
                    for i in range(len(values))]
        else:
            want = lag_ind
        if got != want:
            mismatched += 1
            print(f"  MISMATCH {label}: reference {got!r} vs independent {want!r}")
    failed += mismatched
    print(f"  {len(SCENARIOS)} scenarios, {mismatched} mismatches")

    print("3) the landmine: the shift model is not the queue:")
    conditional = [False, True, False, True]
    values = [10.0, 20.0, 30.0, 40.0]
    queue_result = reference("conditional", values, conditional, 1)
    shift_result = shift_model(values, conditional)
    print(f"  queue (SAS) : {[tok(v) for v in queue_result]}")
    print(f"  shift (naive): {[tok(v) for v in shift_result]}")
    if queue_result == shift_result:
        failed += 1
        print("  FAIL the known-wrong shift model matched the queue law")
    if [tok(v) for v in queue_result] != [".", ".", ".", "20"]:
        failed += 1
        print("  FAIL the queue law no longer returns missing then 20")

    print("4) pandas agrees where a shift is correct, and only there:")
    import pandas as pd
    unconditional = [10.0, 20.0, 30.0, 40.0]
    ours = reference("queue", unconditional, None, 1)
    pandas_shift = pd.Series(unconditional).shift(1).tolist()
    if [tok(v) for v in ours] != [tok(None if pd.isna(v) else v)
                                  for v in pandas_shift]:
        failed += 1
        print("  FAIL unconditional LAG must equal a column shift")
    print("  unconditional case: a column shift is correct by construction")
    print("  conditional case: rejected in step 3")

    print("5) two occurrences keep independent queues:")
    a, b = sas_lag_occurrences(
        [(OCCURRENCE_VALUES, OCCURRENCE_INV[0]),
         (OCCURRENCE_VALUES, OCCURRENCE_INV[1])], 1)
    pin_a, pin_b = [None, 10.0, 20.0], [None, None, 10.0]
    if a != pin_a or b != pin_b or a == b:
        failed += 1
        print(f"  FAIL occurrences {a!r} {b!r}")

    print("6) byte-equality at 17 digits against the base-R twin:")
    lines_checked = 0
    for cmd, label, values, invoked, depth, pin in SCENARIOS:
        header = (["value", "invoked", "n"]
                  if cmd in ("conditional", "dif") else ["value", "n"])
        rows = rows_for(cmd, values, invoked, depth)
        r = r_lane(cmd, header, rows, len(values))
        py = [tok(v) for v in reference(cmd, values, invoked, depth)]
        if r != py:
            failed += 1
            print(f"  MISMATCH {label}\n    py {py}\n    R  {r}")
        lines_checked += len(r)
    inv_a = ["1" if f else "0" for f in OCCURRENCE_INV[0]]
    inv_b = ["1" if f else "0" for f in OCCURRENCE_INV[1]]
    rows = [[repr(v), inv_a[i], inv_b[i], "1"]
            for i, v in enumerate(OCCURRENCE_VALUES)]
    r = r_lane("occurrences", ["value", "inv_a", "inv_b", "n"], rows,
               len(OCCURRENCE_VALUES))
    py = [" ".join([tok(a[i]), tok(b[i])])
          for i in range(len(OCCURRENCE_VALUES))]
    if r != py:
        failed += 1
        print(f"  MISMATCH occurrences\n    py {py}\n    R  {r}")
    lines_checked += len(r)
    print(f"  {lines_checked} values byte-equal across Python and base R")

    print()
    print("VERIFIED: LAG/DIF queue semantics match the rule, agree with an "
          "independent implementation, and are byte-equal Python/R"
          if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())