#!/usr/bin/env python3
"""DS-072 complete original source and independent base-R component schedules.

Bounded repository policy evidence only. No live SAS or whole-vendor proof.
"""
from copy import deepcopy
from dataclasses import asdict
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
from saschi import formatted_input as module
from saschi.parser import Kind, split_statements
from examples.verify_character_input import assert_exact, cli_check

ORIGINAL = HERE / 'formatted_input_capture.sas'
SOURCE_PIN = '29cd0307fbc0148bb5d82b4648074f2335daca66856c393dc4aa9fad4b77bc07'
RESULT_PIN = '93cbf57164869af97f84d5c9f0fe36ed751b7a20448999bffca99071f6a915ba'
TRACE_PIN = '984d0baae91afe2d4bba9296e87bbad4e8cf77861c0ef880690fe3910fa01232'
ACCOUNT_KEYS = ('statements', 'definitions', 'producers', 'physical_records', 'observations', 'attempts', 'outputs')
DEFAULT_DEFINITION = "proc format;\n invalue usr_rating 'High'=9 'Low'=2 'Medium'=5;\nrun;\n"


def source(records, fields='id $ @10 raw $6. @10 value usr_rating.', name='d', definition=DEFAULT_DEFINITION):
    return definition + f'data {name};\ninput {fields};\ndatalines;\n' + ''.join(record + '\n' for record in records) + ';\nrun;\n'


def expected(values, name='d', width=6):
    schema = {'id': {'type': 'character', 'length': 8}, 'raw': {'type': 'character', 'length': width},
              'value': {'type': 'number', 'length': 8}}
    return {'datasets': {name: {'schema': schema, 'rows': [dict(zip(schema, row)) for row in values]}}, 'log': []}


def original_expected():
    ratings = {'person': {'type': 'character', 'length': 8},
               'original': {'type': 'character', 'length': 6}, 'rating': {'type': 'number', 'length': 8}}
    signs = {'token': {'type': 'character', 'length': 8},
             'original': {'type': 'character', 'length': 5}, 'sign': {'type': 'number', 'length': 8}}
    return {'datasets': {
        'ratings': {'schema': ratings, 'rows': [dict(zip(ratings, row)) for row in [
            ['A1      ', 'High  ', 9.], ['B02     ', '7     ', 7.],
            ['C3      ', 'Medium', 5.], ['D04     ', 'Low   ', 2.]]]},
        'signs': {'schema': signs, 'rows': [dict(zip(signs, row)) for row in [
            ['p       ', 'Plus ', 1.], ['n       ', 'Minus', -1.], ['z       ', '0    ', 0.]]]}}, 'log': []}


def original_accounting():
    return dict(zip(ACCOUNT_KEYS, (14, 2, 2, 7, 7, 9, 7)))


def original_trace():
    # Hand event schedule: four observations at INPUT line6,three at line18,one EOF each.
    events = []
    for line, observations in ((6, 4), (18, 3)):
        for attempt in range(1, observations + 2):
            complete = attempt <= observations
            events.append({'kind': 'formatted_input', 'line': line, 'attempt': attempt, 'complete': complete})
            if complete: events.append({'kind': 'formatted_output', 'line': line, 'observation': attempt})
    return events


def direct(source_text):
    """Component-only compiler, no alternate public admission path."""
    statements = split_statements(source_text)
    registry, tables, steps, trace = {}, {}, [], []
    position = 0
    while position < len(statements):
        statement = statements[position]
        if statement.text.lower() == 'proc format':
            step = module.compile_definition(statements[position:position + 3])
            context = module.validate_definition_step(asdict(step))
            if len(registry) >= 8 or step.name in registry:
                raise ValueError('duplicate or excess job-local informat')
            registry[step.name] = context; position += 3
        else:
            step = module.compile_data(statements[position:position + 5], source_text, registry)
            if len(tables) >= 8:
                raise ValueError('excess formatted producer')
            table, log = module.execute_data(asdict(step), registry, tables, trace=trace)
            assert log == []
            tables[step.name] = table; position += 5
        steps.append(step)
    if not registry or not tables:
        raise ValueError('component program requires a definition and producer')
    return {'result': {'datasets': tables, 'log': []}, 'registry': registry, 'steps': steps, 'trace': trace}


def execute(text, emitted=False):
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    from saschi.emit_py import translate
    plan = compile_plan(text); assert not plan.blocked, plan.tickets
    portable = plan.to_dict(); saved = deepcopy(portable)
    result = run_plan(portable); assert_exact(portable, saved)
    if emitted:
        namespace = {}; output = io.StringIO()
        with contextlib.redirect_stdout(output): exec(translate(text).code, namespace)
        assert_exact(namespace['result'], result); assert output.getvalue() == ''
    return result


def batch_witness(cases, definitions=False):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory); paths = []
        for index, text in enumerate(cases):
            path = folder / f'{index}.sas'; path.write_bytes(text.encode()); paths.append(path)
        listing = folder / 'sources.txt'; listing.write_text(''.join(str(path) + '\n' for path in paths))
        rscript = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        process = subprocess.run([rscript, str(HERE / ('numeric_invalue.R' if definitions else 'formatted_input.R')), str(listing)],
                                 cwd=ROOT, capture_output=True, text=True, timeout=120, check=True)
    answers, current, result, table, registry, definition, accounting, refused = [], None, None, None, {}, None, None, False
    trace = []
    for line in process.stdout.splitlines():
        if line.startswith('BEGIN '):
            assert current is None; current = int(line[6:]); result = {'datasets': {}, 'log': []}; registry = {}; refused = False; accounting = None; trace = []
        elif line == 'REFUSED': refused = True
        elif line == 'OK': pass
        elif line.startswith('DEF '):
            _, name, width = line.split(); definition = {'width': int(width), 'mapping': {}}; registry[name] = definition
        elif line.startswith('MAP '):
            _, raw, value = line.split(); definition['mapping'][bytes.fromhex(raw).decode('ascii')] = int(value)
        elif line == 'ENDDEF': definition = None
        elif line.startswith('TABLE '): table = {'schema': {}, 'rows': []}; result['datasets'][line[6:]] = table
        elif line.startswith('COL '):
            _, name, kind, width = line.split(); table['schema'][name] = {'type': kind, 'length': int(width)}
        elif line.startswith('ROW '):
            values = [bytes.fromhex(value[2:]).decode('ascii') if value.startswith('C:') else float(value[2:]) for value in line[4:].split('|')]
            assert len(values) == len(table['schema']); table['rows'].append(dict(zip(table['schema'], values)))
        elif line == 'ENDTABLE': table = None
        elif line.startswith('TRACE '):
            values = line.split()
            if values[1] == 'input':
                trace.append({'kind': 'formatted_input', 'line': int(values[2]), 'attempt': int(values[3]), 'complete': values[4] == '1'})
            else: trace.append({'kind': 'formatted_output', 'line': int(values[2]), 'observation': int(values[3])})
        elif line.startswith('ACCOUNT '):
            keys = ('statements', 'definitions') if definitions else ACCOUNT_KEYS
            accounting = dict(zip(keys, map(int, line[8:].split())))
        elif line == 'END':
            assert current == len(answers) + 1
            assert refused or accounting is not None
            answers.append(None if refused else {'registry': registry, 'result': result, 'accounting': accounting, 'trace': trace}); current = None
        else: raise AssertionError((line, process.stderr))
    assert len(answers) == len(cases) and current is None, (process.stdout, process.stderr)
    return answers


def hand_cases(mode='input'):
    result = [
        ('empty', source([]), expected([])),
        ('mapped-and-fallback', source(['A        High  ', 'B        7     ', 'C        Low   ']),
         expected([['A       ', 'High  ', 9.], ['B       ', '7     ', 7.], ['C       ', 'Low   ', 2.]])),
        ('signed-exponent-fallback', source(['A        -1e2  ', 'B        +0000 ', 'C        1.0e2 ']),
         expected([['A       ', '-1e2  ', -100.], ['B       ', '+0000 ', 0.], ['C       ', '1.0e2 ', 100.]])),
        ('period-fixed-character-only', source(['A        .     High  '], 'id $ @10 raw $6. @16 value usr_rating.'),
         expected([['A       ', '      ', 9.]])),
        ('leading-fixed-character-only', source(['A          X   High  '], 'id $ @10 raw $6. @16 value usr_rating.'),
         expected([['A       ', 'X     ', 9.]])),
        ('repeated-and-backward-spans', source(['007      Medium'], 'id $ @10 raw $6. @10 value usr_rating.'),
         expected([['007     ', 'Medium', 5.]])),
        ('same-line-code', source(['A        High  ']).replace('data d;\ninput', 'data d;input'),
         expected([['A       ', 'High  ', 9.]])),
        ('crlf-and-comments', ('/* π is opaque */\n' + source(['A        Medium'])).replace('\n', '\r\n'),
         expected([['A       ', 'Medium', 5.]])),
        ('edge-integers', source(['A        -1000 ', 'B        1000  ']),
         expected([['A       ', '-1000 ', -1000.], ['B       ', '1000  ', 1000.]])),
        ('identifier-eight-and-case', source(['Abc123xy High  '], name='MiXeD'),
         expected([['Abc123xy', 'High  ', 9.]], name='mixed')),
    ]
    if mode == 'invalue':
        definition = "proc format;invalue eval 'A'=1 'a'=-1 'Longest'=5;run;\n"
        text = source(['x        A      ', 'y        a      ', 'z        2      '],
                      'id $ @10 raw $7. @10 value eval.', definition=definition)
        result.append(('literal-case-and-width', text, expected([['x       ', 'A      ', 1.], ['y       ', 'a      ', -1.], ['z       ', '2      ', 2.]], width=7)))
    return result


def definition_cases():
    return [
        ('literal-case', "proc format;invalue eval 'A'=1 'a'=-1;run;", {'eval': {'width': 1, 'mapping': {'A': 1, 'a': -1}}}),
        ('right-padding-width', "proc format;invalue usr_grade 'Wide name'=2 'X'=3;run;", {'usr_grade': {'width': 9, 'mapping': {'Wide name': 2, 'X': 3}}}),
        ('bounds', "proc format;invalue usr_sign 'Positive'=1000 'Negative'=-1000;run;", {'usr_sign': {'width': 8, 'mapping': {'Positive': 1000, 'Negative': -1000}}}),
        ('source-leading-zero', "proc format;invalue eval 'A'=0000001 'B'=-000;run;", {'eval': {'width': 1, 'mapping': {'A': 1, 'B': 0}}}),
        ('two-definitions', "proc format;invalue eval 'A'=1;run;proc format;invalue usr_other 'B'=2;run;", {'eval': {'width': 1, 'mapping': {'A': 1}}, 'usr_other': {'width': 1, 'mapping': {'B': 2}}}),
        ('punctuation-literal', "proc format;invalue usr_code 'A;B'=7 'X\\Y'=2;run;", {'usr_code': {'width': 3, 'mapping': {'A;B': 7, 'X\\Y': 2}}}),
        ('32-literals', "proc format;invalue eval " + ' '.join(f"'K{i}'={i}" for i in range(32)) + ';run;',
         {'eval': {'width': 3, 'mapping': {f'K{i}': i for i in range(32)}}}),
        ('31-byte-name', "proc format;invalue " + 'usr_' + 'x' * 27 + " 'A'=1;run;",
         {'usr_' + 'x' * 27: {'width': 1, 'mapping': {'A': 1}}}),
    ]


def generated_cases(count=160, mode='input'):
    rng = random.Random(72031 if mode == 'input' else 71031); cases = []
    for index in range(count):
        width = rng.randint(4, 12); key = 'Grade' + 'X' * max(0, width - 5)
        key = key[:width]; mapped = rng.randint(-1000, 1000)
        definition = f"proc format;invalue usr_generated '{key}'={mapped} 'Q'=-2;run;\n"
        records, values = [], []
        for row in range(index % 11):
            identifier = f'R{row:02d}'
            token, value = (key, float(mapped)) if row % 3 == 0 else ('Q', -2.) if row % 3 == 1 else (str(rng.randint(-99, 99)), None)
            if value is None: value = float(token)
            records.append(identifier.ljust(9) + token.ljust(width))
            values.append([identifier.ljust(8), token.ljust(width), value])
        cases.append((source(records, f'id $ @10 raw ${width}. @10 value usr_generated.', definition=definition), expected(values, width=width)))
    return cases


def refusal_cases():
    empty = source([])
    bad = [
        ('missing-proc-semicolon', empty.replace('proc format;', 'proc format')),
        ('missing-run-semicolon', empty[:-2] + '\n'),
        ('format-option', empty.replace('proc format;', 'proc format fmtlib;')),
        ('definition-option', empty.replace('usr_rating ', 'usr_rating (upcase) ', 1)),
        ('unknown-custom-name', empty.replace('usr_rating', 'rating')),
        ('digit-custom-name', empty.replace('usr_rating', 'usr_rating2')),
        ('32-byte-custom-name', empty.replace('usr_rating', 'usr_' + 'x' * 28)),
        ('duplicate-literal', empty.replace("'Low'=2", "'High'=2")),
        ('empty-literal', empty.replace("'Low'", "''")),
        ('edge-space-literal', empty.replace("'Low'", "' Low'")),
        ('macro-literal', empty.replace("'Low'", "'&Low'")),
        ('fractional-result', empty.replace("'Low'=2", "'Low'=2.5")),
        ('large-result', empty.replace("'Low'=2", "'Low'=1001")),
        ('other-default', empty.replace("'Low'=2", "other=2")),
        ('range', empty.replace("'Low'=2", "'A'-'Z'=2")),
        ('unicode-name', empty.replace('usr_rating', 'usr_K')),
        ('unicode-field', empty.replace('id $', 'K $')),
        ('duplicate-field', empty.replace('raw $6.', 'ID $6.')),
        ('reserved-field', empty.replace('id $', '_error_ $')),
        ('missing-pointer', empty.replace('@10 raw', 'raw')),
        ('relative-pointer', empty.replace('@10 raw', '+10 raw')),
        ('pointer-expression', empty.replace('@10 raw', '@(10) raw')),
        ('zero-pointer', empty.replace('@10 raw', '@0 raw')),
        ('wide-character', empty.replace('$6.', '$33.')),
        ('outside-span', empty.replace('@10 raw', '@80 raw')),
        ('builtin-numeric', empty.replace('value usr_rating.', 'value 6.')),
        ('unavailable-informat', empty.replace('value usr_rating.', 'value usr_other.')),
        ('no-custom-read', empty.replace('@10 value usr_rating.', '@10 value $6.')),
        ('extra-body', empty.replace('datalines;', 'x=1;datalines;')),
        ('infile-option', empty.replace('input id', 'infile datalines;input id')),
        ('cards-alias', empty.replace('datalines;', 'cards;')),
        ('datalines4', empty.replace('datalines;', 'datalines4;').replace(';\nrun;\n', ';;;;\nrun;\n')),
        ('indented-delimiter', empty.replace('\n;\n', '\n ;\n')),
        ('trailing-delimiter', empty.replace('\n;\n', '\n; \n')),
        ('short-record', source(['A        High ' ])),
        ('first-token-period', source(['.        High  '])),
        ('first-token-overwidth', source(['ABCDEFGHIHigh  '])),
        ('semicolon-record', source(['A        Hi;gh '])),
        ('quoted-record', source(['A        "High"'])),
        ('nonascii-record', source(['A        é     '])),
        ('tab-record', source(['A\t       High  '])),
        ('too-many-records', source(['A        High  '] * 1001)),
        ('record81', source(['A        High  ' + ' ' * 66])),
    ]
    for token in ('', '.', '.A', 'high', ' High', '0.1', '1001', '-1001', '1e16', 'NaN'):
        bad.append(('custom-field-' + repr(token), source(['A        ' + token.ljust(6)])))
    return bad


def wrong_cases():
    truth = original_expected(); result = []
    for kind in ('padding', 'id-leading-zero', 'mapped', 'fallback', 'row-order', 'row-count', 'schema-order', 'descriptor'):
        wrong = deepcopy(truth); table = wrong['datasets']['ratings']
        if kind == 'padding': table['rows'][0]['person'] = 'A1'
        elif kind == 'id-leading-zero': table['rows'][1]['person'] = 'B2      '
        elif kind == 'mapped': table['rows'][0]['rating'] = 8.
        elif kind == 'fallback': table['rows'][1]['rating'] = 0.
        elif kind == 'row-order': table['rows'][0:2] = reversed(table['rows'][0:2])
        elif kind == 'row-count': table['rows'].pop()
        elif kind == 'schema-order': table['schema'] = dict(reversed(list(table['schema'].items())))
        else: table['schema']['original']['length'] = 5
        result.append((kind, wrong))
    return result


def atomic_cli():
    # A valid earlier producer must not publish when a later producer is invalid.
    text = source(['A        High  ']) + source(['B        high  '], name='later', definition='')
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory); path = folder / 'program.sas'; path.write_text(text); out = folder / 'job'
        process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'run', str(path), '--output', str(out)],
                                 cwd=ROOT, capture_output=True, text=True, timeout=45)
        receipt = json.loads((out / 'receipt.json').read_text())
        assert process.returncode == 2 and receipt['accepted'] is False, (process.stdout, process.stderr, receipt)
        assert not any((out / name).exists() for name in ('result.json', 'observed.json', 'exports', 'reports'))
    return 1


def run(mode='input'):
    original = ORIGINAL.read_text(); truth = original_expected()
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == SOURCE_PIN
    assert hashlib.sha256(json.dumps(truth, separators=(',', ':')).encode()).hexdigest() == RESULT_PIN
    hand, generated, refused = hand_cases(mode), generated_cases(mode=mode), refusal_cases()
    texts = [original] + [item[1] for item in hand] + [item[0] for item in generated] + [item[1] for item in refused]
    independent = batch_witness(texts)
    positive = [truth] + [item[2] for item in hand] + [item[1] for item in generated]
    for index, expected_result in enumerate(positive):
        assert independent[index] is not None, (index, texts[index])
        assert_exact(independent[index]['result'], expected_result)
        component_result = direct(texts[index])
        assert_exact(component_result['result'], expected_result)
        assert_exact(independent[index]['trace'], component_result['trace'])
        assert_exact(execute(texts[index], emitted=True), expected_result)
    assert independent[0]['accounting'] == original_accounting()
    trace = direct(original)['trace']
    assert_exact(trace, original_trace())
    assert hashlib.sha256(json.dumps(trace, separators=(',', ':')).encode()).hexdigest() == TRACE_PIN
    from saschi.plan import compile_plan
    for index, (name, text) in enumerate(refused, len(positive)):
        assert independent[index] is None, (name, independent[index])
        try: direct(text)
        except ValueError: pass
        else: raise AssertionError(name)
        assert compile_plan(text).blocked, name
    definitions = definition_cases(); observed = batch_witness([item[1] for item in definitions], definitions=True)
    for (name, text, expected_registry), witness in zip(definitions, observed):
        assert witness is not None, name; assert_exact(witness['registry'], expected_registry)
    cli_check(original, truth)
    for _, wrong in wrong_cases(): cli_check(original, wrong, True)
    atomic_cli()
    summary = {'hand_programs': len(hand), 'generated_programs': len(generated), 'shared_source_refusals': len(refused),
               'definition_handpins': len(definitions), 'actual_wrong_dataset_comparators': len(wrong_cases()),
               'atomic_cli_refusals': 1, 'original_accounting': original_accounting(),
               'prior_source_promotions': 0}
    print(('formatted-input' if mode == 'input' else 'numeric-invalue') + ': ' + json.dumps(summary, sort_keys=True))
    return summary


if __name__ == '__main__': run()
