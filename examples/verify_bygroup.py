#!/usr/bin/env python3
"""verify_bygroup.py : the fixture gate for SAS BY-group processing, the first
construct that is a stateful sequential model rather than a scalar function.

Proves the FIRST./LAST. prefix flags and the RETAIN running-total (reset at
first, output at last, missing addend as zero) against hand-pins, demonstrates
the retain-across-groups landmine (a naive global cumsum that never resets), and
proves Python/R agreement on both.
"""

import csv
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import (is_sas_missing, sas_by_groups,  # noqa: E402
                           sas_retain_total)

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

# FIRST./LAST. hand-pins for BY a b: per row (first.a, first.b, last.a, last.b).
FLAG_ROWS = [{"a": "1", "b": "1"}, {"a": "1", "b": "2"}, {"a": "1", "b": "2"},
             {"a": "2", "b": "1"}, {"a": "2", "b": "1"}]
FLAG_PINS = [(1, 1, 0, 1), (0, 1, 0, 0), (0, 0, 1, 1), (1, 1, 0, 0), (0, 0, 1, 1)]

# RETAIN hand-pins for BY id, sum amt: per-group total, reset at first.id, with a
# missing addend (row 2) that the sum statement takes as zero.
RETAIN_ROWS = [{"id": "1", "amt": 10.0}, {"id": "1", "amt": None},
               {"id": "2", "amt": 7.0}, {"id": "2", "amt": 3.0},
               {"id": "3", "amt": 100.0}]
RETAIN_PINS = [(("1",), 10.0), (("2",), 10.0), (("3",), 100.0)]


def py_flags(rows, by_vars):
    out = []
    for i, first, last in sas_by_groups(rows, by_vars):
        out.append(tuple([int(first[v]) for v in by_vars]
                         + [int(last[v]) for v in by_vars]))
    return out


def py_retain(rows, by_vars, sum_var):
    return [(tuple(str(r[v]) for v in by_vars), float(r["total"]))
            for r in sas_retain_total(rows, by_vars, sum_var)]


def r_flags(rows, by_vars):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
        w = csv.DictWriter(f, fieldnames=by_vars)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in by_vars})
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "bygroup.R"), "flags", path,
                          ",".join(by_vars)], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    return [tuple(int(x) for x in ln.split())
            for ln in out.stdout.splitlines() if ln.strip()]


def r_retain(rows, by_vars, sum_var):
    cols = by_vars + [sum_var]
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r[k]) for k in cols})
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "bygroup.R"), "retain", path,
                          ",".join(by_vars), sum_var], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    res = []
    for ln in out.stdout.splitlines():
        if not ln.strip():
            continue
        parts = ln.split()
        res.append((tuple(parts[:len(by_vars)]), float(parts[-1])))
    return res


def main() -> int:
    failed = 0

    print("1) FIRST./LAST. flag hand-pins (BY a b):")
    pf = py_flags(FLAG_ROWS, ["a", "b"])
    for got, want in zip(pf, FLAG_PINS):
        if got != want:
            failed += 1
            print(f"  FAIL {got} want {want}")
    print(f"  {len(FLAG_PINS)} rows checked")

    print("2) RETAIN running-total hand-pins (reset at first.id, missing as 0):")
    pr = py_retain(RETAIN_ROWS, ["id"], "amt")
    for got, want in zip(pr, RETAIN_PINS):
        if got != want:
            failed += 1
            print(f"  FAIL {got} want {want}")
    print(f"  {len(RETAIN_PINS)} groups checked")

    print("3) the landmine (naive global cumsum never resets at first.id):")
    glob, t = [], 0.0
    for r in RETAIN_ROWS:
        t += 0.0 if is_sas_missing(r["amt"]) else r["amt"]
        glob.append(t)
    last_idx = [i for i, _f, last in sas_by_groups(RETAIN_ROWS, ["id"]) if last["id"]]
    naive = [glob[i] for i in last_idx]
    sas = [tot for _k, tot in RETAIN_PINS]
    diverge = sum(1 for n, s in zip(naive, sas) if n != s)
    print(f"  naive at group-last {naive} vs SAS {sas}: {diverge} of {len(sas)} diverge")
    if diverge < 1:
        failed += 1
        print("  FAIL: expected the global cumsum to diverge, found none")

    print("4) Python/R agreement:")
    fmis = sum(1 for a, b in zip(pf, r_flags(FLAG_ROWS, ["a", "b"])) if a != b)
    failed += fmis
    print(f"  FLAGS: {len(pf)} rows, {fmis} Python/R mismatches")
    rmis = sum(1 for a, b in zip(pr, r_retain(RETAIN_ROWS, ["id"], "amt")) if a != b)
    failed += rmis
    print(f"  RETAIN: {len(pr)} groups, {rmis} Python/R mismatches")

    print()
    print("VERIFIED: BY-group first/last flags and retain match the rule and agree "
          "Python/R" if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
