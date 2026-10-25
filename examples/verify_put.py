#!/usr/bin/env python3
"""DS-023: original documented pins, R witness, and wrong-spacing detectors.

Repository evidence for maintainers, not a live-SAS comparison. Expected log
records are hand-derived from the PUT and character-constant references in
DS-023. Generated cases start with known text, encode it as SAS literals, and
check decoding without deriving expectations from either implementation.
"""
import csv
import itertools
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_put_literals
from saschi.plan import compile_plan
from saschi.runtime import run_plan

PINS = [
    (["'Ready'"], 'Ready'),
    (['"Ready"'], 'Ready'),
    (["'left'", "'right'"], 'leftright'),
    (["'left '", "'right'"], 'left right'),
    (["' left  '", "' right '"], ' left   right '),
    (["' '", "'  '"], '   '),
    (["'O''Neil'"], "O'Neil"),
    (['"say ""go"""'], 'say "go"'),
    (["'a'", '"b"', "'c'"], 'abc'),
    (["'a''b'"], "a'b"),
    (["''"], "'"),
    (['""'], '"'),
    (["''''"], "'"),
    (['""""'], '"'),
    (["'a; /* text */'"], 'a; /* text */'),
    (["'_ALL_ _ERROR_'"], '_ALL_ _ERROR_'),
    (["'&name %macro'"], '&name %macro'),
    ([r"'a\nb'"], r'a\nb'),
    (["'" + 'x' * 32 + "'", '"' + 'y' * 32 + '"'], 'x' * 32 + 'y' * 32),
]

REFUSALS = [
    (["'" + 'x' * 65 + "'"], 'LINESIZE review'),
    (["'" + 'x' * 64 + "'", "'x'"], 'LINESIZE review'),
    (["'a\nb'"], 'printable ASCII'),
    (["'a\tb'"], 'printable ASCII'),
    (["'a\x00b'"], 'printable ASCII'),
    (["'café'"], 'printable ASCII'),
    (['"&name"'], 'macro review'),
    (['"%macro()"'], 'macro review'),
    (["'missing"], 'complete quoted literals'),
    (["'a'b'"], 'complete quoted literals'),
    (["'41'x"], 'complete quoted literals'),
]


def generated_cases():
    for size in range(1, 4):
        for chars in itertools.product("a '\"", repeat=size):
            text = ''.join(chars)
            for quote in "'\"":
                encoded = quote + text.replace(quote, quote * 2) + quote
                yield [encoded], text
                yield [encoded, "' '", encoded], text + ' ' + text


def r_results(cases):
    # NUL is tested directly in Python; CSV/R cannot transport embedded NUL.
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'put.csv'
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
            writer.writerow(['id', 'token'])
            for index, (tokens, _) in enumerate(cases):
                for token in tokens:
                    writer.writerow([index, token])
        r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        run = subprocess.run([r, str(HERE / 'put.R'), str(path)],
                             capture_output=True, text=True, check=True, timeout=60)
    return run.stdout.splitlines()


def main():
    generated = list(generated_cases())
    successes = PINS + generated
    for tokens, expected in successes:
        assert sas_put_literals(tokens) == expected, (tokens, expected)
    for tokens, reason in REFUSALS:
        try:
            sas_put_literals(tokens)
        except ValueError as exc:
            assert reason in str(exc), (tokens, exc)
        else:
            raise AssertionError(('must refuse', tokens))

    transportable = [(tokens, reason) for tokens, reason in REFUSALS
                     if not any('\x00' in token for token in tokens)]
    cases = successes + transportable
    results = r_results(cases)
    assert len(results) == len(cases), (len(results), len(cases))
    for index, ((tokens, expected), result) in enumerate(zip(cases, results)):
        if index < len(successes):
            assert result.startswith('OK:'), (tokens, result)
            assert bytes.fromhex(result[3:]).decode('ascii') == expected, (tokens, result)
        else:
            assert result.startswith('ERROR:') and expected in result, (tokens, result)

    for tokens, expected in PINS:
        plan = compile_plan('data _null_; put ' + ' '.join(tokens) + '; run;')
        assert not plan.blocked, plan.tickets
        assert run_plan(plan.to_dict())['log'] == [expected]

    # Known-wrong defaults: print inserts blanks, strip drops explicit blanks,
    # Python does not decode SAS doubled quotes, and empty text is not quote PUT.
    assert ' '.join(['left', 'right']) != PINS[2][1]
    assert PINS[4][1].strip() != PINS[4][1]
    assert "O''Neil" != PINS[6][1]
    assert '' != PINS[10][1]
    print(f'VERIFIED: PUT {len(PINS)} pins, {len(generated)} generated cases, '
          f'{len(REFUSALS)} refusals; independent base R; 4 naive errors caught; no live SAS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
