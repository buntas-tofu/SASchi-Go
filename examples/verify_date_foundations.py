#!/usr/bin/env python3
"""Independent original date foundations; no source/whole-vendor acceptance."""
import csv
from pathlib import Path
import os
import random
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from examples.verify_calendar import ordinal, days_in_month

MONTHS = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC')
DATE_PINS = [('01JAN1960', 0), ('31DEC1959', -1), ('01JAN1970', 3653),
             ('01JAN2000', 14610), ('29FEB2000', 14669), ('01JAN1900', -21914),
             ('16mar2012', 19068), ('.', None)]
FIELD_PINS = [(0, 'weekdate', 29, 'Friday, January 1, 1960'),
              (1, 'weekdate', 37, 'Saturday, January 2, 1960'),
              (3653, 'weekdate', 29, 'Thursday, January 1, 1970'),
              (14610, 'weekdate', 29, 'Saturday, January 1, 2000'),
              (14669, 'worddate', 20, 'February 29, 2000'),
              (0, 'worddate', 18, 'January 1, 1960'),
              (None, 'weekdate', 37, '.'), (None, 'worddate', 20, '.')]


def kind(value):
    if type(value) is str: return 'text'
    if type(value) is bool: return 'boolean'
    if type(value) is int: return 'int'
    if type(value) is float: return 'number'
    if value is None: return 'missing'
    return 'structured'


def cases():
    good = [('read9', token, '', 0, expected) for token, expected in DATE_PINS]
    good += [('field', value, fmt, width, text.rjust(width))
             for value, fmt, width, text in FIELD_PINS]
    rng = random.Random(8011)
    dates = [(year, month, day) for year in (1753, 1800, 1900, 1960, 2000, 2100, 2400, 3999)
             for month in range(1, 13) for day in (1, days_in_month(year, month))]
    for _ in range(500):
        year, month = rng.randrange(1753, 4000), rng.randrange(1, 13)
        dates.append((year, month, rng.randint(1, days_in_month(year, month))))
    for year, month, day in dates:
        token = f'{day:02}{MONTHS[month-1]}{year:04}'
        value = ordinal(year, month, day) - ordinal(1960, 1, 1)
        good.append(('read9', token, '', 0, value))
        # Field text comes from the independent R/C-locale witness, never the engine.
        good.append(('field', value, 'weekdate', rng.choice((29, 30, 37)), ...))
        good.append(('field', value, 'worddate', rng.choice((18, 20, 32)), ...))
    bad = [('read9', value, '', 0, ...) for value in (
        None, True, 0, 19600101, [], {}, '', ' ', '01JAN60', '1JAN1960',
        '01JAN01960', '01JAN1960X', ' 01JAN1960', '01JAN1960 ', '00JAN1960',
        '32JAN1960', '31APR2000', '29FEB1900', '29FEB2100', '30FEB2000',
        '01XYZ2000', '01MÄR2000', '01JAN1752', '01JAN4000', '.A', '._', '\0', '\t')]
    for value in (True, '0', [], {}, float('nan'), float('inf'), -.5,
                  ordinal(1753,1,1)-ordinal(1960,1,1)-1,
                  ordinal(3999,12,31)-ordinal(1960,1,1)+1):
        bad.append(('field', value, 'worddate', 20, ...))
    for fmt, width in [('weekdate', 28), ('weekdate', 38), ('weekdate', 50),
                       ('worddate', 17), ('worddate', 33), ('worddate', True),
                       ('worddate', 20.0), ('worddate', '20'), ('worddate', None),
                       ('date', 9), ('WÉEKDATE', 29), (None, 29), ([], 29)]:
        bad.extend([('field', 0, fmt, width, ...), ('field', None, fmt, width, ...)])
    return good, bad


def witness(rows):
    with tempfile.TemporaryDirectory(prefix='saschi-date-oracle-') as directory:
        path = Path(directory) / 'cases.csv'
        with path.open('w', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['id', 'op', 'kind', 'value', 'fmt_kind', 'fmt', 'width_kind', 'width'])
            for index, (op, value, fmt, width, _) in enumerate(rows):
                writer.writerow([index, op, kind(value), str(value), kind(fmt), str(fmt), kind(width), str(width)])
        executable = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        run = subprocess.run([executable, str(HERE/'date_foundations.R'), str(path)],
                             text=True, capture_output=True, check=True, timeout=120)
    answers = run.stdout.splitlines()
    assert len(answers) == len(rows), 'independent R count differs'
    results = []
    for index, answer in enumerate(answers):
        number, _, payload = answer.partition(':')
        assert number == str(index), 'independent R order differs'
        if payload == 'REFUSE': results.append(...)
        elif payload == 'M': results.append(None)
        elif payload.startswith('N:'): results.append(int(payload[2:]))
        elif payload.startswith('T:'): results.append(bytes.fromhex(payload[2:]).decode('ascii'))
        else: raise AssertionError(('invalid R response', answer))
    return results


def qualify():
    good, bad = cases()
    answers = witness(good + bad)
    for row, expected in zip(good, answers[:len(good)], strict=True):
        assert expected is not ..., ('independent constructive case refused', row)
        if row[-1] is not ...: assert expected == row[-1], ('hand/R pin differs', row, expected)
    assert all(answer is ... for answer in answers[len(good):]), 'independent refusal differs'
    return good, bad, answers


def main():
    good, bad, answers = qualify()
    from saschi.date_foundations import sas_input_date9, sas_date_field
    for row, expected in zip(good, answers[:len(good)], strict=True):
        op, value, fmt, width, _ = row
        actual = sas_input_date9(value) if op == 'read9' else sas_date_field(value, fmt, width)
        assert type(actual) is type(expected), ('date foundation result type differs', row)
        assert actual == expected, (row, actual, expected)
    for op, value, fmt, width, _ in bad:
        try:
            sas_input_date9(value) if op == 'read9' else sas_date_field(value, fmt, width)
        except ValueError: pass
        else: raise AssertionError(('missing date foundation refusal', op, value, fmt, width))
    assert sas_input_date9('01JAN1970') != 0, 'Unix epoch discriminator'
    assert sas_date_field(0, 'weekdate', 29).strip() != 'Thursday, January 1, 1960', 'weekday discriminator'
    assert sas_date_field(0, 'worddate', 20).startswith(' '), 'alignment discriminator'
    print(f'VERIFIED: date foundations {len(DATE_PINS)+len(FIELD_PINS)} hand pins, '
          f'{len(good)} independent R positive cases,{len(bad)} shared refusals; '
          'canonical DATE9 and valid full-name right-aligned fields; reference only, no source execution or live SAS')


if __name__ == '__main__':
    main()
