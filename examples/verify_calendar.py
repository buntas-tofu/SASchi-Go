#!/usr/bin/env python3
"""DS-033 original calendar pins and independent base-R evidence, no live SAS."""
import csv
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_calendar

PINS = [
    ('mdy', (1, 1, 1960), 0), ('mdy', (12, 31, 1959), -1),
    ('mdy', (1, 1, 1970), 3653), ('mdy', (1, 1, 2000), 14610),
    ('mdy', (2, 29, 2000), 14669), ('mdy', (7, 11, 2001), 15167),
    ('mdy', (1, 1, 1900), -21914), ('mdy', (2, 28, 1900), -21856),
    ('mdy', (3, 1, 1900), -21855), ('mdy', (1., 1., 1960.), 0),
    ('weekday', (0,), 6), ('weekday', (1,), 7), ('weekday', (2,), 1),
    ('weekday', (3,), 2), ('weekday', (4,), 3), ('weekday', (5,), 4),
    ('weekday', (6,), 5), ('weekday', (-1,), 5), ('weekday', (-5,), 1),
    ('weekday', (-6,), 7), ('weekday', (-7,), 6),
    ('weekday', (58,), 1), ('weekday', (59,), 2), ('weekday', (60,), 3),
    ('weekday', (14610,), 7), ('weekday', (14669,), 3),
]


def ordinal(year, month, day):
    """Constructive Gregorian day count, independent of datetime/date helpers."""
    prior = year - 1
    before_month = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)[month - 1]
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return 365 * prior + prior // 4 - prior // 100 + prior // 400 + before_month + (month > 2 and leap) + day


def days_in_month(year, month):
    if month == 2:
        return 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
    return 30 if month in (4, 6, 9, 11) else 31


def successes():
    result = list(PINS)
    dates = []
    for year in (1753, 1799, 1800, 1899, 1900, 1999, 2000, 2099, 2100, 2399, 2400, 3999):
        for month in range(1, 13):
            dates.extend((year, month, day) for day in (1, days_in_month(year, month)))
    rng = random.Random(3301)
    for _ in range(2000):
        year, month = rng.randint(1753, 3999), rng.randint(1, 12)
        dates.append((year, month, rng.randint(1, days_in_month(year, month))))
    for year, month, day in dates:
        offset = ordinal(year, month, day) - ordinal(1960, 1, 1)
        result.extend([('mdy', (month, day, year), offset),
                       ('weekday', (offset,), (offset + 5) % 7 + 1)])
    return result


def refusals():
    bad = (None, {'missing': 'A'}, {'missing': '_'}, True, False, '1', [], {},
           float('nan'), float('inf'), float('-inf'), 10**400)
    result = [('weekday', (value,), None) for value in bad]
    for index in range(3):
        for value in bad:
            args = [1, 1, 2000]
            args[index] = value
            result.append(('mdy', tuple(args), None))
    result.extend(('mdy', args, None) for args in (
        (0, 1, 2000), (13, 1, 2000), (1.5, 1, 2000), (1, 0, 2000),
        (1, 32, 2000), (1, 1.5, 2000), (1, 1, 20), (1, 1, 1752),
        (1, 1, 4000), (1, 1, 2000.5), (2, 29, 1900), (2, 29, 2100),
        (2, 30, 2000), (4, 31, 2000), (6, 31, 2000)))
    lower, upper = ordinal(1753, 1, 1) - ordinal(1960, 1, 1), ordinal(3999, 12, 31) - ordinal(1960, 1, 1)
    result.extend(('weekday', (day,), None) for day in (lower - 1, upper + 1, .5, -.5))
    result.extend([(name, args, None) for name, args in (
        ('mdy', ()), ('mdy', (1, 1)), ('mdy', (1, 1, 2000, 1)),
        ('weekday', ()), ('weekday', (0, 1)), ('unsupported', (0,)))])
    return result


def rrun(mode, path):
    r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r, str(HERE / 'calendar.R'), mode, str(path)],
                          capture_output=True, text=True, check=True, timeout=90).stdout


def program_records(path):
    lines = rrun('program', path).splitlines()
    header = lines[0].split(':')
    assert len(header) == 3 and header[0] == 'STATE', 'independent program state missing'
    records = []
    for line in lines[1:]:
        assert line.startswith('RECORD:'), 'unexpected independent witness output'
        records.append(bytes.fromhex(line[7:]).decode('ascii'))
    assert len(records) == int(header[2]), 'independent program record count differs'
    return records, int(header[1])


def kind(value):
    if isinstance(value, bool): return 'boolean'
    if isinstance(value, (int, float)): return 'number'
    if value is None: return 'missing'
    if isinstance(value, dict): return 'structured'
    return 'text'


def main():
    good, bad = successes(), refusals()
    cases = good + bad
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'cases.csv'
        with path.open('w', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['id', 'name', 'count', 'a_kind', 'a', 'b_kind', 'b', 'c_kind', 'c'])
            for index, (name, args, _) in enumerate(cases):
                padded = list(args[:3]) + [None] * (3 - len(args[:3]))
                writer.writerow([index, name, len(args), *(item for value in padded for item in (kind(value), str(value)))])
        rows = rrun('cases', path).splitlines()
    assert len(rows) == len(cases), 'independent R row-count guard'
    for index, ((name, args, expected), row) in enumerate(zip(cases, rows)):
        if index < len(good):
            assert sas_calendar(name, *args) == expected, (index, name, args)
            assert row == f'{index}:OK:{expected}', (index, row)
        else:
            try: sas_calendar(name, *args)
            except ValueError: pass
            else: raise AssertionError(('missing calendar refusal', index, name))
            assert row == f'{index}:REFUSE', (index, row)
    # Discriminators catch common host defaults and century simplifications.
    assert 0 != PINS[2][2], 'Unix epoch is not the SAS date epoch'
    assert 4 != PINS[10][2], 'Monday-zero weekday is not Sunday-one weekday'
    assert 1900 % 4 == 0 and days_in_month(1900, 2) == 28, 'century exception'
    assert 2000 % 100 == 0 and days_in_month(2000, 2) == 29, '400-year exception'
    print(f'VERIFIED: calendar {len(PINS)} pins, {len(good)-len(PINS)} constructive/boundary R cases, '
          f'{len(bad)} shared typed/date/range/arity refusals, 4 naive errors caught; '
          'valid dates in1753..3999, independent base R; no live SAS')


if __name__ == '__main__':
    main()
