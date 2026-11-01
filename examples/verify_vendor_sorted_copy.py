#!/usr/bin/env python3
"""Prove one complete external program under explicit repository logical policies."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.vendor_sources import verify_sources
from vendor_sort_hand import build, LINES
from saschi.emit_py import translate
from saschi.emit_cpp import translate as translate_cpp
from saschi.job import build_job
from saschi.plan import compile_plan
from saschi import character_input, mixed_reports, runtime

IDENTITY = 'sas-code-examples-sorted-copy-v1'
SOURCE_SHA256 = '33ca0b33fb43b9cefe27c8879e204bfbe7ee0fe675769ec266bf9c5ed75d77c5'
FROZEN = {
    'result.json': 'd37b4ad3b19ffb360e3aa8353fb91811a3e6eef4a7d2387604c74ab7e7115705',
    'accounting.json': '6cddde70481f76581a619e47dbed6cb7e9c866e0a04eecdd1a47eeccb752d8af',
    'trace.json': '54677839608420403d7a4d172b8855cef8c95d5909af39556b6fc1edb3612369',
    'print_01.txt': '965c813bf45fcd5a95ee4d557820536b7126ad67dd3e207d729f7af78574d997',
    'print_02.txt': '5a0143b93d250c94d696e29a31acdfbd65003984ff448a1291778b592f807036',
}


def need(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def ordered_equal(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isfinite(left) and math.isfinite(right) and left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return list(left) == list(right) and all(ordered_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(ordered_equal(a, b) for a, b in zip(left, right))
    return left == right


def traced_run(plan):
    """Observe actual whole-plan calls and legacy SORT, without changing values."""
    trace = []
    input_engine, title_engine = character_input.execute_step, mixed_reports.execute_title
    print_engine, native_sorted = mixed_reports.execute_print, sorted
    sort_steps = [step for step in plan['steps'] if step['kind'] == 'sort']
    need(len(sort_steps) == 1, 'whole target requires its one SORT')
    sort_step = sort_steps[0]
    sort_calls = []

    def input_observer(step, tables, version=2, **kwargs):
        observations = []
        table, logs = input_engine(step, tables, version, trace=observations)
        lines = step['operations'][0]['args']['source_lines']
        trace.append({'event': 'data_begin', 'line': step['line'], 'table': step['name']})
        for observation in observations:
            if observation['kind'] == 'character_input':
                event = {'event': 'input_attempt', 'line': observation['line'],
                         'record': observation['attempt']}
                if observation['complete']:
                    event['record_line'] = lines[3] + observation['attempt']
                event['eof'] = not observation['complete']
                trace.append(event)
            else:
                need(observation['kind'] == 'character_output', 'unexpected input event')
                trace.append({'event': 'implicit_output', 'table': step['name'],
                              'observation': observation['observation']})
        trace.append({'event': 'data_end', 'line': lines[-1], 'table': step['name'], 'rows': len(table['rows'])})
        return table, logs

    def title_observer(step, version=2, **kwargs):
        value = title_engine(step, version)
        event = {'event': 'title_reset' if value is None else 'title_set', 'line': step['line']}
        if value is not None:
            event['text'] = value
        trace.append(event)
        return value

    def print_observer(step, tables, title=None, ordinal=1, version=2, **kwargs):
        result = print_engine(step, tables, title, ordinal, version)
        trace.append({'event': 'print', 'line': step['line'], 'table': step['inputs'][0],
                      'report': next(iter(result)), 'rows': len(tables[step['inputs'][0]]['rows']), 'title': title})
        return result

    def sort_observer(values, *args, **kwargs):
        items = list(values)
        result = native_sorted(items, *args, **kwargs)
        ordinals = {id(row): index for index, row in enumerate(items, 1)}
        order = [ordinals[id(row)] for row in result]
        sort_calls.append(order)
        trace.append({'event': 'sort', 'line': sort_step['line'], 'source': sort_step['inputs'][0],
                      'destination': sort_step['name'], 'source_ordinals': order})
        return result

    with patch.object(character_input, 'execute_step', input_observer), \
            patch.object(mixed_reports, 'execute_title', title_observer), \
            patch.object(mixed_reports, 'execute_print', print_observer), \
            patch.object(runtime, 'sorted', sort_observer, create=True):
        result = runtime.run_plan(plan)
    need(len(sort_calls) == 1, 'SORT execution count differs')
    return result, trace


def cli(source, output, *, expected=None, reports=None):
    command = [sys.executable, '-B', '-m', 'saschi', 'run', str(source), '--output', str(output)]
    if expected is not None:
        command += ['--expect', str(expected)]
    if reports is not None:
        command += ['--expect-reports', str(reports)]
    env = {**os.environ, 'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'}
    run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    need((output / 'receipt.json').is_file(), 'actual CLI did not publish a controlled receipt: ' + run.stderr)
    receipt = json.loads((output / 'receipt.json').read_text())
    return run, receipt


def late_failure(area):
    # This is our own two-producer adversarial source, never a changed vendor file.
    def producer(name, token):
        return ('data ' + name + ';\ninfile datalines dsd;\ninput word :$4. number;\n'
                'datalines4;\nA,' + token + '\n;;;;\nrun;\n')
    text = producer('first', '1') + 'title "First"; proc print data=first; run;\n'
    text += producer('second', '0.5') + 'title "Second"; proc print data=second; run;\n'
    seen = []
    original = mixed_reports.execute_print
    def observe(step, tables, title=None, ordinal=1, version=2, **kwargs):
        seen.append(ordinal)
        return original(step, tables, title, ordinal, version)
    with patch.object(mixed_reports, 'execute_print', observe):
        job = build_job(text)
    need(not job.plan.blocked and seen == [1, 2] and job.code == 1 and job.result is None,
         'late second-report failure was not an actual runtime refusal')
    source = area / 'owned-late-failure.sas'
    source.write_text(text)
    output = area / 'late-cli'
    run, receipt = cli(source, output)
    need(run.returncode == 1 and receipt['accepted'] is False, 'late CLI refusal failed')
    need(not any((output / name).exists() for name in ('reports', 'exports', 'result.json', 'observed.json')),
         'late failure leaked a partial result or report artifact')


def main():
    with patch('tools.vendor_sources.urlopen', side_effect=AssertionError('fixture gate attempted network')):
        bound = verify_sources()[IDENTITY]
    original = bound['source'].read_bytes()
    need(len(original) == 1896 and digest(original) == SOURCE_SHA256, 'whole vendor source pin differs')
    license_bytes = bound['license'].read_bytes()
    need(digest(license_bytes) == bound['program']['license']['sha256'], 'license pin differs')
    expected, accounting, expected_trace = build(original)
    bodies = {'result.json': encode(expected), 'accounting.json': encode(accounting), 'trace.json': encode(expected_trace),
              **{name: text.encode('ascii') for name, text in expected['reports'].items()}}
    for name, expected_hash in FROZEN.items():
        need(digest(bodies[name]) == expected_hash, 'pre-engine frozen expectation changed: ' + name)
    with tempfile.TemporaryDirectory(prefix='saschi-vendor-sort-') as temporary:
        area = Path(temporary).resolve()
        need(not area.is_relative_to(ROOT), 'vendor bodies require external temporary storage')
        staged_source = area / 'original.sas'
        staged_source.write_bytes(original)
        reference = area / 'R'
        run = subprocess.run([os.environ.get('ROSETTA_RSCRIPT', 'Rscript'),
                              str(ROOT / 'examples/vendor_sorted_copy.R'), str(staged_source), str(reference)],
                             cwd=ROOT, capture_output=True, timeout=120)
        need(run.returncode == 0, 'independent whole-source R failed: ' + run.stderr.decode(errors='replace'))
        for name, body in bodies.items():
            need((reference / name).read_bytes() == body, 'independent whole-source hand/R bytes differ: ' + name)
        plan = compile_plan(original.decode('utf-8'))
        need(not plan.blocked and len(plan.steps) == 8 and len(plan.matched) == 14,
             'complete original was not fully admitted')
        # Legacy SORT records its header as one rule application. Its BY and RUN
        # remain separate language statements in the independent source count.
        need(sorted(line for _, _, line in plan.matched) == [line for line in LINES if line not in (44,45)],
             'compiled rule-application accounting differs')
        need(accounting['language_statements'] == 16 and accounting['opaque_payloads'] == 1,
             'independent complete-source accounting differs')
        actual, trace = traced_run(plan.to_dict())
        need(ordered_equal(actual, expected), 'whole runtime dataset/report outcome differs')
        need(ordered_equal(trace, expected_trace), 'actual source/runtime event schedule differs')
        need(len(trace) == 38 and accounting['input_attempts'] == 15, 'whole-program event accounting differs')
        emitted = translate(original.decode('utf-8'))
        need(not emitted.blocked, 'Python emission refused the complete original')
        environment = {}
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exec(emitted.code, environment)
        need(stdout.getvalue() == '' and ordered_equal(environment['result'], expected), 'emitted outcome/log differs')
        need(translate_cpp(original.decode('utf-8')).blocked, 'unadmitted C++ target did not refuse')
        expected_path, reports_path = area / 'expected.json', area / 'reports.json'
        expected_path.write_bytes(encode(expected['datasets']))
        reports_path.write_bytes(encode(expected['reports']))
        positive = area / 'accepted'
        accepted, receipt = cli(staged_source, positive, expected=expected_path, reports=reports_path)
        need(accepted.returncode == 0 and receipt['accepted'] is True and
             receipt['comparison'] == receipt['report_comparison'] == 'passed' and
             receipt['report_contract'] == mixed_reports.REPORT_CONTRACT, 'actual CLI full comparison failed')
        completeness = receipt['completeness']
        need([completeness[key] for key in ('n_statements','n_routed','n_unrouted','n_functions','n_tickets')]
             == [17,14,3,0,0], 'source catalog accounting differs from its declared units')
        need(ordered_equal(json.loads((positive / 'result.json').read_text()), expected), 'CLI full result differs')
        for name, text in expected['reports'].items():
            need((positive / 'reports' / name).read_bytes() == text.encode('ascii'), 'published report differs')
        wrong_datasets = []
        value = deepcopy(expected['datasets']); value['classtest']['schema']['name']['length'] = 8
        wrong_datasets.append(value)
        value = deepcopy(expected['datasets']); value['classtest_sort']['rows'][4:6] = reversed(value['classtest_sort']['rows'][4:6])
        wrong_datasets.append(value)
        value = deepcopy(expected['datasets']); value['classtest']['rows'][0]['name'] = 'Wrong  '
        wrong_datasets.append(value)
        wrong_reports = []
        for transform in [lambda t: t.split('\n', 1)[1], lambda t: t.replace('\n1 ', '\n15 ', 1),
                          lambda t: t.rstrip('\n'), lambda t: t.replace('"', '')]:
            value = deepcopy(expected['reports']); value['print_02.txt'] = transform(value['print_02.txt'])
            wrong_reports.append(value)
        value = deepcopy(expected['reports']); value['other.txt'] = value.pop('print_02.txt')
        wrong_reports.append(value)
        for index, value in enumerate(wrong_datasets):
            path = area / ('wrong-data-' + str(index) + '.json'); path.write_bytes(encode(value))
            output = area / ('wrong-data-' + str(index))
            failed, record = cli(staged_source, output, expected=path, reports=reports_path)
            need(failed.returncode == 1 and record['accepted'] is False and not (output / 'reports').exists(),
                 'wrong dataset comparator accepted or published report files')
        for index, value in enumerate(wrong_reports):
            path = area / ('wrong-report-' + str(index) + '.json'); path.write_bytes(encode(value))
            output = area / ('wrong-report-' + str(index))
            failed, record = cli(staged_source, output, expected=expected_path, reports=path)
            need(failed.returncode == 1 and record['accepted'] is False and not (output / 'reports').exists(),
                 'wrong report comparator accepted or published report files')
        broken = deepcopy(actual); broken['datasets']['classtest']['rows'][0]['name'] = 'Judy'
        need(not ordered_equal(broken, expected), 'raw stored padding comparator is weak')
        late_failure(area)
        need(staged_source.read_bytes() == original, 'original source changed during gate')
    with patch('tools.vendor_sources.urlopen', side_effect=AssertionError('fixture gate attempted network')):
        verify_sources()
    need(bound['source'].read_bytes() == original and bound['license'].read_bytes() == license_bytes,
         'pinned external originals changed during gate')
    print('VERIFIED vendor: ' + IDENTITY + '; unchanged1896bytes; independent whole hand/baseR; '
          '16statements+1opaque/14rows/15attempts/38events;2datasets/2exactreports375+402; '
          'actualCLI+8wrongcomparators+late-second-report-atomic; no live SAS or physical-layout claim')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
