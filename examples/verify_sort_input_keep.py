#!/usr/bin/env python3
"""Independent original PROC SORT input KEEP gate for maintainer review.

Hand/base-R qualification runs before new translator comparisons. No live SAS.
"""
from copy import deepcopy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('SASCHI_REPOSITORY_ROOT', str(HERE.parent))).resolve()
sys.path.insert(0, str(ROOT))
ORIGINAL = HERE / 'sort_input_keep_capture.sas'
SOURCE_PIN = '00f74989f17165e942d78b15431145c40d7a71f0b615db62205c585a0cddb13d'
RESULT_PIN = '5dae209fd985e46b9eb3e56657f1c9b28db196aa328eb461910eb6181a213661'
TRACE_PIN = '93cbf22d6e6fcda7e2e1067e182f3df7e8b73096533f100be79bda7e2ee1bc5a'
ACCOUNT_KEYS = ('statements', 'physical_records', 'observations', 'attempts', 'outputs')


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()


def exact(actual, expected):
    if type(expected) is dict:
        assert type(actual) is dict and list(actual) == list(expected), (actual, expected)
        for name in expected: exact(actual[name], expected[name])
    elif type(expected) is list:
        assert type(actual) is list and len(actual) == len(expected), (actual, expected)
        for a, b in zip(actual, expected, strict=True): exact(a, b)
    elif type(expected) in (int, float):
        assert type(actual) in (int, float) and actual == expected, (actual, expected)
    else: assert type(actual) is type(expected) and actual == expected, (actual, expected)


def table(columns, values):
    schema = {name: {'type': 'character' if width else 'number', 'length': width or 8} for name, width in columns}
    return {'schema': schema, 'rows': [{name: str(value).ljust(width) if width else None if value is None else float(value)
                                      for (name, width), value in zip(columns, row, strict=True)} for row in values]}


def original_expected():
    raw = table([('zebra', 3), ('alpha', 0), ('serial', 0), ('discard', 2)],
                [('B', 2, 1, 'X'), ('A', None, 2, 'Y'), ('A', -2, 3, 'Z'), ('A', 2, 4, 'U'),
                 ('A', 2, 5, 'V'), ('a', -1, 6, 'W'), ('', 9, 7, 'M'), ('B', None, 8, 'N')])
    selected = {'schema': {name: deepcopy(raw['schema'][name]) for name in ['zebra', 'alpha', 'serial']},
                'rows': [{name: raw['rows'][i-1][name] for name in ['zebra', 'alpha', 'serial']} for i in [7, 2, 3, 4, 8, 1, 6]]}
    serial_order = {'schema': {name: deepcopy(raw['schema'][name]) for name in ['zebra', 'serial']},
                    'rows': [{name: raw['rows'][i-1][name] for name in ['zebra', 'serial']} for i in [1, 2, 3, 4, 6, 7, 8]]}
    before = ('TITLE: Raw snapshot\nobs zebra alpha serial discard\n'
              '1 "B" 2 1 "X"\n2 "A" . 2 "Y"\n3 "A" -2 3 "Z"\n4 "A" 2 4 "U"\n'
              '5 "A" 2 5 "V"\n6 "a" -1 6 "W"\n7 "" 9 7 "M"\n8 "B" . 8 "N"\n')
    after = ('TITLE: Selected snapshot\nobs zebra alpha serial\n'
             '1 "" 9 7\n2 "A" . 2\n3 "A" -2 3\n4 "A" 2 4\n5 "B" . 8\n6 "B" 2 1\n7 "a" -1 6\n')
    return {'datasets': {'raw': raw, 'selected': selected, 'serial_order': serial_order}, 'log': [],
            'reports': {'print_01.txt': before, 'print_02.txt': after}}


def original_trace():
    events = []
    for attempt in range(1, 10):
        events.append({'kind': 'character_input', 'line': 4, 'attempt': attempt, 'complete': attempt <= 8})
        if attempt <= 8: events.append({'kind': 'character_output', 'line': 4, 'observation': attempt})
    def report_events(title, dataset, name, content, rows):
        records = content.splitlines()
        return ['title|set|' + title.encode().hex(), 'mixed-print|input|' + dataset + '|' + str(rows),
                'mixed-print|title|' + records[0].encode().hex(), 'mixed-print|header|' + records[1].encode().hex(),
                *['mixed-print|row|' + record.encode().hex() for record in records[2:]],
                'mixed-print|output|' + name + '|' + str(len(content.encode()))]
    reports = original_expected()['reports']
    events += report_events('Raw snapshot', 'raw', 'print_01.txt', reports['print_01.txt'], 8)
    events.append({'event': 'sort', 'line': 19, 'source': 'raw', 'destination': 'selected',
                   'source_ordinals': [7, 2, 3, 4, 5, 8, 1, 6], 'kept_ordinals': [7, 2, 3, 4, 8, 1, 6]})
    events += report_events('Selected snapshot', 'selected', 'print_02.txt', reports['print_02.txt'], 7)
    events.append({'event': 'sort', 'line': 25, 'source': 'selected', 'destination': 'serial_order',
                   'source_ordinals': [6, 2, 3, 4, 7, 1, 5], 'kept_ordinals': [6, 2, 3, 4, 7, 1, 5]})
    events.append('title|reset')
    return events


def source(cards, columns='z :$3. n serial q :$2.', keep='serial n z', by='z n', nodupkey=True):
    return ('data raw;\ninfile datalines dsd;\ninput ' + columns + ';\ndatalines4;\n'
            + ''.join(card + '\n' for card in cards) + ';;;;\nrun;\n'
            + 'proc sort data=raw(keep=' + keep + ') out=ordered' + (' nodupkey' if nodupkey else '')
            + ';\nby ' + by + ';\nrun;\n')


def batch_witness(sources):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory); paths = []
        for i, text in enumerate(sources):
            path = folder / f'{i}.sas'; path.write_text(text); paths.append(path)
        listing = folder / 'sources.txt'; listing.write_text(''.join(str(path) + '\n' for path in paths))
        rscript = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        run = subprocess.run([rscript, str(HERE / 'sort_input_keep.R'), str(listing)], cwd=ROOT,
                             env={**os.environ, 'SASCHI_EXAMPLES_ROOT': str(ROOT / 'examples')},
                             text=True, capture_output=True, check=True, timeout=120)
    answers = []; active = None; current = None
    for line in run.stdout.splitlines():
        if line.startswith('BEGIN '):
            assert active is None; active = int(line[6:]); refused = False
            result = {'datasets': {}, 'log': []}; trace = []; accounting = None; reports = {}
        elif line == 'REFUSED': refused = True
        elif line == 'OK': pass
        elif line.startswith('TABLE '): current = {'schema': {}, 'rows': []}; result['datasets'][line[6:]] = current
        elif line.startswith('COL '):
            _, name, kind, width = line.split(); current['schema'][name] = {'type': kind, 'length': int(width)}
        elif line.startswith('ROW '):
            fields = [None if item == 'M' else bytes.fromhex(item[2:]).decode('ascii') if item.startswith('C:') else float(item[2:]) for item in line[4:].split('|')]
            current['rows'].append(dict(zip(current['schema'], fields, strict=True)))
        elif line == 'ENDTABLE': current = None
        elif line.startswith('ACCOUNT '): accounting = dict(zip(ACCOUNT_KEYS, map(int, line[8:].split()), strict=True))
        elif line.startswith('REPORT '):
            _, name, body = line.split(); reports[name] = bytes.fromhex(body).decode('ascii')
        elif line.startswith('EVENT '): trace.append(json.loads(line[6:]))
        elif line == 'END':
            assert active == len(answers) + 1
            if reports: result['reports'] = reports
            answers.append(None if refused else {'result': result, 'trace': trace, 'accounting': accounting}); active = None
        else: raise AssertionError((line, run.stderr))
    assert active is None and len(answers) == len(sources)
    return answers


def expected_case(values, keep, by, nodupkey):
    raw = table([('z', 3), ('n', 0), ('serial', 0), ('q', 2)], values)
    names = [name for name in raw['schema'] if name in keep]
    def key(row):
        return tuple((0, 0) if row[name] is None else (1, row[name].rstrip(' ') if isinstance(row[name], str) else row[name]) for name in by)
    ordered = sorted(raw['rows'], key=key); rows = []; previous = None
    for row in ordered:
        k = key(row)
        if not nodupkey or k != previous: rows.append({name: row[name] for name in names})
        previous = k
    return {'datasets': {'raw': raw, 'ordered': {'schema': {name: deepcopy(raw['schema'][name]) for name in names}, 'rows': rows}}, 'log': []}


def generated_cases(count=64):
    rng = random.Random(7501); cases = []
    for i in range(count):
        values = [(rng.choice(['', 'A', 'B', 'a']), rng.choice([None, -2, -.5, 0, .5, 2]), rng.randrange(5), rng.choice(['X', 'Y', ''])) for _ in range(rng.randrange(24))]
        keep = ['serial', 'n', 'z'] if i % 2 else ['serial', 'z']
        by = ['z', 'n'] if 'n' in keep else ['z']; nodup = i % 3 != 0
        cards = [','.join('.' if value is None else str(value) for value in row) for row in values]
        text = source(cards, keep=' '.join(keep), by=' '.join(by), nodupkey=nodup)
        cases.append((text, expected_case(values, keep, by, nodup)))
    return cases


def boundary_cases():
    full = source([])
    for i in range(62): full += f'proc sort data=raw(keep=z) out=s{i};by z;run;\n'
    return [source([]), source(['A,1,2,X'] * 1000),
            source(['A,-2147483647,1,X', 'B,2147483647,2,Y', ',.,3,Z']),
            source(['Z' * 64 + ',1'], 'z :$64. n', keep='n z', by='z', nodupkey=False),
            source([], 'z :$1. ' + ' '.join('n'+str(i) for i in range(31)),
                   keep=' '.join('n'+str(i) for i in reversed(range(31))) + ' z', by='z'),
            source([], 'z :$1. ' + ' '.join('n'+str(i) for i in range(7)),
                   keep='z ' + ' '.join('n'+str(i) for i in range(7)), by='z ' + ' '.join('n'+str(i) for i in range(7))), full,
            source(['A,1,2,X']).replace('\n', '\r\n')]


def refusal_cases():
    base = source([]); result = []
    for label, keep, by in [('removed-key', 'z serial', 'n'), ('unknown-keep', 'z absent', 'z'),
                           ('duplicate-keep', 'z z', 'z'), ('numeric-only', 'n serial', 'n'),
                           ('empty-keep', '', 'z'), ('unknown-by', 'z', 'absent'), ('duplicate-by', 'z n', 'z z'),
                           ('descending', 'z n', 'descending n'), ('special-by', 'z n', '_all_'),
                           ('range-keep', 'z n1-n2', 'z'), ('special-keep', '_all_', 'z')]:
        result.append((label, source([], keep=keep, by=by)))
    for label, before, after in [('drop-option', '(keep=serial n z)', '(drop=q)'), ('output-option', 'out=ordered', 'out=ordered(keep=z)'),
                                 ('in-place', ' out=ordered', ''), ('collision', 'out=ordered', 'out=raw'),
                                 ('unknown-option', 'out=ordered', 'out=ordered force')]:
        result.append((label, base.replace(before, after)))
    result += [('no-run', base.rsplit('run;', 1)[0]), ('extra-statement', base.replace('by z n;', 'by z n;where n=1;')),
               ('excluded-inexact', source(['A,0.1,2,X'], keep='z serial', by='z')),
               ('excluded-nonascii', source(['A,1,2,é'], keep='z serial', by='z')),
               ('excluded-tagged', source(['A,.A,2,X'], keep='z serial', by='z')),
               ('rows1001', source(['A,1,2,X'] * 1001)), ('invalid-empty-descriptor', source([], 'z :$3. n serial q :$65.')),
               ('step65', boundary_cases()[6] + 'proc sort data=raw(keep=z) out=too_many;by z;run;\n')]
    cols = 'z :$1. ' + ' '.join('n'+str(i) for i in range(8))
    result.append(('by9', source([], cols, keep='z ' + ' '.join('n'+str(i) for i in range(8)), by='z ' + ' '.join('n'+str(i) for i in range(8)))))
    return result


def qualify():
    text = ORIGINAL.read_text(); truth = original_expected(); trace = original_trace()
    if SOURCE_PIN: assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == SOURCE_PIN
    if RESULT_PIN: assert digest(truth) == RESULT_PIN
    if TRACE_PIN: assert digest(trace) == TRACE_PIN
    generated = generated_cases(); boundaries = boundary_cases(); refused = refusal_cases()
    sources = [text] + [t for t, _ in generated] + boundaries + [t for _, t in refused]
    independent = batch_witness(sources); exact(independent[0]['result'], truth); exact(independent[0]['trace'], trace)
    assert independent[0]['accounting'] == dict(zip(ACCOUNT_KEYS, [18, 8, 8, 9, 8], strict=True))
    for i, (_, expected) in enumerate(generated, 1): exact(independent[i]['result'], expected)
    assert all(item is not None for item in independent[1+len(generated):1+len(generated)+len(boundaries)])
    for (label, _), item in zip(refused, independent[1+len(generated)+len(boundaries):], strict=True): assert item is None, label
    return {'original': text, 'truth': truth, 'trace': trace, 'generated': generated, 'boundaries': boundaries,
            'refused': refused, 'independent': independent, 'sources': sources}


def execute(text):
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    from saschi.emit_py import translate
    from saschi.sort_projection import run_program
    plan = compile_plan(text); assert not plan.blocked, plan.tickets
    portable = plan.to_dict(); before = deepcopy(portable); trace = []
    result = run_plan(portable); exact(portable, before); exact(run_program(portable, trace=trace), result)
    namespace = {}; output = io.StringIO()
    with contextlib.redirect_stdout(output): exec(translate(text).code, namespace)
    exact(namespace['result'], result); assert output.getvalue() == ''
    return result, trace


def cli_check(text, truth, wrong=False):
    from saschi.cli import main
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory); src = folder / 'input.sas'; src.write_text(text)
        expected = folder / 'expected.json'; expected.write_text(json.dumps(truth['datasets']))
        reports = folder / 'reports.json'; reports.write_text(json.dumps(truth.get('reports', {})))
        output = folder / 'job'; console = io.StringIO()
        argv = ['run', str(src), '--expect', str(expected), '--output', str(output)]
        if 'reports' in truth: argv += ['--expect-reports', str(reports)]
        with contextlib.redirect_stdout(console): code = main(argv)
        receipt = json.loads((output / 'receipt.json').read_text()); assert code == (1 if wrong else 0), (code, receipt.get('error'))
        assert receipt['accepted'] is (not wrong) and receipt['source_sha256'] == hashlib.sha256(src.read_bytes()).hexdigest()
        assert not (output / 'exports').exists()
        if wrong: assert not (output / 'result.json').exists() and (output / 'observed.json').is_file() and not (output / 'reports').exists()
        else:
            exact(json.loads((output / 'result.json').read_text()), truth)
            if 'reports' in truth:
                assert sorted(p.name for p in (output / 'reports').iterdir()) == sorted(truth['reports'])
                for name, body in truth['reports'].items(): assert (output / 'reports' / name).read_bytes() == body.encode()


def wrong_cases(truth):
    result = []
    for mode in ['descriptor-order', 'padding', 'last-survivor', 'ignored-keep', 'report', 'basename', 'newline']:
        wrong = deepcopy(truth); t = wrong['datasets']['selected']
        if mode == 'descriptor-order': t['schema'] = dict(reversed(list(t['schema'].items())))
        elif mode == 'padding': t['rows'][0]['zebra'] = ''
        elif mode == 'last-survivor': t['rows'][3]['serial'] = 5.
        elif mode == 'ignored-keep':
            t['schema']['discard'] = {'type': 'character', 'length': 2}
            for row in t['rows']: row['discard'] = 'X '
        elif mode == 'report': wrong['reports']['print_02.txt'] += 'extra\n'
        elif mode == 'basename': wrong['reports']['other.txt'] = wrong['reports'].pop('print_02.txt')
        else: wrong['reports']['print_02.txt'] = wrong['reports']['print_02.txt'].removesuffix('\n')
        result.append(wrong)
    return result


def portable_refusals():
    from saschi.plan import compile_plan
    from saschi.sort_projection import execute_sort, run_program
    plan = compile_plan(source([])).to_dict(); step = next(x for x in plan['steps'] if x['kind'] == 'projected_sort')
    empty = table([('z', 3), ('n', 0), ('serial', 0), ('q', 2)], [])
    count = 0
    def rejected(s=step, t=empty, version=2):
        nonlocal count
        before = json.dumps(t, separators=(',', ':'))
        try: execute_sort(s, {'raw': t}, version=version)
        except (ValueError, TypeError, KeyError, RecursionError): pass
        else: raise AssertionError(s)
        assert json.dumps(t, separators=(',', ':')) == before; count += 1
    for name, value in [('by', ['z']), ('nodupkey', True), ('line', True), ('inputs', []), ('name', 'raw'), ('extra', 1)]:
        s = deepcopy(step); s[name] = value; rejected(s)
    for name, value in [('keep', ['z', 'z']), ('keep', ['z', 'absent']), ('keep', ['n']), ('keep', []), ('by', ['q']),
                        ('by', ['z', 'z']), ('by', []), ('by', ['descending', 'z']), ('nodupkey', 1),
                        ('source_lines', []), ('profile', 'old-sort'), ('extra', 1)]:
        s = deepcopy(step); s['operations'][0]['args'][name] = value; rejected(s)
    rejected(version=True)
    for value in [True, float('nan'), '.A', 2147483648, .1]:
        t = deepcopy(empty); t['rows'] = [{'z': 'A  ', 'n': value, 'serial': 1., 'q': 'X '}]
        s = deepcopy(step); s['operations'][0]['args'].update(keep=['z', 'serial'], by=['z']); rejected(s, t)
    t = deepcopy(empty); t['schema']['q']['length'] = True; rejected(t=t)
    t = deepcopy(empty); t['rows'] = [{'z': 'A  ', 'n': 1., 'serial': 1., 'q': 'é '}]; rejected(t=t)
    s = deepcopy(step); s['operations'][0]['args']['keep'] = tuple(['z']); rejected(s)
    try: run_program(plan, {'external': empty})
    except (ValueError, TypeError, KeyError): count += 1
    else: raise AssertionError('external catalog admitted')
    return count


def atomic_check(text):
    from saschi import sort_projection, mixed_reports
    from saschi.cli import main
    real = sort_projection.execute_sort; printed = mixed_reports.execute_print; calls = []; reports = []
    def later(step, tables, version=2, *, trace=None):
        result = real(step, tables, version, trace=trace); calls.append(step['name'])
        if len(calls) == 2: raise ValueError('KEEP second-SORT late runtime fault')
        return result
    def observed(*args, **kwargs):
        result = printed(*args, **kwargs); reports.append(deepcopy(result)); return result
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'original.sas'; path.write_text(text); output = Path(directory) / 'job'; console = io.StringIO()
        with patch.object(sort_projection, 'execute_sort', later), patch.object(mixed_reports, 'execute_print', observed), contextlib.redirect_stdout(console):
            code = main(['run', str(path), '--output', str(output)])
        receipt = json.loads((output / 'receipt.json').read_text())
        assert code == 1 and receipt['accepted'] is False and receipt['error'] == 'KEEP second-SORT late runtime fault'
        assert len(calls) == 2 and len(reports) == 2 and all(reports)
        assert not any((output / name).exists() for name in ['result.json', 'observed.json', 'reports', 'exports'])
        assert not list(Path(directory).glob('.job.*'))
    return 1


def run():
    qualified = qualify(); npositive = 1 + len(qualified['generated']) + len(qualified['boundaries'])
    for text, witness in zip(qualified['sources'][:npositive], qualified['independent'][:npositive], strict=True):
        result, trace = execute(text); exact(result, witness['result']); exact(trace, witness['trace'])
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    boundary_admissions = 0
    for label, text in qualified['refused']:
        plan = compile_plan(text)
        if label in ('descending', 'drop-option'):
            from saschi.parser import split_statements
            from saschi.formatted_program import _blocks
            from saschi.sort_projection import parse_sort
            block = list(_blocks(split_statements(text)))[1][2]
            try: parse_sort(block)
            except ValueError: pass
            else: raise AssertionError('old KEEP profile broadened: ' + label)
            assert not plan.blocked and [step.kind for step in plan.steps] == ['character_data', 'composed_sort']
            args = plan.steps[1].operations[0].args
            assert args['profile'] == 'sort-projection-composition-v1'
            names = ['z', 'n'] if label == 'descending' else ['z', 'n', 'serial']
            assert args['selection'] == ({'mode': 'keep', 'names': ['z', 'n']} if label == 'descending'
                                         else {'mode': 'drop', 'names': ['q']})
            assert args['keys'] == ([{'name': 'n', 'descending': True}] if label == 'descending'
                                   else [{'name': 'z', 'descending': False}, {'name': 'n', 'descending': False}])
            exact(run_plan(plan.to_dict()), expected_case([], names, [], False))
            boundary_admissions += 1
        elif not plan.blocked:
            try: run_plan(plan.to_dict())
            except (ValueError, TypeError, KeyError, RecursionError): pass
            else: raise AssertionError(label)
    assert boundary_admissions == 2
    truth = qualified['truth']; cli_check(qualified['original'], truth)
    for incorrect in wrong_cases(truth): cli_check(qualified['original'], incorrect, True)
    portable = portable_refusals(); atomic = atomic_check(qualified['original'])
    summary = {'original_language_statements': 18, 'original_rows': 8, 'original_input_attempts': 9, 'original_trace_events': len(qualified['trace']),
               'generated_programs': len(qualified['generated']), 'positive_boundaries': len(qualified['boundaries']),
               'old_profile_refusals': len(qualified['refused']),
               'whole_compiler_refusals': len(qualified['refused']) - boundary_admissions,
               'new_profile_boundary_admissions': boundary_admissions, 'portable_refusals': portable,
               'actual_wrong_cli_comparators': len(wrong_cases(truth)), 'actual_late_runtime_cli_faults': atomic}
    print('sort-input-keep: ' + json.dumps(summary, sort_keys=True)); return summary


if __name__ == '__main__': run()
