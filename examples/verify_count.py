#!/usr/bin/env python3
"""COUNT gate: hand-derived pins, independent regex/Python/R agreement.

Repository evidence for maintainers, not a live-SAS comparison. The semantics
source is the SAS COUNT reference linked by DS-022. Overlap is undefined in
SAS; all other refusals below are explicit boundaries of this implementation.
No expected value is obtained from sas_count or from the R twin.
"""
import csv
import itertools
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_count

RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"

# Synthetic pins derived from the documented rule, not copied SAS outputs.
PINS = [
    (("abc", "a", ""), 1),
    (("abc", "z", ""), 0),
    (("abc", "abcd", ""), 0),
    (("aaaa", "a", ""), 4),
    (("abab", "ab", ""), 2),
    (("abc", "A", ""), 0),
    (("abc", "A", "i"), 1),
    (("aA aA", "aa", "I"), 2),
    (("abc", "abc ", ""), 0),
    (("abc", "abc ", "t"), 1),
    (("ab ", "b ", ""), 1),
    (("ab ", "b ", "T"), 1),
    (("ab   ", " ", ""), 3),
    (("   ", " ", ""), 3),
    (("   ", "x", "T"), 0),
    ((" Ab AB ", "ab ", "iT"), 2),
    ((" Ab AB ", "ab ", "Ti"), 2),
    (("Ab", "a ", "IItt"), 1),
    ((" a a ", " a", "T"), 2),
    (("a.*a.*", ".*", ""), 2),
    (("a\tb\t", "\t", "T"), 2),
    (("a\nb\n", "\n", "T"), 2),
    (("a'a'a", "'", ""), 2),
    (("a,b,a", ",", ""), 2),
]

# Error pins assert refusal, never a numeric interpretation of undefined SAS.
REFUSALS = [
    (("aaa", "aa", ""), "overlapping matches"),
    (("abababa", "aba", ""), "overlapping matches"),
    (("AaA", "aa", "I"), "overlapping matches"),
    (("aaaa ", "aa ", "T"), "overlapping matches"),
    (("abc", "", ""), "empty substring"),
    (("abc", "   ", "T"), "empty substring"),
    (("", "a", ""), "zero-length string"),
    (("abc", "a", "x"), "unsupported modifier"),
    (("abc", "a", "i "), "unsupported modifier"),
    (("café", "é", ""), "encoding review"),
    (("abc", "é", ""), "encoding review"),
    (("abc", "a", "İ"), "encoding review"),
    ((None, "a", ""), "character arguments"),
    (("abc", None, ""), "character arguments"),
    (("abc", "a", None), "character arguments"),
    ((123, "1", ""), "character arguments"),
    (("123", 1, ""), "character arguments"),
    (("abc", "a", 1), "character arguments"),
]


def regex_oracle(string, substring, modifiers):
    """Independent enumeration oracle for the nonempty ASCII generated inputs."""
    if "t" in modifiers.lower():
        string, substring = string.rstrip(" "), substring.rstrip(" ")
    if not substring:
        return "empty substring"
    flags = re.IGNORECASE | re.ASCII if "i" in modifiers.lower() else 0
    matches = list(re.finditer("(?=" + re.escape(substring) + ")", string, flags))
    if any(b.start() - a.start() < len(substring) for a, b in zip(matches, matches[1:])):
        return "overlapping matches"
    return len(matches)


def generated_cases():
    words = lambda n: ("".join(chars) for chars in itertools.product("aA ", repeat=n))
    strings = [s for n in range(1, 5) for s in words(n)]
    needles = [s for n in range(1, 3) for s in words(n)]
    for args in itertools.product(strings, needles, ("", "i", "t", "IT")):
        yield args, regex_oracle(*args)


def matches(got, expected):
    if isinstance(expected, str):
        return isinstance(got, str) and got.startswith("ERROR: ") and expected in got
    return got == expected


def python_result(args):
    try:
        return sas_count(*args)
    except ValueError as exc:
        return "ERROR: " + str(exc)


def r_results(cases):
    def encode(value):
        if value is None:
            return "", "missing"
        return str(value), "text" if isinstance(value, str) else "number"

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "count.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
            writer.writerow(["string", "string_kind", "substring", "substring_kind",
                             "modifiers", "modifiers_kind"])
            for args, _ in cases:
                writer.writerow([part for value in args for part in encode(value)])
        run = subprocess.run([str(RSCRIPT), str(HERE / "count.R"), str(path)],
                             capture_output=True, text=True, timeout=120, check=True)
    return [line if line.startswith("ERROR: ") else int(line)
            for line in run.stdout.splitlines()]


def main():
    generated = list(generated_cases())
    cases = PINS + REFUSALS + generated
    failures = []
    python = [python_result(args) for args, _ in cases]
    r = r_results(cases)
    if len(r) != len(cases):
        failures.append(f"R returned {len(r)} rows for {len(cases)} cases")
    for index, (args, expected) in enumerate(cases):
        for lane, results in (("Python", python), ("R", r)):
            if index >= len(results) or not matches(results[index], expected):
                got = results[index] if index < len(results) else "MISSING ROW"
                failures.append(f"{lane} {args!r}: {got!r}, expected {expected!r}")
    # A NUL cannot be represented by R's strings/CSV transport; the Python
    # reference must also refuse it instead of silently extending the slice.
    for args in (("a\x00", "a", ""), ("abc", "\x00", ""), ("abc", "a", "\x00")):
        if not matches(python_result(args), "encoding review"):
            failures.append(f"Python accepted NUL input: {args!r}")
    print(f"COUNT: {len(PINS)} numeric pins, {len(REFUSALS)} refusal pins, "
          f"{len(generated)} enumerated cases; Python and R checked against expectations")
    # Witnesses that naive defaults do not implement the contract.
    landmines = [sas_count("abc", "A", "I") != "abc".count("A"),
                 sas_count("abc", "abc ", "T") != "abc".count("abc "),
                 sas_count("ab ", "b ") != "ab ".rstrip().count("b "),
                 isinstance(python_result(("aaa", "aa", "")), str) and "aaa".count("aa") == 1,
                 isinstance(python_result(("abc", "", "")), str) and "abc".count("") == 4]
    if not all(landmines):
        failures.append("a naive-default divergence witness disappeared")
    if failures:
        for failure in failures[:20]:
            print("FAIL: " + failure)
        print(f"FAILED: {len(failures)} COUNT mismatches")
        return 1
    print("VERIFIED: bounded COUNT matches the documented pins and agrees Python/R; no live SAS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
