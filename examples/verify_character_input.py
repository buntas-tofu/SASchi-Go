#!/usr/bin/env python3
"""DS-069 whole-source character records, exact padding and physical boundaries.

Repository/base-R evidence only. No live SAS or general CSV claim.
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from saschi.character_input import compile_program, execute_step
from saschi.emit_py import translate
from saschi.plan import compile_plan
from saschi.runtime import run_plan

ORIGINAL = HERE / 'character_input_capture.sas'
SOURCE_PIN = '195afb32da6e40f09e1ebed2b446591629be0fd5494241922060587e5f3eb299'
RESULT_PIN = 'f040ad43801bf1bbc34e6dea9353f7c85785734c14f2de3ddeedf1190d69dd13'
ACCOUNT_KEYS = ('statements', 'physical_records', 'observations', 'attempts', 'outputs')


def assert_exact(actual, expected):
    if type(expected) is dict:
        assert type(actual) is dict and list(actual) == list(expected), (actual, expected)
        for key in expected:
            assert_exact(actual[key], expected[key])
    elif type(expected) is list:
        assert type(actual) is list and len(actual) == len(expected), (actual, expected)
        for left, right in zip(actual, expected):
            assert_exact(left, right)
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        assert not isinstance(actual, bool) and isinstance(actual, (int, float)) and actual == expected, (actual, expected)
    else:
        assert type(actual) is type(expected) and actual == expected, (actual, expected)


def source(records, columns='a :$4. n', name='d', sort=False):
    text = f'data {name};\ninfile datalines dsd;\ninput {columns};\ndatalines4;\n'
    text += ''.join(record + '\n' for record in records) + ';;;;\nrun;\n'
    if sort:
        text += f'proc sort data={name} out=ordered;by a;run;\n'
    return text


def table(schema, rows):
    return {'schema': schema, 'rows': rows}


def expected(schema, values, name='d'):
    return {'datasets': {name: table(schema, [dict(zip(schema, row)) for row in values])}, 'log': []}


def original_expected():
    schema = {'person': {'type': 'character', 'length': 8},
              'topic': {'type': 'character', 'length': 7}, 'score': {'type': 'number', 'length': 8}}
    rows = [dict(zip(schema, values)) for values in [
        ['Nia     ', 'Math   ', 8.], ['Omar    ', 'Reading', None],
        ['Nia     ', 'Math   ', 9.], ['        ', 'Reading', 4.],
        ['Ivo;Q   ', 'Logic  ', 1.5], ['A\\B     ', '       ', None]]]
    ordered = [deepcopy(rows[index]) for index in (3, 5, 4, 0, 2, 1)]
    return {'datasets': {'scores': table(deepcopy(schema), rows),
                         'ordered': table(deepcopy(schema), ordered)}, 'log': []}


def original_accounting():
    return dict(zip(ACCOUNT_KEYS, (8, 6, 6, 7, 6)))


def batch_witness(cases):
    """Run original source bytes through the independent base-R scanner."""
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        paths = []
        for index, text in enumerate(cases):
            path = folder / f'{index}.sas'
            path.write_bytes(text.encode('utf-8'))
            paths.append(path)
        listing = folder / 'sources.txt'
        listing.write_text(''.join(str(path) + '\n' for path in paths))
        rscript = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        process = subprocess.run([rscript, str(HERE / 'character_input.R'), str(listing)],
                                 cwd=ROOT, capture_output=True, text=True, check=True, timeout=120)
    answers, current, result, current_table = [], None, None, None
    for line in process.stdout.splitlines():
        if line.startswith('BEGIN '):
            assert current is None
            current = int(line[6:]); result = {'datasets': {}, 'log': []}; refused = False; accounting = None
        elif line == 'REFUSED':
            refused = True
        elif line == 'OK':
            pass
        elif line.startswith('TABLE '):
            current_table = table({}, []); result['datasets'][line[6:]] = current_table
        elif line.startswith('COL '):
            _, name, kind, width = line.split(' ')
            current_table['schema'][name] = {'type': kind, 'length': int(width)}
        elif line.startswith('ROW '):
            values = [None if item == 'M' else bytes.fromhex(item[2:]).decode('ascii')
                      if item.startswith('C:') else float(item[2:]) for item in line[4:].split('|')]
            assert len(values) == len(current_table['schema'])
            current_table['rows'].append(dict(zip(current_table['schema'], values)))
        elif line == 'ENDTABLE':
            current_table = None
        elif line.startswith('ACCOUNT '):
            accounting = dict(zip(ACCOUNT_KEYS, map(int, line[8:].split(' '))))
        elif line == 'END':
            assert current == len(answers) + 1
            if not refused:
                assert accounting is not None
            answers.append(None if refused else {'result': result, 'accounting': accounting})
            current = None
        else:
            raise AssertionError((line, process.stderr))
    assert len(answers) == len(cases) and current is None, (process.stdout, process.stderr)
    return answers


def execute(text, emitted=False):
    parsed = compile_plan(text)
    assert not parsed.blocked, parsed.tickets
    portable = parsed.to_dict(); before = deepcopy(portable)
    result = run_plan(portable)
    assert portable == before
    if emitted:
        namespace = {}; output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(translate(text).code, namespace)
        assert_exact(namespace['result'], result)
        assert output.getvalue() == ''
    return result


def hand_cases():
    two = {'a': {'type': 'character', 'length': 4}, 'n': {'type': 'number', 'length': 8}}
    one = {'a': {'type': 'character', 'length': 4}}
    wide = {'a': {'type': 'character', 'length': 64}, 'n': {'type': 'number', 'length': 8}}
    return [
        ('empty', source([]), expected(two, [])),
        ('missing-spans', source([',', ' , . ', ' A ,1.25']), expected(two, [['    ', None], ['    ', None], ['A   ', 1.25]])),
        ('blank-single-field', source(['', '  ', 'ab'], 'a :$4.'), expected(one, [['    '], ['    '], ['ab  ']])),
        ('opaque-punctuation', source(['a;b,2', 'a\\b,-.5', '%&(),+0', 'run;,3', ';;;;,4']), expected(two, [['a;b ', 2.], ['a\\b ', -.5], ['%&()', 0.], ['run;', 3.], [';;;;', 4.]])),
        ('maximum-width', source(['z' * 64 + ',2147483647'], 'a :$64. n'), expected(wide, [['z' * 64, 2147483647.]])),
        ('32-columns-empty', source([], 'a :$1. ' + ' '.join('n' + str(i) for i in range(31))), expected({'a': {'type': 'character', 'length': 1}, **{'n' + str(i): {'type': 'number', 'length': 8} for i in range(31)}}, [])),
        ('exact80-byte-record', source(['z' * 64 + ',' + ' ' * 15], 'a :$64. n'), expected(wide, [['z' * 64, None]])),
        ('numeric-boundaries', source(['X,-2147483647', 'Y,5e-1', 'Z,-0']), expected(two, [['X   ', -2147483647.], ['Y   ', .5], ['Z   ', 0.]])),
        ('crlf-comments', source([' A ,2']).replace('input a', '/* declaration */\ninput a').replace('\n', '\r\n'), expected(two, [['A   ', 2.]])),
    ]


def generated_cases(count=120):
    randomizer = random.Random(69001)
    result = []
    for index in range(count):
        width = randomizer.randint(1, 12)
        schema = {'a': {'type': 'character', 'length': width}, 'n': {'type': 'number', 'length': 8}}
        records, values = [], []
        for _ in range(index % 13):
            char = ''.join(randomizer.choice('ABab _;\\%&') for _ in range(randomizer.randint(0, width))).strip(' ')
            value = randomizer.choice([None, -16., -.5, 0., .25, 2., 1024.])
            token = '' if value is None else str(value)
            records.append(' ' + char + ' ,' + token)
            values.append([char.ljust(width), value])
        result.append((source(records, f'a :${width}. n'), expected(schema, values)))
    return result


def refusal_cases():
    cases = [('short-record', source(['A'])), ('extra-record', source(['A,1,2'])),
             ('blank-record-width', source([''])), ('quote-double', source(['"A",1'])),
             ('quote-single', source(["A'B,1"])), ('tab', source(['A\t,1'])),
             ('nonascii', source(['é,1'])), ('control', source(['A\x01,1'])),
             ('overwidth', source(['ABCDE,1'])), ('character-period', source(['.,1'])),
             ('physical-limit', source(['A' * 79 + ',1'], 'a :$64. n')),
             ('record-count', source(['A,1'] * 1001)), ('zero-width', source([], 'a :$0. n')),
             ('wide-width', source([], 'a :$65. n')), ('duplicate', source([], 'A :$2. a')),
             ('reserved', source([], '_error_ :$2. n')), ('unicode-name', source([], 'K :$2. n')),
             ('numeric-only', source([], 'a n')), ('numeric-informat', source([], 'a :$2. n :8.')),
             ('input-range', source([], 'a :$2. n1-n2')),
             ('unknown-option', source([]).replace('datalines dsd', 'datalines dsd truncover')),
             ('missing-dsd', source([]).replace('datalines dsd', 'datalines')),
             ('body-action', source([]).replace('datalines4;', 'x=1;datalines4;')),
             ('datalines-alias', source([]).replace('datalines4;', 'cards4;')),
             ('indented-terminator', source([]).replace(';;;;', ' ;;;;')),
             ('missing-run', source([]).replace('run;', ''))]
    for token in ('0.1', '1e-16', '2147483648', '.A', 'NaN', '1_0', '1'*33):
        cases.append(('numeric-' + token[:12], source(['A,' + token])))
    return cases


def cli_check(text, truth, wrong=False):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory); path = folder / 'program.sas'; path.write_text(text)
        out = folder / 'job'; expectation = folder / 'expected.json'
        expectation.write_text(json.dumps(truth['datasets']))
        process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'run', str(path),
                                  '--expect', str(expectation), '--output', str(out)], cwd=ROOT,
                                 capture_output=True, text=True, timeout=45)
        receipt = json.loads((out / 'receipt.json').read_text())
        assert process.returncode == (1 if wrong else 0), (process.stdout, process.stderr, receipt)
        assert receipt['accepted'] is (not wrong)
        assert receipt['comparison'] == ('failed' if wrong else 'passed')
        assert receipt['source_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert not (out / 'exports').exists() and not (out / 'reports').exists()
        if wrong:
            assert (out / 'observed.json').is_file() and not (out / 'result.json').exists()
        else:
            assert_exact(json.loads((out / 'result.json').read_text()), truth)
    return True


def wrong_cases():
    truth = original_expected(); result = []
    for damage in ('padding', 'missing-character', 'numeric', 'duplicate', 'stability', 'schema-order', 'descriptor', 'dataset'):
        wrong = deepcopy(truth); raw = wrong['datasets']['scores']; ordered = wrong['datasets']['ordered']
        if damage == 'padding': raw['rows'][0]['person'] = 'Nia'
        elif damage == 'missing-character': raw['rows'][3]['person'] = None
        elif damage == 'numeric': raw['rows'][4]['score'] = 1.6
        elif damage == 'duplicate': ordered['rows'].pop(4)
        elif damage == 'stability': ordered['rows'][3:5] = reversed(ordered['rows'][3:5])
        elif damage == 'schema-order': raw['schema'] = dict(reversed(list(raw['schema'].items())))
        elif damage == 'descriptor': raw['schema']['person']['length'] = 7
        else: wrong['datasets']['extra'] = deepcopy(raw)
        result.append((damage, wrong))
    return result


def atomic_cli():
    texts = [source(['A,1', 'B,0.1']), source(['A,1']) + source(['.,2'], name='later')]
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        for index, text in enumerate(texts):
            path = folder / f'{index}.sas'; path.write_text(text); out = folder / f'job{index}'
            process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'run', str(path), '--output', str(out)],
                                     cwd=ROOT, capture_output=True, text=True, timeout=45)
            receipt = json.loads((out / 'receipt.json').read_text())
            assert process.returncode == 2 and not receipt['accepted'], (process.stdout, process.stderr, receipt)
            assert not any((out / name).exists() for name in ('result.json', 'observed.json', 'exports', 'reports'))
    return len(texts)


def run():
    original = ORIGINAL.read_text(); truth = original_expected()
    if SOURCE_PIN: assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == SOURCE_PIN
    if RESULT_PIN: assert hashlib.sha256(json.dumps(truth, separators=(',', ':')).encode()).hexdigest() == RESULT_PIN
    hand = hand_cases(); generated = generated_cases(); refusals = refusal_cases()
    texts = [original] + [item[1] for item in hand] + [item[0] for item in generated] + [item[1] for item in refusals]
    independent = batch_witness(texts)
    expected_results = [truth] + [item[2] for item in hand] + [item[1] for item in generated]
    for index, expected_result in enumerate(expected_results):
        witness = independent[index]; assert witness is not None, (index, texts[index])
        assert_exact(witness['result'], expected_result)
        assert_exact(execute(texts[index], emitted=True), expected_result)
    assert independent[0]['accounting'] == original_accounting()
    context = validate_original_trace()
    assert context == {'observations': 6, 'attempts': 7, 'outputs': 6}
    for index, (name, text) in enumerate(refusals, len(expected_results)):
        assert compile_plan(text).blocked, name
        assert independent[index] is None, (name, independent[index])
    cli_check(original, truth)
    for _, wrong in wrong_cases(): cli_check(original, wrong, True)
    assert atomic_cli() == 2
    summary = {'hand_programs': len(hand), 'generated_programs': len(generated), 'shared_source_refusals': len(refusals),
               'actual_wrong_dataset_comparators': len(wrong_cases()), 'atomic_cli_refusals': 2,
               'original_accounting': original_accounting(), 'prior_source_promotions': 0}
    print('character-input: ' + json.dumps(summary, sort_keys=True))
    return summary


def validate_original_trace():
    parsed = compile_plan(ORIGINAL.read_text()); assert not parsed.blocked, parsed.tickets
    trace = []
    step = parsed.steps[0]
    from dataclasses import asdict
    execute_step(asdict(step), {}, trace=trace)
    return {'observations': sum(event['kind'] == 'character_input' and event['complete'] for event in trace),
            'attempts': sum(event['kind'] == 'character_input' for event in trace),
            'outputs': sum(event['kind'] == 'character_output' for event in trace)}


if __name__ == '__main__':
    run()
