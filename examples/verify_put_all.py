#!/usr/bin/env python3
"""Original DS-025 pins and independent R records. No live SAS evidence."""
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
from sas_semantics import sas_put_all


def field(name, value, kind='number'):
    return {'name': name, 'kind': kind, 'value': value}


TAIL = '_ERROR_=0 _N_=1 '
PINS = [([], TAIL), ([field('n', 7)], 'n=7 ' + TAIL),
        ([field('n', None)], 'n=. ' + TAIL), ([field('n', -0.)], 'n=0 ' + TAIL),
        ([field('z', -3), field('A', '  x  ', 'character')], 'z=-3 A=x ' + TAIL),
        ([field('c', 'a  b', 'character')], 'c=a  b ' + TAIL),
        ([field('c', "O'Neil", 'character')], "c=O'Neil " + TAIL),
        ([field('n', -99999999999)], 'n=-99999999999 ' + TAIL),
        ([field('n', 99999999999)], 'n=99999999999 ' + TAIL),
        ([field('x', 'q' * 45, 'character')], 'x=' + 'q' * 45 + ' ' + TAIL)]
REFUSALS = [([field('n', 1.25)], 'whole numbers'),
            ([field('n', 100000000000)], 'whole numbers'),
            ([field('n', float('inf'))], 'whole numbers'),
            ([field('n', float('nan'))], 'whole numbers'),
            ([field('n', True)], 'ordinary numeric'),
            ([field('n', '7')], 'ordinary numeric'),
            ([field('n', {'missing': 'A'})], 'ordinary numeric'),
            ([field('c', '', 'character')], 'blank character'),
            ([field('c', '   ', 'character')], 'blank character'),
            ([field('c', None, 'character')], 'printable ASCII'),
            ([field('c', 'a\tb', 'character')], 'printable ASCII'),
            ([field('c', 'café', 'character')], 'printable ASCII'),
            ([field('x', 'q' * 46, 'character')], 'LINESIZE'),
            ([field('_n_', 1)], 'V7'), ([field('a', 1), field('A', 2)], 'V7'),
            ([field('bad name', 1)], 'V7'), ([field('x', 1, 'other')], 'field kind')]


def rscript():
    return os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'


def program_records(path):
    run = subprocess.run([rscript(), str(HERE / 'put_all.R'), 'program', str(path)],
                         capture_output=True, text=True, timeout=60, check=True)
    return [bytes.fromhex(line).decode('ascii') for line in run.stdout.splitlines()]


def generated_cases():
    for body, pad, n in itertools.product(('Q', 'two words', 'a  b', 'say "yes"'), ('', ' ', '   '), range(-8, 9)):
        yield [field('Text', pad + body + pad, 'character'), field('count', float(n))], 'Text=' + body + ' count=' + str(n) + ' ' + TAIL


def main():
    successes = PINS + list(generated_cases())
    for fields, expected in successes:
        assert sas_put_all(fields) == expected, (fields, expected)
    for fields, reason in REFUSALS:
        try:
            sas_put_all(fields)
        except ValueError as exc:
            assert reason in str(exc), (fields, reason, exc)
        else:
            raise AssertionError(('must refuse', fields))
    cases = successes + REFUSALS
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'fields.csv'
        with path.open('w', newline='') as stream:
            writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
            writer.writerow(['id', 'name', 'kind', 'value', 'type'])
            for index, (fields, _) in enumerate(cases):
                if not fields:
                    writer.writerow([index, '', 'empty', '', 'empty'])
                for item in fields:
                    value = item['value']
                    kind = ('text' if isinstance(value, str) else 'missing' if value is None else
                            'boolean' if isinstance(value, bool) else 'tagged' if isinstance(value, dict) else 'number')
                    writer.writerow([index, item['name'], item['kind'], str(value), kind])
        run = subprocess.run([rscript(), str(HERE / 'put_all.R'), 'fields', str(path)],
                             capture_output=True, text=True, timeout=60, check=True)
    results = run.stdout.splitlines()
    assert len(results) == len(cases)
    for index, ((fields, expected), result) in enumerate(zip(cases, results)):
        if index < len(successes):
            assert result.startswith('OK:') and bytes.fromhex(result[3:]).decode('ascii') == expected, (fields, result)
        else:
            assert result.startswith('ERROR:') and expected in result, (fields, result)
    assert 'A=x z=-3 ' + TAIL != PINS[4][1], 'alphabetical PDV sort must differ'
    assert 'n=7 ' != PINS[1][1], 'automatic variables must be present'
    assert 'z=-3 A=  x ' + TAIL != PINS[4][1], 'leading blanks must be removed'
    assert PINS[0][1].rstrip() != PINS[0][1], 'pointer separator must survive'
    print(f'VERIFIED: PUT _ALL_ {len(PINS)} pins, {len(successes)-len(PINS)} generated cases, '
          f'{len(REFUSALS)} shared refusals, 4 naive errors caught; independent base R; no live SAS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
