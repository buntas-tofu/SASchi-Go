#!/usr/bin/env python3
"""Original directed/descriptor SORT gates with independent source-reading R.

Repository/base-R evidence for maintainers. No live SAS or native host-sort claim.
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
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from examples.verify_character_input import assert_exact, cli_check
from saschi.emit_py import translate
from saschi.plan import compile_plan
from saschi.runtime import run_plan

SOURCE_PINS = {'descending': 'ca6a3da8ab49079bcbef7cf1d9aab30159768021dc11cad448d2466bed021a49',
               'all': '7640929dbced0900c5976f061f2ff49f22cd234b42659eb7430f8e0c95760e81'}
RESULT_PINS = {'descending': 'cdd598fa98560d6c84223ffd54a8f03e1438a913c77bdad5c74647ba70cd6685',
               'all': 'd6fb11aa2a6933f7c4b129d51d73c0713f463e7f438dc50d4a15aca4d4dcb2fe'}
TRACE_PINS = {'descending': '81e2494754ebaf95b18ca90ec22e2bd073dc1ed4507855685701b0b25ff3b423',
              'all': '7345a5390a03cfb9ccee4a72ff440f5f7d5da1a286258a01bbbbc4429cff02e8'}
ACCOUNT_KEYS = ('statements', 'physical_records', 'observations', 'attempts', 'outputs')


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()


def source(records, columns='z :$3. a payload', by='z descending a', *, nodupkey=False, name='raw', output='ordered'):
    return (f'data {name};\ninfile datalines dsd;\ninput {columns};\ndatalines4;\n'
            + ''.join(row + '\n' for row in records) + ';;;;\nrun;\n'
            + f'proc sort data={name} out={output}' + (' nodupkey' if nodupkey else '')
            + f';\nby {by};\nrun;\n')


def rows_table(names, values):
    schema = {name: {'type': 'character', 'length': width} if width else {'type': 'number', 'length': 8}
              for name, width in names}
    rows = [{name: str(value).ljust(width) if width else None if value is None else float(value)
             for (name, width), value in zip(names, row, strict=True)} for row in values]
    return {'schema': schema, 'rows': rows}


def original_expected(mode):
    if mode == 'descending':
        table = rows_table([('zone', 3), ('value', 0), ('serial', 0)],
                           [('B', 2, 1), ('A', None, 2), ('A', -2, 3), ('A', 2, 4),
                            ('A', 2, 5), ('a', -.5, 6), ('', 9, 7), ('B', None, 8)])
        ranked = {'schema': deepcopy(table['schema']), 'rows': [deepcopy(table['rows'][i-1]) for i in (7, 4, 5, 3, 2, 1, 8, 6)]}
        survivors = {'schema': deepcopy(table['schema']), 'rows': [deepcopy(table['rows'][i-1]) for i in (6, 8, 1, 2, 3, 4, 7)]}
        return {'datasets': {'intake': table, 'ranked': ranked, 'survivors': survivors}, 'log': []}
    values = [('B', 1, 'z'), ('A', 2, 'y'), ('A', 1, 'x'), ('A', 1, 'x'),
              ('', None, 'm'), ('a', -1, 'n'), ('B', None, 'w')]
    first = rows_table([('zebra', 3), ('alpha', 0), ('middle', 3)], values)
    second = rows_table([('alpha', 0), ('zebra', 3), ('middle', 3)], [(b, a, c) for a, b, c in values])
    unique1 = {'schema': deepcopy(first['schema']), 'rows': [deepcopy(first['rows'][i-1]) for i in (5, 3, 2, 7, 1, 6)]}
    unique2 = {'schema': deepcopy(second['schema']), 'rows': [deepcopy(second['rows'][i-1]) for i in (5, 7, 6, 3, 1, 2)]}
    return {'datasets': {'first': first, 'first_unique': unique1, 'second': second, 'second_unique': unique2}, 'log': []}


def original_sorts(mode):
    if mode == 'descending':
        return [dict(event='sort', line=16, source='intake', destination='ranked',
                     source_ordinals=[7, 4, 5, 3, 2, 1, 8, 6], kept_ordinals=[7, 4, 5, 3, 2, 1, 8, 6]),
                dict(event='sort', line=19, source='ranked', destination='survivors',
                     source_ordinals=[8, 7, 6, 5, 4, 2, 3, 1], kept_ordinals=[8, 7, 6, 5, 4, 2, 1])]
    return [dict(event='sort', line=15, source='first', destination='first_unique',
                 source_ordinals=[5, 3, 4, 2, 7, 1, 6], kept_ordinals=[5, 3, 2, 7, 1, 6]),
            dict(event='sort', line=31, source='second', destination='second_unique',
                 source_ordinals=[5, 7, 6, 3, 4, 1, 2], kept_ordinals=[5, 7, 6, 3, 1, 2])]


def original_trace(mode):
    events = []
    sections = [(4, 8)] if mode == 'descending' else [(4, 7), (20, 7)]
    sorts = original_sorts(mode)
    for section, (line, count) in enumerate(sections):
        for attempt in range(1, count + 2):
            complete = attempt <= count
            events.append({'kind': 'character_input', 'line': line, 'attempt': attempt, 'complete': complete})
            if complete: events.append({'kind': 'character_output', 'line': line, 'observation': attempt})
        events.extend(sorts if mode == 'descending' else [sorts[section]])
    return events


def batch_witness(texts):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory); paths = []
        for index, text in enumerate(texts):
            path = folder / f'{index}.sas'; path.write_text(text); paths.append(path)
        listing = folder / 'sources.txt'; listing.write_text(''.join(str(path) + '\n' for path in paths))
        rscript = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        process = subprocess.run([rscript, str(HERE / 'sort_options.R'), str(listing)], capture_output=True,
                                 text=True, cwd=ROOT, check=True, timeout=120)
    answers = []; current = table = result = None
    for line in process.stdout.splitlines():
        if line.startswith('BEGIN '):
            assert current is None
            current = int(line[6:]); result = {'datasets': {}, 'log': []}; refused = False; sorts = []; account = None
        elif line == 'REFUSED': refused = True
        elif line == 'OK': pass
        elif line.startswith('TABLE '):
            table = {'schema': {}, 'rows': []}; result['datasets'][line[6:]] = table
        elif line.startswith('COL '):
            _, name, kind, width = line.split(); table['schema'][name] = {'type': kind, 'length': int(width)}
        elif line.startswith('ROW '):
            values = [None if item == 'M' else bytes.fromhex(item[2:]).decode('ascii')
                      if item.startswith('C:') else float(item[2:]) for item in line[4:].split('|')]
            table['rows'].append(dict(zip(table['schema'], values, strict=True)))
        elif line == 'ENDTABLE': table = None
        elif line.startswith('ACCOUNT '): account = dict(zip(ACCOUNT_KEYS, map(int, line[8:].split()), strict=True))
        elif line.startswith('SORT '):
            _, number, src, dest, ordered, kept = line.split()
            sorts.append(dict(event='sort', line=int(number), source=src, destination=dest,
                              source_ordinals=[] if ordered == '-' else list(map(int, ordered.split(','))),
                              kept_ordinals=[] if kept == '-' else list(map(int, kept.split(',')))))
        elif line == 'END':
            assert current == len(answers) + 1
            answers.append(None if refused else {'result': result, 'sorts': sorts, 'accounting': account}); current = None
        else: raise AssertionError((line, process.stderr))
    assert current is None and len(answers) == len(texts), process.stdout
    return answers


def execute(text, *, emitted=True):
    from saschi.sort_options import run_program
    plan = compile_plan(text); assert not plan.blocked, plan.tickets
    portable = plan.to_dict(); saved = deepcopy(portable); trace = []
    result = run_plan(portable); assert_exact(portable, saved)
    assert_exact(run_program(portable, trace=trace), result)
    if emitted:
        namespace = {}; output = io.StringIO()
        with contextlib.redirect_stdout(output): exec(translate(text).code, namespace)
        assert_exact(namespace['result'], result); assert output.getvalue() == ''
    return result, [event for event in trace if isinstance(event, dict) and event.get('event') == 'sort']


def independently_order(table, keys, descending, nodupkey):
    # Tuple ranking is separate from the independent R pairwise insertion oracle.
    ranks = {}
    for name in keys:
        values = {row[name] for row in table['rows']}
        values = sorted(values, key=lambda value: (value is not None, value if value is not None else 0))
        ranks[name] = {value: rank for rank, value in enumerate(values)}
    def key(row):
        return tuple((-1 if direction else 1) * ranks[name][row[name]] for name, direction in zip(keys, descending, strict=True))
    ordered = sorted(table['rows'], key=key); retained = []; previous = None
    for row in ordered:
        current = key(row)
        if not nodupkey or current != previous: retained.append(deepcopy(row))
        previous = current
    return {'schema': deepcopy(table['schema']), 'rows': retained}


def generated_cases(mode, count=64):
    rng = random.Random(7481 if mode == 'descending' else 7482); cases = []
    for index in range(count):
        values = [(rng.choice(['', 'A', 'B', 'a', 'a b']), rng.choice([None, -2, -.5, 0, .5, 2]), rng.randrange(5))
                  for _ in range(rng.randrange(24))]
        # Every ninth case tests a nonalphabetical numeric-first descriptor order.
        permuted = mode == 'all' and index % 9 == 0
        names = [('a', 0), ('z', 3), ('payload', 0)] if permuted else [('z', 3), ('a', 0), ('payload', 0)]
        ordered_values = [(b, a, c) for a, b, c in values] if permuted else values
        table = rows_table(names, ordered_values)
        cards = [','.join('.' if value is None else str(value) for value in row) for row in ordered_values]
        columns = 'a z :$3. payload' if permuted else 'z :$3. a payload'
        if mode == 'all': by = '_all_'; keys = list(table['schema']); directions = [False] * len(keys); nodup = True
        else:
            keys = ['z', 'a'] if index % 2 == 0 else ['a', 'z']
            directions = [index % 3 == 0, True]; nodup = index % 4 == 0
            by = ' '.join(('descending ' if direction else '') + name for name, direction in zip(keys, directions, strict=True))
        text = source(cards, columns, by, nodupkey=nodup)
        truth = {'datasets': {'raw': table, 'ordered': independently_order(table, keys, directions, nodup)}, 'log': []}
        cases.append((text, truth))
    return cases


def boundary_cases(mode):
    by = '_all_' if mode == 'all' else 'descending z a'; nodup = mode == 'all'
    full_steps = source([], by=by, nodupkey=nodup)
    for index in range(62):
        full_steps += f'proc sort data=raw out=s{index}' + (' nodupkey' if nodup else '') + f';by {by};run;\n'
    cases = [source([], by=by, nodupkey=nodup),
            source(['A,1,2'] * 1000, by=by, nodupkey=nodup),
            source(['A,-2147483647,1', 'B,2147483647,2', ',.,3'], by=by, nodupkey=nodup),
            source(['A' * 64 + ',1'], 'z :$64. a', by=by, nodupkey=nodup),
            source([], 'z :$1. ' + ' '.join('n' + str(i) for i in range(31)),
                   by='_all_' if mode == 'all' else 'descending z', nodupkey=nodup),
            source(['A,1,2'], by=by, nodupkey=nodup).replace('\n', '\r\n'), full_steps]
    if mode == 'descending':
        cases.append(source([], 'z :$1. ' + ' '.join('n' + str(i) for i in range(7)),
                            by='descending z ' + ' '.join('n' + str(i) for i in range(7))))
    return cases


def refusal_cases(mode):
    by = '_all_' if mode == 'all' else 'z descending a'; nodup = mode == 'all'
    base = source([], by=by, nodupkey=nodup)
    cases = [('missing-key', base.replace('by ' + by, 'by descending absent' if mode == 'descending' else 'by absent _all_')),
             ('duplicate-key', base.replace('by ' + by, 'by z descending z')),
             ('dangling-direction', base.replace('by ' + by, 'by z descending')),
             ('double-direction', base.replace('by ' + by, 'by descending descending z')),
             ('notsorted', base.replace('by ' + by, 'by z notsorted')),
             ('mixed-all', base.replace('by ' + by, 'by z _all_')),
             ('descending-all', base.replace('by ' + by, 'by descending _all_')),
             ('absent-run', base.rsplit('run;', 1)[0]),
             ('inplace', base.replace(' out=ordered', '')),
             ('same-destination', base.replace('out=ordered', 'out=raw')),
             ('unknown-option', base.replace('out=ordered', 'out=ordered force')),
             ('empty-by', base.replace('by ' + by, 'by')),
             ('extra-clause', base.replace('by ' + by + ';', 'by ' + by + ';where a=1;')),
             ('record-limit', source(['A,1,2'] * 1001, by=by, nodupkey=nodup)),
             ('tagged-missing', source(['A,.A,2'], by=by, nodupkey=nodup)),
             ('inexact-input', source(['A,0.1,2'], by=by, nodupkey=nodup)),
             ('nonascii', source(['é,1,2'], by=by, nodupkey=nodup)),
             ('schema-width', source([], 'z :$65. a payload', by=by, nodupkey=nodup))]
    cases.append(('65-steps', boundary_cases(mode)[6] + f'proc sort data=raw out=excess' + (' nodupkey' if nodup else '') + f';by {by};run;\n'))
    if mode == 'all': cases.append(('all-without-nodup', base.replace(' nodupkey;', ';')))
    else:
        columns = 'z :$1. ' + ' '.join('n' + str(i) for i in range(8))
        cases.append(('nine-keys', source([], columns, by='descending z ' + ' '.join('n' + str(i) for i in range(8)))))
    return cases


def refuses(text):
    try:
        plan = compile_plan(text)
        if plan.blocked: return
        run_plan(plan.to_dict())
    except (ValueError, TypeError, KeyError, RecursionError): return
    raise AssertionError('unexpected admission: ' + text)


def portable_refusals(mode):
    from saschi.sort_options import execute_sort, run_program
    by = '_all_' if mode == 'all' else 'z descending a'
    plan = compile_plan(source([], by=by, nodupkey=mode == 'all')).to_dict()
    step = next(step for step in plan['steps'] if step['kind'] == 'bounded_sort')
    empty = rows_table([('z', 3), ('a', 0), ('payload', 0)], [])
    def reject(step_value, table=empty, version=2):
        before = json.dumps(table, separators=(',', ':'))
        try: execute_sort(step_value, {'raw': table}, version=version)
        except (ValueError, TypeError, KeyError, RecursionError): pass
        else: raise AssertionError(step_value)
        assert json.dumps(table, separators=(',', ':')) == before
    mutations = []
    for name, value in [('extra', 1), ('by', ['z']), ('nodupkey', True), ('line', True), ('where', {}), ('inputs', []), ('name', 'raw')]:
        damaged = deepcopy(step); damaged[name] = value; mutations.append(damaged)
    for name, value in [('extra', 1), ('profile', 'unknown-sort'), ('nodupkey', 1), ('source_lines', []), ('keys', ())]:
        damaged = deepcopy(step); damaged['operations'][0]['args'][name] = value; mutations.append(damaged)
    for bad in mutations: reject(bad)
    reject(step, version=True)
    for change in [('bad-length', lambda t: t['schema']['z'].update(length=True)),
                   ('too-many-columns', lambda t: t['schema'].update({f'c{i}': {'type': 'number', 'length': 8} for i in range(30)}))]:
        table = deepcopy(empty); change[1](table)
        reject(step, table)
    for value in ('.A', float('nan'), True, 2147483648):
        table = deepcopy(empty); table['rows'] = [{'z': 'A  ', 'a': value, 'payload': 1.}]; reject(step, table)
    table = deepcopy(empty); table['rows'] = [{'z': 'é  ', 'a': 1., 'payload': 1.}]; reject(step, table)
    try: run_program(plan, {'external': empty})
    except (ValueError, TypeError, KeyError): pass
    else: raise AssertionError('initial catalog accepted')
    return len(mutations) + 9


def wrong_cases(mode, truth):
    result = []
    for damage in ('order', 'descriptor', 'padding', 'dataset-set'):
        wrong = deepcopy(truth); target = wrong['datasets']['ranked' if mode == 'descending' else 'first_unique']
        if damage == 'order': target['rows'].reverse()
        elif damage == 'descriptor': next(iter(target['schema'].values()))['length'] = 2
        elif damage == 'padding': target['rows'][0]['zone' if mode == 'descending' else 'zebra'] = ''
        else: wrong['datasets']['extra'] = deepcopy(target)
        result.append(wrong)
    return result


def atomic_checks(mode, text):
    from saschi import sort_options
    from saschi.job import build_job
    real = sort_options.execute_sort; real_program = sort_options.run_program; calls = []
    def fail_late(step, tables, version=2, *, trace=None):
        answer = real(step, tables, version, trace=trace)
        if trace is not None:
            calls.append(step['name'])
            if len(calls) == 2: raise ValueError('original component late-sort atomicity witness')
        return answer
    def traced_program(plan, catalog=None, *, trace=None):
        return real_program(plan, catalog, trace=[] if trace is None else trace)
    with patch.object(sort_options, 'execute_sort', fail_late), patch.object(sort_options, 'run_program', traced_program):
        job = build_job(text)
    assert len(calls) == 2 and job.code == 1 and job.result is None and not job.receipt['accepted'], (calls, job.code)
    late = text + 'data late;infile datalines dsd;input z :$1. n;datalines4;\nA,0.1\n;;;;\nrun;\n'
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'late.sas'; path.write_text(late); out = Path(directory) / 'job'
        process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'run', str(path), '--output', str(out)],
                                 cwd=ROOT, capture_output=True, text=True, timeout=45)
        receipt = json.loads((out / 'receipt.json').read_text())
        assert process.returncode == 2 and not receipt['accepted'], (process.stdout, process.stderr, receipt)
        assert not any((out / name).exists() for name in ('result.json', 'observed.json', 'reports', 'exports'))
    # This valid source reaches a real second SORT after computing a first SORT
    # and a report. The actual CLI publication path must discard every buffer.
    from saschi.cli import main as cli_main
    insertion = ('title "Atomic report buffer";\nproc print data='
                 + ('ranked' if mode == 'descending' else 'first_unique') + ';run;\n')
    marker = 'proc sort data=ranked' if mode == 'descending' else 'data second;'
    with_report = text.replace(marker, insertion + marker, 1)
    if mode == 'descending':
        with_report = with_report.replace('a,-.5,6', 'a,-1,6')
    assert not compile_plan(with_report).blocked
    from saschi import mixed_reports
    calls.clear(); reports = []; real_print = mixed_reports.execute_print
    def observed_print(*args, **kwargs):
        answer = real_print(*args, **kwargs); reports.append(deepcopy(answer)); return answer
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'runtime-late.sas'; path.write_text(with_report)
        out = Path(directory) / 'job'; console = io.StringIO()
        with patch.object(sort_options, 'execute_sort', fail_late), \
             patch.object(sort_options, 'run_program', traced_program), \
             patch.object(mixed_reports, 'execute_print', observed_print), contextlib.redirect_stdout(console):
            code = cli_main(['run', str(path), '--output', str(out)])
        receipt = json.loads((out / 'receipt.json').read_text())
        assert code == 1 and receipt['accepted'] is False and len(calls) == 2, (code, calls, receipt.get('error'), reports)
        assert receipt['error'] == 'original component late-sort atomicity witness'
        assert len(reports) == 1 and set(reports[0]) == {'print_01.txt'} and reports[0]['print_01.txt']
        assert receipt['source_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert not any((out / name).exists() for name in ('result.json', 'observed.json', 'reports', 'exports'))
        assert not list(Path(directory).glob('.job.*'))
    return 3


def run(mode='descending'):
    original = HERE / ('sort_descending_capture.sas' if mode == 'descending' else 'sort_all_capture.sas')
    text = original.read_text(); truth = original_expected(mode)
    assert hashlib.sha256(original.read_bytes()).hexdigest() == SOURCE_PINS[mode]
    assert digest(truth) == RESULT_PINS[mode]
    assert digest(original_trace(mode)) == TRACE_PINS[mode]
    generated = generated_cases(mode); boundaries = boundary_cases(mode); refused = refusal_cases(mode)
    texts = [text] + [item[0] for item in generated] + boundaries + [item[1] for item in refused]
    independent = batch_witness(texts)
    assert_exact(independent[0]['result'], truth); assert_exact(independent[0]['sorts'], original_sorts(mode))
    expected_account = dict(zip(ACCOUNT_KEYS, (11, 8, 8, 9, 8) if mode == 'descending' else (16, 14, 14, 16, 14), strict=True))
    assert independent[0]['accounting'] == expected_account
    from saschi.sort_options import run_program
    trace = []; assert_exact(run_program(compile_plan(text).to_dict(), trace=trace), truth)
    assert_exact(trace, original_trace(mode))
    for index, source_text in enumerate(texts[:1 + len(generated) + len(boundaries)]):
        witness = independent[index]; assert witness is not None, (index, source_text)
        observed, sorts = execute(source_text)
        assert_exact(observed, witness['result']); assert_exact(sorts, witness['sorts'])
        if 1 <= index <= len(generated): assert_exact(observed, generated[index-1][1])
    for index, (name, source_text) in enumerate(refused, 1 + len(generated) + len(boundaries)):
        assert independent[index] is None, (name, independent[index]); refuses(source_text)
    # Explicit known-wrong models: full-list reversal changes ascending primary
    # keys; last-survivor breaks equal-key payload identity; alphabetical ALL
    # expansion breaks the deliberately nonalphabetical descriptor witness.
    if mode == 'descending':
        raw = truth['datasets']['intake']
        globally_reversed = independently_order(raw, ['zone', 'value'], [False, False], False)
        globally_reversed['rows'].reverse()
        assert truth['datasets']['ranked'] != globally_reversed
        reverse_wrong = deepcopy(truth); reverse_wrong['datasets']['ranked'] = globally_reversed
        assert truth['datasets']['survivors']['rows'][-2]['serial'] == 4.
        wrong = deepcopy(truth); wrong['datasets']['survivors']['rows'][-2]['serial'] = 5.
    else:
        table = truth['datasets']['first']; alphabetic = independently_order(table, sorted(table['schema']), [False]*3, True)
        assert alphabetic != truth['datasets']['first_unique']; wrong = deepcopy(truth); wrong['datasets']['first_unique'] = alphabetic
    cli_check(text, truth)
    incorrect_models = wrong_cases(mode, truth) + [wrong] + ([reverse_wrong] if mode == 'descending' else [])
    for incorrect in incorrect_models: cli_check(text, incorrect, True)
    portability = portable_refusals(mode); atomic = atomic_checks(mode, text)
    summary = {'generated_programs': len(generated), 'positive_boundaries': len(boundaries), 'shared_refusals': len(refused),
               'portable_refusals': portability, 'wrong_cli_comparators': len(incorrect_models), 'atomic_controls': atomic,
               'original_accounting': expected_account, 'sort_events': len(original_sorts(mode)),
               'original_trace_events': len(original_trace(mode))}
    print('sort-' + mode + ': ' + json.dumps(summary, sort_keys=True)); return summary


if __name__ == '__main__': run()
