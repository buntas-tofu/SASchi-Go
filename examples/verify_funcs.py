#!/usr/bin/env python3
"""verify_funcs.py : the fixture gate for the scalar SAS functions -- MAX/MIN
(ignore missing), the LENGTH family (trailing-blank exclusion, floor of 1),
SUBSTR (1-based), %EVAL (integer truncating division), and character-to-numeric
coercion (blank or invalid becomes missing). Hand-pins from the rule, the
naive-divergence demo, and Python/R agreement.
"""

import csv
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import (sas_charnum, sas_eval, sas_length,  # noqa: E402
                           sas_lengthc, sas_lengthn, sas_max, sas_min,
                           sas_substr, sas_sysevalf)

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

# LENGTH hand-pins: (string, LENGTH, LENGTHN, LENGTHC)
LEN_PINS = [("abc", 3, 3, 3), ("abc  ", 3, 3, 5), ("   ", 1, 0, 3),
            ("", 1, 0, 0), ("a b ", 3, 3, 4), ("x     ", 1, 1, 6)]
# MAX/MIN hand-pins: (values, MAX, MIN)
AGG_PINS = [((3, 7, 2), 7, 2), ((3, None, 7), 7, 3), ((None, None), None, None),
            ((5,), 5, 5), ((-1, None, -9), -1, -9)]
# SUBSTR hand-pins: (string, pos, length, expected)  -- SAS is 1-based
SUB_PINS = [("abcde", 1, 3, "abc"), ("abcde", 2, 3, "bcd"), ("abcde", 3, None, "cde"),
            ("abcde", 4, 10, "de"), ("hello world", 7, 5, "world")]
# %EVAL hand-pins: (expr, integer result) -- division truncates toward zero
EVAL_PINS = [("7/2", 3), ("10/3", 3), ("3+4", 7), ("2*3", 6), ("-7/2", -3),
             ("17/5", 3), ("(5+1)/2", 3), ("100/7", 14)]
EVALDIV_PAIRS = [(7, 2), (10, 3), (-7, 2), (17, 5), (100, 7), (-10, 3), (10, -3), (99, 100)]
# CHAR->NUM hand-pins: (string, numeric or None) -- blank/invalid is missing
CHARNUM_PINS = [("5", 5.0), ("  42  ", 42.0), ("-3", -3.0), ("3.5", 3.5),
                (".5", 0.5), ("3.", 3.0), ("1e3", 1000.0), ("1E+3", 1000.0),
                ("+7", 7.0), ("", None), ("   ", None), ("abc", None),
                ("1,000", None), ("$5", None), (".", None), ("0x10", None),
                ("5.5.5", None), ("1e", None)]


def r_length(strings):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
        w = csv.writer(f); w.writerow(["base", "n_trail"])
        for s in strings:
            body = s.rstrip(" ")
            w.writerow([body, len(s) - len(body)])
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "funcs.R"), "length", path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    return [tuple(int(x) for x in ln.split()) for ln in out.stdout.splitlines() if ln.strip()]


def r_agg(tuples):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
        w = csv.writer(f); w.writerow(["nums"])
        for t in tuples:
            w.writerow([";".join("NA" if v is None else str(v) for v in t)])
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "funcs.R"), "maxmin", path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    res = []
    for ln in out.stdout.splitlines():
        if not ln.strip():
            continue
        a, b = ln.split()
        res.append((None if a == "NA" else float(a), None if b == "NA" else float(b)))
    return res


def r_substr(cases):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
        w = csv.writer(f); w.writerow(["s", "pos", "len"])
        for s, pos, ln in cases:
            w.writerow([s, pos, "" if ln is None else ln])
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "funcs.R"), "substr", path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    return out.stdout.splitlines()


def r_evaldiv(pairs):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
        w = csv.writer(f); w.writerow(["a", "b"])
        for a, b in pairs:
            w.writerow([a, b])
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "funcs.R"), "evaldiv", path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    return [int(x) for x in out.stdout.split()]


def r_charnum(strings):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL); w.writerow(["s"])
        for s in strings:
            w.writerow([s])
        path = f.name
    out = subprocess.run([str(RSCRIPT), str(HERE / "funcs.R"), "charnum", path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    res = []
    for ln in out.stdout.splitlines():
        s = ln.strip()
        res.append(None if s == "NA" else float(s))
    return res


def charnum_eq(a, b):
    return (a is None and b is None) or (
        a is not None and b is not None and math.isclose(a, b))


def _raises_float(s):
    try:
        float(s)
        return False
    except ValueError:
        return True


def norm(pair):
    return tuple(None if v is None else float(v) for v in pair)


def main() -> int:
    failed = 0

    print("1) LENGTH family hand-pins:")
    for s, L, N, C in LEN_PINS:
        got = (sas_length(s), sas_lengthn(s), sas_lengthc(s))
        if got != (L, N, C):
            failed += 1
            print(f"  FAIL {s!r} -> {got} want {(L, N, C)}")
    print(f"  {len(LEN_PINS)} length fixtures checked")

    print("2) MAX/MIN hand-pins (ignore missing):")
    for vals, mx, mn in AGG_PINS:
        got = (sas_max(*vals), sas_min(*vals))
        if got != (mx, mn):
            failed += 1
            print(f"  FAIL {vals} -> {got} want {(mx, mn)}")
    print(f"  {len(AGG_PINS)} agg fixtures checked")

    print("3) the landmines (naive vs SAS):")
    nd = [s for s, *_ in LEN_PINS if len(str(s)) != sas_length(s)]
    print(f"  naive len() over-counts on {len(nd)} of {len(LEN_PINS)} length fixtures")
    naive_max = float(np.max([3.0, np.nan, 7.0]))
    sas_ans = sas_max(3, float("nan"), 7)
    diverge = naive_max != naive_max and sas_ans == 7  # nan vs 7
    print(f"  naive np.max([3,nan,7]) = {naive_max} vs SAS MAX = {sas_ans}")
    if not nd or not diverge:
        failed += 1
        print("  FAIL: expected divergence, found none")

    print("4) cross-language Python/R agreement:")
    strings = [s for s, *_ in LEN_PINS] + ["hello   ", "  ", "z", "  mid  "]
    pl = [(sas_length(s), sas_lengthn(s), sas_lengthc(s)) for s in strings]
    lmis = sum(1 for a, b in zip(pl, r_length(strings)) if a != b)
    failed += lmis
    print(f"  LENGTH: {len(strings)} fixtures, {lmis} Python/R mismatches")
    tuples = [t for t, *_ in AGG_PINS] + [(10, 20, None), (None,), (1.5, 2.5, 0.5)]
    pa = [norm((sas_max(*t), sas_min(*t))) for t in tuples]
    amis = sum(1 for a, b in zip(pa, r_agg(tuples)) if a != norm(b))
    failed += amis
    print(f"  MAX/MIN: {len(tuples)} fixtures, {amis} Python/R mismatches")

    print("5) SUBSTR (1-based) hand-pins, the landmine, and Python/R:")
    for s, pos, ln, exp in SUB_PINS:
        got = sas_substr(s, pos, ln)
        if got != exp:
            failed += 1
            print(f"  FAIL substr({s!r},{pos},{ln}) -> {got!r} want {exp!r}")
    naive = "abcde"[2:2 + 3]  # 1-based args used as 0-based
    print(f"  naive s[pos:pos+len] on ('abcde',2,3) = {naive!r} vs SAS {sas_substr('abcde', 2, 3)!r}")
    if naive == sas_substr("abcde", 2, 3):
        failed += 1
        print("  FAIL: expected divergence, found none")
    cases = [(s, pos, ln) for s, pos, ln, _ in SUB_PINS]
    ps = [sas_substr(s, pos, ln) for s, pos, ln in cases]
    smis = sum(1 for a, b in zip(ps, r_substr(cases)) if a != b)
    failed += smis
    print(f"  SUBSTR: {len(cases)} fixtures, {smis} Python/R mismatches")

    print("6) %EVAL (integer arithmetic, truncating division):")
    for expr, want in EVAL_PINS:
        got = sas_eval(expr)
        if got != want:
            failed += 1
            print(f"  FAIL %eval({expr}) -> {got} want {want}")
    print(f"  %sysevalf('7/2') = {sas_sysevalf('7/2')} (float) vs "
          f"%eval('7/2') = {sas_eval('7/2')} (int, the landmine)")
    if sas_sysevalf("7/2") == sas_eval("7/2"):
        failed += 1
        print("  FAIL: expected int/float divergence, found none")
    pe = [sas_eval(f"{a}/{b}") for a, b in EVALDIV_PAIRS]
    emis = sum(1 for a, b in zip(pe, r_evaldiv(EVALDIV_PAIRS)) if a != b)
    failed += emis
    print(f"  integer division: {len(EVALDIV_PAIRS)} fixtures, {emis} Python/R mismatches")

    print("7) CHAR->NUM coercion (blank/invalid -> missing) hand-pins:")
    for s, want in CHARNUM_PINS:
        got = sas_charnum(s)
        if not charnum_eq(got, want):
            failed += 1
            print(f"  FAIL charnum({s!r}) -> {got} want {want}")
    print(f"  {len(CHARNUM_PINS)} char->num fixtures checked")

    print("   the landmine (naive float() vs SAS missing):")
    crashers = [s for s in ("", "abc", "1,000", "$5")
                if _raises_float(s)]
    sas_missing = all(sas_charnum(s) is None for s in ("", "abc", "1,000", "$5"))
    print(f"  naive float() raised on {len(crashers)}/4 rows SAS reads as missing; "
          f"SAS raised on 0")
    if len(crashers) != 4 or not sas_missing:
        failed += 1
        print("  FAIL: expected float() to crash where SAS returns missing")

    print("   cross-language Python/R agreement:")
    cstrings = [s for s, _ in CHARNUM_PINS] + ["1.5e2", "  -0.25 ", "99", "NaN", "Inf"]
    pc = [sas_charnum(s) for s in cstrings]
    cmis = sum(1 for a, b in zip(pc, r_charnum(cstrings)) if not charnum_eq(a, b))
    failed += cmis
    print(f"  CHAR->NUM: {len(cstrings)} fixtures, {cmis} Python/R mismatches")

    print()
    print("VERIFIED: MAX/MIN, LENGTH, SUBSTR, %EVAL, and CHAR->NUM match the rule "
          "and agree Python/R" if failed == 0 else f"FAILED: {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
