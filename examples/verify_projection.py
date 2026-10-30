"""Bounded KEEP/DROP selection, independent R order and original source witness."""
import csv
from copy import deepcopy
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from saschi.plan import compile_plan
from saschi.projection import declaration, name_list, selected_names
from saschi.runtime import run_plan
from saschi.compare import equal, table_equal

ORIGINAL = HERE / 'projection_capture.sas'
PINS = [(['b', 'a', 'c'], 'keep', 'a b', ['b', 'a']),
        (['b', 'a', 'c'], 'drop', 'a', ['b', 'c']),
        (['x3', 'x1', 'x2', 'z'], 'keep', 'x1-x3', ['x3', 'x1', 'x2']),
        (['x1', 'x2', 'x3', 'z'], 'drop', 'x1 - x3', ['z']),
        (['a'], 'keep', 'A', ['a']),
        ([f'x{i}' for i in range(64, 0, -1)], 'keep', 'x1-x64', [f'x{i}' for i in range(64, 0, -1)])]
BAD_LISTS = ['', 'a a', 'a A', '_n_', '_error_', '_all_', '_numeric_', '_character_',
             'a:', 'a--c', 'x0-x2', 'x01-x03', 'x2-x1', 'x1-y2', 'x1-x65',
             'a,b', 'a keep=b', 'a rename=(a=b)', 'a /', 'K', 'aK', '1a', 'a' * 33]
REFUSALS = [(['a', 'b'], 'keep', text) for text in BAD_LISTS] + [
    (['a', 'b'], 'keep', 'c'), (['a', 'b'], 'drop', 'a b'),
    (['a', 'b'], 'drop', 'c')]


def rrun(*args):
    executable = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([executable, str(HERE / 'projection.R'), *map(str, args)],
                          capture_output=True, text=True, check=True, timeout=60).stdout


def program_witness(path=ORIGINAL):
    result = {'datasets': {}, 'log': []}
    names = []
    table = None
    lines = rrun('program', path).splitlines()
    for line in lines[1:]:
        tag, value = line.split(':', 1)
        if tag == 'TABLE':
            table = {'schema': {}, 'rows': []}
            result['datasets'][value] = table
        elif tag == 'SCHEMA':
            for column in value.split(','):
                name, spec = column.split('=')
                table['schema'][name] = ('number' if spec == 'number' else
                    {'type': 'character', 'length': int(spec.split(':')[1])})
            names = list(table['schema'])
        elif tag == 'ROW':
            values = [None if v == 'M' else bytes.fromhex(v[1:]).decode() if v[0] == 'C'
                      else float(v[1:]) for v in value.split(',')]
            table['rows'].append(dict(zip(names, values)))
        elif tag == 'LOG':
            result['log'].append(bytes.fromhex(value).decode())
        else:
            raise AssertionError(line)
    return result, int(lines[0].split(':')[1])


def original_expected():
    schema = {'tag': {'type': 'character', 'length': 4}, 'a': 'number', 'c': 'number'}
    source_rows = [{'tag': 'seed', 'a': a, 'c': 3.} for a in (1., 4.)]
    fresh_schema = {'tag': {'type': 'character', 'length': 4}, 'a': 'number',
                    'before': 'number', 'c': 'number'}
    return {'datasets': {'source': {'schema': schema, 'rows': source_rows},
                        'capture': {'schema': schema, 'rows': [dict(row) for row in source_rows for _ in range(2)]},
                        'fresh': {'schema': fresh_schema, 'rows': [
                            {'tag': 'seed', 'a': a, 'before': None, 'c': 7.} for a in (1., 4.)]}},
            'log': ['b=99 tag=seed', 'b=99 tag=seed']}


def naive_controls():
    expected = original_expected()
    # Removing b from the PDV loses supported PUT state.
    wrong = deepcopy(expected)
    wrong['log'] = ['b=. tag=seed', 'b=. tag=seed']
    assert not equal(wrong, expected)
    # KEEP list order does not become descriptor order.
    wrong = deepcopy(expected['datasets']['source'])
    wrong['schema'] = {n: wrong['schema'][n] for n in ('c', 'a', 'tag')}
    assert not table_equal(wrong, expected['datasets']['source'])
    # A late KEEP declaration applies to snapshots taken before it.
    wrong = deepcopy(expected['datasets']['source'])
    wrong['schema']['b'] = 'number'
    for row in wrong['rows']:
        row['b'] = 2.
    assert not table_equal(wrong, expected['datasets']['source'])
    # Input DROP removes c before PDV discovery and every observation.
    wrong = deepcopy(expected['datasets']['fresh'])
    for row in wrong['rows']:
        row['before'] = 3.
    assert not table_equal(wrong, expected['datasets']['fresh'])
    return 4


def main():
    rng = random.Random(4701)
    cases = list(PINS)
    for _ in range(300):
        names = [f'x{i}' for i in range(1, rng.randint(2, 20) + 1)]
        rng.shuffle(names)
        selected = rng.sample(names, rng.randint(1, len(names) - 1))
        mode = rng.choice(('keep', 'drop'))
        expected = [n for n in names if (n in selected) == (mode == 'keep')]
        cases.append((names, mode, ' '.join(selected), expected))
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'cases.csv'
        with path.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['schema', 'mode', 'list'])
            writer.writerows((' '.join(names), mode, text) for names, mode, text, _ in cases)
            writer.writerows((' '.join(names), mode, text) for names, mode, text in REFUSALS)
        observed = rrun('cases', path).splitlines()
    assert len(observed) == len(cases) + len(REFUSALS)
    for (names, mode, text, expected), line in zip(cases, observed):
        selection = declaration(mode + ' ' + text)
        assert selected_names(dict.fromkeys(names, 'number'), selection) == expected
        assert line == 'OK:' + ','.join(expected), (names, mode, text, line)
        catalog = {'raw': {'schema': dict.fromkeys(names, 'number'),
                           'rows': [{n: float(i) for i, n in enumerate(names)}]}}
        for source in (f'data d;set raw;{mode} {text};run;',
                       f'data d({mode}={text});set raw;run;',
                       f'data d;set raw({mode}={text});run;'):
            plan = compile_plan(source)
            assert not plan.blocked, plan.tickets
            table = run_plan(plan.to_dict(), catalog)['datasets']['d']
            assert list(table['schema']) == expected
            assert table['rows'] == [{n: catalog['raw']['rows'][0][n] for n in expected}]
    for (names, mode, text), line in zip(REFUSALS, observed[len(cases):]):
        try:
            selected_names(dict.fromkeys(names, 'number'), declaration(mode + ' ' + text))
        except ValueError:
            pass
        else:
            raise AssertionError(('missing refusal', names, mode, text))
        assert line == 'REFUSE', (text, line)
    expected, statements = program_witness()
    plan = compile_plan(ORIGINAL.read_text())
    assert not plan.blocked, plan.tickets
    assert run_plan(plan.to_dict()) == expected == original_expected()
    assert statements == 25, statements
    controls = naive_controls()
    print(f'VERIFIED: projection6 hand pins,300 constructive R/source/runtime cases across3 timing forms,'
          f'{len(REFUSALS)} shared refusals,{controls} naive controls and complete original25-statement program; no live SAS')


if __name__ == '__main__':
    main()
