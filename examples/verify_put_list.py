#!/usr/bin/env python3
"""DS-024 original documented pins and independent R logical-record witness.

Repository evidence for maintainers, not live-SAS output or physical log
equivalence. Blank-value refusal is a support policy, not a SAS behavior claim.
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
from sas_semantics import sas_put_character_list


def char(value):
    return {'kind': 'character', 'value': value}


def lit(value):
    return {'kind': 'literal', 'value': value}


PINS = [
    ([char('Alpha')], 'Alpha '),
    ([char('  Alpha  ')], 'Alpha '),
    ([char('A  B')], 'A  B '),
    ([char('A'), char('B')], 'A B '),
    ([lit("'['"), char('  A  '), lit("']'")], '[A ]'),
    ([char('A'), lit("']'"), char('B')], 'A ]B '),
    ([lit("'('"), lit("'['"), char('A'), lit("']'")], '([A ]'),
    ([lit("'  '"), char(' A '), lit("'  '")], '  A   '),
    ([char("O'Neil"), lit('"said ""yes"""')], 'O\'Neil said "yes"'),
    ([lit("''"), char('A'), lit('""')], "'A \""),
    ([char('&name %macro')], '&name %macro '),
    ([char(r'a\nb')], 'a\\nb '),
    ([char('x' * 63)], 'x' * 63 + ' '),
    ([lit("'['"), char('x' * 61), lit("']'")], '[' + 'x' * 61 + ' ]'),
]
REFUSALS = [
    ([char('')], 'blank character'),
    ([char('   ')], 'blank character'),
    ([char(None)], 'character values'),
    ([char(7)], 'character values'),
    ([char({'missing': 'A'})], 'character values'),
    ([char('x' * 64)], 'LINESIZE review'),
    ([lit("'['"), char('x' * 62), lit("']'")], 'LINESIZE review'),
    ([char('a\tb')], 'printable ASCII'),
    ([char('a\nb')], 'printable ASCII'),
    ([char('a\x00b')], 'printable ASCII'),
    ([char('café')], 'printable ASCII'),
    ([lit('"&name"'), char('A')], 'macro review'),
    ([lit('"%macro"'), char('A')], 'macro review'),
    ([lit("'41'x"), char('A')], 'complete quoted literals'),
    ([{'kind': 'numeric', 'value': '1'}], 'unsupported item kind'),
    ([lit("'only'")], 'at least one character'),
]


def generated_cases():
    # Expected text is constructed before the raw SAS literal tokens exist.
    for left, right, quote, padding in itertools.product(
            ('A', 'two words', "O'Neil", 'say "go"'),
            ('B', 'x  y'), ("'", '"'), ('', ' ', '   ')):
        token = quote + '['.replace(quote, quote * 2) + quote
        yield [lit(token), char(padding + left + padding), char(right), lit("']'")], '[' + left + ' ' + right + ' ]'
        token = quote + left.replace(quote, quote * 2) + quote
        yield [lit(token), char(padding + right + padding)], left + right + ' '


def r_results(cases):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'put-list.csv'
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
            writer.writerow(['id', 'kind', 'value', 'type'])
            for index, (items, _) in enumerate(cases):
                for item in items:
                    value = item['value']
                    kind = 'text' if isinstance(value, str) else 'null' if value is None else 'tagged' if isinstance(value, dict) else 'number'
                    writer.writerow([index, item['kind'], value if kind != 'tagged' else value['missing'], kind])
        r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        run = subprocess.run([r, str(HERE / 'put_list.R'), str(path)], capture_output=True,
                             text=True, check=True, timeout=60)
    return run.stdout.splitlines()


def main():
    generated = list(generated_cases())
    successes = PINS + generated
    for items, expected in successes:
        assert sas_put_character_list(items) == expected, (items, expected)
    for items, reason in REFUSALS:
        try:
            sas_put_character_list(items)
        except ValueError as exc:
            assert reason in str(exc), (items, exc)
        else:
            raise AssertionError(('must refuse', items))
    transportable = [(items, reason) for items, reason in REFUSALS
                     if not any(isinstance(i['value'], str) and '\x00' in i['value'] for i in items)]
    cases = successes + transportable
    results = r_results(cases)
    assert len(results) == len(cases), (len(results), len(cases))
    for index, ((items, expected), result) in enumerate(zip(cases, results)):
        if index < len(successes):
            assert result.startswith('OK:'), (items, result)
            assert bytes.fromhex(result[3:]).decode('ascii') == expected, (items, result)
        else:
            assert result.startswith('ERROR:') and expected in result, (items, result)
    # Wrong defaults: rstrip-only, join-everything, no variable separator,
    # whole-record stripping, and width checks before the separator.
    assert '  Alpha  '.rstrip(' ') + ' ' != PINS[1][1]
    assert ' '.join(['[', 'A', ']']) != PINS[4][1]
    assert '[A]' != PINS[4][1]
    assert PINS[7][1].strip() != PINS[7][1]
    assert len('x' * 64) == 64 and len('x' * 64 + ' ') > 64
    print(f'VERIFIED: PUT character list {len(PINS)} pins, {len(generated)} generated cases, '
          f'{len(REFUSALS)} refusals; independent base R; 5 naive errors caught; no live SAS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
