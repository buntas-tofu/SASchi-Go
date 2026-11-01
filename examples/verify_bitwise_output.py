#!/usr/bin/env python3
"""DS-070 explicit bitwise67 source/hand/R/emitted/CLI evidence, no live SAS."""
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
from saschi import bitwise_output
from saschi.emit_py import translate
from saschi.job import build_job
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from examples.verify_bitwise import program_state

PROFILE = bitwise_output.PROFILE
ORIGINAL = HERE / 'bitwise_output_capture.sas'
CORPUS_SHA256 = 'e774418156723a8c2aa8f6a2e6b9fac9f6c258a87ee1aff13502b8a654584799'
SOURCE_PIN = 'c7861ed5e78a18ee80bbb64e4b864510d2e7bd1846cc01b93d35eb6ad8f9e00f'
ORIGINAL_STDOUT_PIN = 'b7a683f88ee741719d5afad01a6b84a9ced8255b6e38afeb63af236c98c7749d'
CORPUS_STDOUT_PIN = '1d4faadb6075c1a28fc2167759c8b71f20a573e62108a3a8d1efb3e4ca43c40d'
ACCOUNT_KEYS = ('statements', 'assignments', 'bitwise_calls', 'width', 'variables')


def corpus_path():
    return Path(os.environ.get('SASCHI_ROKU_CORPUS', str(ROOT.parent / 'saschi-roku/corpus'))) / 'bitwise_operations.sas'


def text(case):
    return case.read_text() if isinstance(case, Path) else case


def expected(record):
    return {'datasets': {}, 'log': [record]}


def original_expected():
    return expected('Seed=2 mask=6 Bits=11 Shift=16 ' + bitwise_output.TAIL)


def corpus_expected():
    return expected('a=105 b=91 c=50 d=73 e=123 f=4294967190 g=210 h=52 ' + bitwise_output.TAIL)


def source(body):
    return 'data _null_;\n' + body + '\nput _all_;\nrun;\n'


def assert_exact(actual, truth):
    if type(truth) is dict:
        assert type(actual) is dict and list(actual) == list(truth), (actual, truth)
        for key in truth: assert_exact(actual[key], truth[key])
    elif type(truth) is list:
        assert type(actual) is list and len(actual) == len(truth), (actual, truth)
        for a, b in zip(actual, truth): assert_exact(a, b)
    elif type(truth) in (int, float):
        assert type(actual) in (int, float) and actual == truth, (actual, truth)
    else:
        assert type(actual) is type(truth) and actual == truth, (actual, truth)


def witnesses(cases):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory); paths = []
        for index, case in enumerate(cases):
            if isinstance(case, Path): path = case.resolve()
            else:
                path = folder / f'{index}.sas'; path.write_text(case)
            paths.append(path)
        listing = folder / 'sources.txt'; listing.write_text(''.join(str(path) + '\n' for path in paths))
        rscript = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        process = subprocess.run([rscript, str(HERE / 'bitwise_output.R'), str(listing)], cwd=ROOT,
                                 capture_output=True, text=True, check=True, timeout=120)
    answers = []; current = None
    for line in process.stdout.splitlines():
        if line.startswith('BEGIN '):
            current = {'fields': [], 'events': []}; index = int(line[6:]); refused = False
        elif line == 'REFUSED': refused = True
        elif line == 'OK': pass
        elif line.startswith('ACCOUNT '): current['accounting'] = dict(zip(ACCOUNT_KEYS, map(int, line[8:].split())))
        elif line.startswith('FIELD '):
            _, name, value = line.split(); current['fields'].append({'name': bytes.fromhex(name).decode('ascii'), 'kind': 'number', 'value': float(value)})
        elif line.startswith('ASSIGN '):
            _, position, name, value = line.split(); current['events'].append({'kind': 'assign', 'line': int(position), 'name': name, 'value': float(value)})
        elif line.startswith('OUTPUT '):
            _, position, encoded = line.split(); record = bytes.fromhex(encoded).decode('ascii')
            current['result'] = expected(record)
            current['events'].append({'kind': 'put_all_67', 'line': int(position), 'record': record, 'fields': current['fields']})
        elif line == 'END':
            assert current is not None and index == len(answers) + 1
            answers.append(None if refused else current); current = None
        else: raise AssertionError((line, process.stderr))
    assert len(answers) == len(cases) and current is None, (process.stdout, process.stderr)
    return answers


def execute(case, emitted=False):
    source_text = text(case); parsed = compile_plan(source_text, output_contract=PROFILE)
    assert not parsed.blocked, parsed.tickets
    portable = parsed.to_dict(); saved = deepcopy(portable)
    context = bitwise_output.validate_step(portable['steps'][0], portable['version'])
    observed = run_plan(portable); assert portable == saved
    if emitted:
        namespace = {}; stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout): exec(translate(source_text, output_contract=PROFILE).code, namespace)
        assert_exact(namespace['result'], observed)
        assert stdout.getvalue() == context['record'] + '\n'
    return observed, context


def width_source(width):
    first = 'a' + 'x' * 31; second = 'b' * (width - 63)
    return source(first + '=1;' + second + '=bnot(0);'), expected(first + '=1 ' + second + '=4294967295 ' + bitwise_output.TAIL)


def hand_cases():
    return [
        ('zero-complement', source('x=bnot(4294967295);'), expected('x=0 ' + bitwise_output.TAIL)),
        ('max-complement', source('x=bnot(0);'), expected('x=4294967295 ' + bitwise_output.TAIL)),
        ('unsigned-shift31', source('a=blshift(1,31);b=brshift(4294967295,31);'), expected('a=2147483648 b=1 ' + bitwise_output.TAIL)),
        ('shift-zero', source('a=blshift(2147483648,0);b=brshift(2147483648,0);'), expected('a=2147483648 b=2147483648 ' + bitwise_output.TAIL)),
        ('nested-overwrite', source('Seed=1e3;mask=+0;value=bor(band(Seed,7),1);Seed=bnot(4294967295);'), expected('Seed=0 mask=0 value=1 ' + bitwise_output.TAIL)),
        ('decimal-integral-and-zero', source('a=1.000;b=band(a,-0.0);'), expected('a=1 b=0 ' + bitwise_output.TAIL)),
        ('comment-fences', '/* nested /* comment */ still comment */\n%* ordinary comment;\n' + source('a=band(1,1);').replace(';', ';;'), expected('a=1 ' + bitwise_output.TAIL)),
        *[(f'width-{width}', *width_source(width)) for width in (64, 65, 66, 67)]
    ]


def generated_cases(count=160):
    rng = random.Random(70001); result = []
    names = ('band', 'bor', 'bxor', 'bnot', 'blshift', 'brshift')
    for index in range(count):
        name = names[index % len(names)]; a = rng.choice([0, 1, 2147483648, 4294967295, rng.randrange(2**32)])
        b = rng.randrange(32) if name in ('blshift', 'brshift') else rng.choice([0, 4294967295, rng.randrange(2**32)])
        arguments = 'A' if name == 'bnot' else 'A,b'
        if name == 'band': value = a & b
        elif name == 'bor': value = a | b
        elif name == 'bxor': value = a ^ b
        elif name == 'bnot': value = (2**32 - 1) - a
        elif name == 'blshift': value = (a * 2**b) % 2**32
        else: value = a // 2**b
        body = f'A={a};b={b};c={name}({arguments});'
        if index % 4 == 0:
            body += 'A=band(c,7);'; final_a = value & 7
        else: final_a = a
        record = f'A={final_a} b={b} c={value} ' + bitwise_output.TAIL
        result.append((source(body), expected(record)))
    return result


def refusal_cases():
    cases = [(f'value-{bad}', source('a=' + bad + ';b=bnot(a);')) for bad in ('.', '.A', '-1', '1.5', '4294967296', '1e-999', '0e33', '0' * 33, '1.000000000000000000000001')]
    cases += [(f'body-{index}', source(body)) for index, body in enumerate([
        'a=1;', 'a=bnot(later);later=1;', 'a=blshift(1,32);', 'a=brshift(1,-1);',
        'a=bnot();', 'a=band(1);', 'a=band(1,2,3);', 'a=max(1,2);', 'a=band(1,1)+0;',
        'a="1";b=bnot(0);', 'a=1;put _all_;b=bnot(0);', 'if 0 then a=bnot(0);',
        'retain a 1;a=bnot(a);', 'input a;b=bnot(a);', 'array a{1} x;x=bnot(0);',
        '_error_=1;a=bnot(0);', 'K=1;a=bnot(0);'])]
    cases.append(('width-68', width_source(68)[0]))
    cases.append(('assignments-65', source('a=0;' * 64 + 'a=bnot(0);')))
    cases.append(('depth-33', source('a=' + 'bnot(' * 33 + '0' + ')' * 33 + ';')))
    cases.append(('second-step', source('a=bnot(0);') + 'data _null_;x=1;run;'))
    cases.append(('named-output', source('a=bnot(0);').replace('data _null_', 'data d')))
    return cases


def cli_check(case, truth, expected_log=None, wrong=False):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        if isinstance(case, Path): path = case
        else: path = folder / 'program.sas'; path.write_text(case)
        output = folder / 'job'; expectation = folder / 'expected-log.json'
        expectation.write_text(json.dumps(truth['log'] if expected_log is None else expected_log))
        command = [sys.executable, '-B', '-m', 'saschi', 'run', str(path), '--output-contract', PROFILE,
                   '--expect-log', str(expectation), '--output', str(output)]
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=45)
        receipt = json.loads((output / 'receipt.json').read_text())
        assert process.returncode == (1 if wrong else 0), (process.stdout, process.stderr, receipt)
        assert receipt['accepted'] is (not wrong) and receipt['output_contract'] == PROFILE
        assert receipt['log_comparison'] == ('failed' if wrong else 'passed')
        assert receipt['log_comparison_contract'] == 'ascii-log-records-v1'
        assert receipt['expected_log_sha256'] == hashlib.sha256(expectation.read_bytes()).hexdigest()
        assert receipt['source_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert not (output / 'reports').exists() and not (output / 'exports').exists()
        if wrong:
            assert (output / 'observed.json').exists() and not (output / 'result.json').exists()
            assert_exact(json.loads((output / 'observed.json').read_text()), truth)
        else: assert_exact(json.loads((output / 'result.json').read_text()), truth)
        assert truth['log'][0] not in process.stdout
    return True


def wrong_logs():
    record = corpus_expected()['log'][0]
    return [('signed-not', [record.replace('4294967190', '-106')]),
            ('signed-shift', [record.replace('h=52', 'h=53')]),
            ('trailing-space', [record.rstrip()]),
            ('automatic-omission', [record.replace('_ERROR_=0 ', '')]),
            ('automatic-order', [record.replace('_ERROR_=0 _N_=1 ', '_N_=1 _ERROR_=0 ')]),
            ('pdv-order', [record.replace('a=105 b=91 ', 'b=91 a=105 ')]),
            ('wrap-at64', [record[:64], record[64:]]), ('duplicate-record', [record, record])]


def default_refusal(path):
    original = path.read_bytes(); width, fields = program_state(path)
    assert width == 67 and len(fields) == 8
    parsed = compile_plan(original.decode()); assert not parsed.blocked
    assert parsed.steps[0].kind == 'data' and parsed.steps[0].operations[-1].kind == 'put_all'
    assert parsed.steps[0].operations[-1].args == {}
    job = build_job(original.decode()); assert job.code == 1 and job.result is None
    assert 'beyond 64 columns' in job.receipt['error'] and 'output_contract' not in job.receipt
    assert path.read_bytes() == original


def atomic_cli():
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        for index, case in enumerate([width_source(68)[0], source('a=band(1,1);a=blshift(1,32);')]):
            path = folder / f'{index}.sas'; path.write_text(case); output = folder / f'job{index}'
            process = subprocess.run([sys.executable, '-B', '-m', 'saschi', 'run', str(path), '--output-contract', PROFILE,
                                      '--output', str(output)], cwd=ROOT, capture_output=True, text=True, timeout=45)
            receipt = json.loads((output / 'receipt.json').read_text())
            assert process.returncode == 2 and not receipt['accepted'], (process.stdout, process.stderr, receipt)
            assert not any((output / name).exists() for name in ('result.json', 'observed.json', 'reports', 'exports'))
    return 2


def run():
    path = corpus_path(); raw = path.read_bytes(); assert hashlib.sha256(raw).hexdigest() == CORPUS_SHA256 and len(raw) == 469
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == SOURCE_PIN
    assert hashlib.sha256((original_expected()['log'][0] + '\n').encode('ascii')).hexdigest() == ORIGINAL_STDOUT_PIN
    assert hashlib.sha256((corpus_expected()['log'][0] + '\n').encode('ascii')).hexdigest() == CORPUS_STDOUT_PIN
    hand = hand_cases(); generated = generated_cases(); refused = refusal_cases()
    cases = [ORIGINAL, path] + [case[1] for case in hand] + [case[0] for case in generated] + [case[1] for case in refused]
    independent = witnesses(cases); truths = [original_expected(), corpus_expected()] + [case[2] for case in hand] + [case[1] for case in generated]
    for index, truth in enumerate(truths):
        witness = independent[index]; assert witness is not None, (index, cases[index])
        assert_exact(witness['result'], truth)
        observed, context = execute(cases[index], emitted=True); assert_exact(observed, truth)
        assert_exact(context['events'], witness['events'])
    assert independent[0]['accounting'] == dict(zip(ACCOUNT_KEYS, (8, 5, 3, 47, 4)))
    assert independent[1]['accounting'] == dict(zip(ACCOUNT_KEYS, (11, 8, 6, 67, 8)))
    for (label, case), witness in zip(refused, independent[len(truths):]):
        assert compile_plan(case, output_contract=PROFILE).blocked, label
        assert witness is None, label
    default_refusal(path); cli_check(ORIGINAL, original_expected()); cli_check(path, corpus_expected())
    for _, damaged in wrong_logs(): cli_check(path, corpus_expected(), damaged, True)
    assert atomic_cli() == 2 and path.read_bytes() == raw
    print(f'VERIFIED: bitwise-output {len(hand)} hand programs,{len(generated)} generated complete-source/R/runtime/emitted schedules,{len(refused)} shared source refusals,{len(wrong_logs())} actual wrong-log CLI comparisons,2 atomic CLI refusals; explicit profile,old defaults unchanged; no live SAS')
    print('VERIFIED corpus: bitwise_operations.sas; unchanged469bytes/11statements/8PDVfields/6calls/one67-byte record+LF; independent hand/full-source R and output_contract=bitwise-put-all-67-v1 runtime/emitted/CLI; old64-column default refusal preserved; no live SAS or physical-log claim')


if __name__ == '__main__':
    run()
