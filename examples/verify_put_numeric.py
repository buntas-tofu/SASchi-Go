#!/usr/bin/env python3
"""DS-027 original pins and independent base-R records, no live SAS evidence."""
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
from sas_semantics import sas_put_numeric_list

PINS = [([0], '0 '), ([7], '7 '), ([-3], '-3 '), ([None], '. '),
        ([-0.0], '0 '), ([7, -3, None], '7 -3 . '),
        ([99999999999], '99999999999 '), ([-99999999999], '-99999999999 '),
        ([1e10, -1e10], '10000000000 -10000000000 '),
        ([0] * 32, '0 ' * 32)]
REFUSALS = [([], 'nonempty value list'), ([1.25], 'whole numbers'),
            ([100000000000], 'whole numbers'), ([-100000000000], 'whole numbers'),
            ([float('inf')], 'whole numbers'), ([float('-inf')], 'whole numbers'),
            ([float('nan')], 'whole numbers'), ([True], 'ordinary numeric'),
            (['7'], 'ordinary numeric'), ([{'missing': 'A'}], 'ordinary numeric'),
            ([0] * 33, 'LINESIZE'), ([-99999999999] * 5, 'LINESIZE')]


def generated_cases():
    domain = (-99999999999, -10000000000, -17, -1, 0, 1, 17, 10000000000, 99999999999, None)
    for values in itertools.product(domain, repeat=3):
        yield list(values), ''.join(('.' if value is None else str(value)) + ' ' for value in values)


def main():
    successes = PINS + list(generated_cases())
    for values, expected in successes:
        assert sas_put_numeric_list(values) == expected, (values, expected)
    for values, reason in REFUSALS:
        try:
            sas_put_numeric_list(values)
        except ValueError as exc:
            assert reason in str(exc), (values, reason, exc)
        else:
            raise AssertionError(('must refuse', values))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'numeric.csv'
        with path.open('w', newline='') as stream:
            writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
            writer.writerow(['id', 'type', 'value'])
            for index, (values, _) in enumerate(successes + REFUSALS):
                if not values:
                    writer.writerow([index, 'empty', ''])
                for value in values:
                    kind = ('missing' if value is None else 'boolean' if isinstance(value, bool) else
                            'text' if isinstance(value, str) else 'tagged' if isinstance(value, dict) else 'number')
                    writer.writerow([index, kind, str(value)])
        r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        run = subprocess.run([r, str(HERE / 'put_numeric.R'), str(path)],
                             capture_output=True, text=True, timeout=60, check=True)
    results = run.stdout.splitlines()
    assert len(results) == len(successes + REFUSALS)
    for index, ((values, expected), result) in enumerate(zip(successes + REFUSALS, results)):
        if index < len(successes):
            assert result.startswith('OK:') and bytes.fromhex(result[3:]).decode('ascii') == expected, (values, result)
        else:
            assert result.startswith('ERROR:') and expected in result, (values, result)
    assert ' '.join(['7', '-3', '.']) != PINS[5][1], 'final separator must survive'
    assert '7.0 ' != PINS[1][1], 'integer-valued floats omit decimals'
    assert '-0 ' != PINS[4][1], 'negative zero prints zero'
    assert '1e+10 -1e+10 ' != PINS[8][1], 'bounded integers use full decimal digits'
    print(f'VERIFIED: numeric list PUT {len(PINS)} pins, {len(successes)-len(PINS)} generated cases, '
          f'{len(REFUSALS)} shared refusals, 4 naive errors caught; independent base R; no live SAS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
