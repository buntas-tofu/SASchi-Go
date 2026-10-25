#!/usr/bin/env python3
"""DS-013 MOD gate: original pins, constructive cases, fmod and base R.

Repository evidence for maintainers, no live SAS. The MOD reference linked in
DS-013 promises exact integer results in the host exact-integer range. Expected
values below are hand-derived or constructed as quotient*divisor+remainder;
neither the Python reference nor the R witness generates the expectations.
Refusals are implementation boundaries, not expectations for SAS errors/logs.
"""
import csv
import itertools
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_mod

LIMIT = 2**53
PINS = [
    ((7, 3), 1), ((-7, 3), -1), ((7, -3), 1), ((-7, -3), -1),
    ((0, 3), 0), ((0, -3), 0), ((-0.0, 3), 0),
    ((12, 3), 0), ((-12, 3), 0), ((12, -3), 0), ((-12, -3), 0),
    ((2, 9), 2), ((-2, 9), -2), ((2, -9), 2), ((-2, -9), -2),
    ((LIMIT, 3), 2), ((-LIMIT, 3), -2), ((LIMIT, -3), 2),
    ((LIMIT - 1, 3), 1), ((LIMIT, LIMIT), 0),
    ((LIMIT - 1, LIMIT), LIMIT - 1), ((LIMIT, LIMIT - 1), 1),
    ((-LIMIT, -(LIMIT - 1)), -1), ((LIMIT, 2**52 + 1), 2**52 - 1),
    ((LIMIT - 1, 2**52 + 1), 2**52 - 2), ((LIMIT, 3 * 2**50), 2**51),
    ((LIMIT, 1), 0), ((7.0, 3.0), 1),
]

REFUSALS = [
    ((7, 0), 'zero divisor'), ((0, 0), 'zero divisor'), ((7, -0.0), 'zero divisor'),
    ((None, 3), 'missing or structured'), ((7, None), 'missing or structured'),
    ((None, None), 'missing or structured'),
    (({'missing': 'A'}, 3), 'missing or structured'),
    ((7, {'missing': '_'}), 'missing or structured'),
    ((float('nan'), 3), 'nonfinite'), ((float('inf'), 3), 'nonfinite'),
    ((7, -float('inf')), 'nonfinite'),
    ((7.5, 3), 'fractional'), ((7, .5), 'fractional'), ((.3, -.1), 'fractional'),
    ((LIMIT + 2, 3), 'exact-integer bound'), ((7, -LIMIT - 2), 'exact-integer bound'),
    (('7', 3), 'numeric arguments'), ((7, '3'), 'numeric arguments'),
    ((True, 3), 'numeric arguments'), ((7, False), 'numeric arguments'),
    (([7], 3), 'numeric arguments'),
]


def generated_cases():
    for divisor in range(1, 18):
        for quotient, remainder in itertools.product(range(17), range(divisor)):
            for sign_a, sign_b in itertools.product((-1, 1), repeat=2):
                yield (sign_a * (quotient * divisor + remainder), sign_b * divisor), sign_a * remainder
    for magnitude in (2**26, 2**40, 2**52, LIMIT):
        for divisor in (1, 2, 3, 7, 31, 2**20 + 1, 2**26 - 1, 2**40 + 1, 2**52 - 1, LIMIT):
            quotient = magnitude // divisor
            for remainder in sorted({0, 1, divisor - 1}):
                dividend = quotient * divisor + remainder
                if remainder < divisor and dividend <= LIMIT:
                    for sign_a, sign_b in itertools.product((-1, 1), repeat=2):
                        yield (sign_a * dividend, sign_b * divisor), sign_a * remainder


def r_results(cases):
    def encode(value):
        if value is None:
            return '', 'missing'
        if isinstance(value, dict):
            return value['missing'], 'tagged'
        if isinstance(value, bool):
            return str(value), 'boolean'
        if isinstance(value, (int, float)):
            return str(value), 'number'
        return str(value), 'text' if isinstance(value, str) else 'other'

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'mod.csv'
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
            writer.writerow(['a', 'a_kind', 'b', 'b_kind'])
            for args, _ in cases:
                writer.writerow([piece for value in args for piece in encode(value)])
        r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        run = subprocess.run([r, str(HERE / 'mod.R'), str(path)],
                             capture_output=True, text=True, timeout=120, check=True)
    return [line if line.startswith('ERROR:') else int(line) for line in run.stdout.splitlines()]


def main():
    generated = list(generated_cases())
    successes = PINS + generated
    for args, expected in successes:
        assert sas_mod(*args) == expected, (args, expected)
        assert math.fmod(*args) == expected, ('fmod witness', args, expected)
    for args, reason in REFUSALS:
        try:
            sas_mod(*args)
        except ValueError as exc:
            assert reason in str(exc), (args, exc)
        else:
            raise AssertionError(('must refuse', args))
    # These Python integers cannot be transported losslessly as R doubles.
    for number in (LIMIT + 1, -(LIMIT + 1), 10**400):
        try:
            sas_mod(number, 3)
        except ValueError as exc:
            assert 'exact-integer bound' in str(exc)
        else:
            raise AssertionError('unbounded Python integer accepted')

    cases = successes + REFUSALS
    results = r_results(cases)
    assert len(results) == len(cases), (len(results), len(cases))
    for (args, expected), result in zip(cases, results):
        if isinstance(expected, str):
            assert isinstance(result, str) and expected in result, (args, result)
        else:
            assert result == expected, (args, result, expected)

    assert (-7 % 3) != -1, 'Python divisor-sign default must be caught'
    assert (7 % -3) != 1, 'negative divisor must not change SAS remainder sign'
    # Noninteger MOD fuzzing is deliberately refused, not replaced by fmod.
    assert math.fmod(.3, -.1) != 0
    print(f'VERIFIED: bounded MOD {len(PINS)} pins, {len(generated)} constructive cases, '
          f'{len(REFUSALS)} shared and 3 Python-integer refusals; fmod/base R agree; no live SAS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
