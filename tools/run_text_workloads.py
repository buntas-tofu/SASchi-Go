#!/usr/bin/env python3
"""Exercise original character-heavy, short-group workloads with base R.

Status: exploratory repository/base-R evidence for maintainer review, no live
SAS or production throughput claim. Existing verification gates are unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import csv
import datetime
import json
import os
from pathlib import Path
import random
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from saschi.cli import write_json
from saschi.compare import equal, table_equal
from saschi.provenance import digest, environment, source_state
from tools.run_workloads import dump_inputs, emitted_worker, invoke

FIXTURE = ROOT / 'examples/workloads/grouped_text'
RAW_SCHEMA = {
    'team': {'type': 'character', 'length': 12, 'label': 'Synthetic group'},
    'seq': 'number', 'include': 'number',
    'payload': {'type': 'character', 'length': 128, 'label': 'Fixed text'},
    'tag': {'type': 'character', 'length': 24},
    'note': {'type': 'character', 'length': 64, 'label': 'Source note'},
    'value': {'type': 'number', 'label': 'Event units'},
}
PREPARED_SCHEMA = {
    'short': {'type': 'character', 'length': 8},
    'combined': {'type': 'character', 'length': 40}, **RAW_SCHEMA,
    'actual_len': 'number', 'storage_len': 'number',
    'backwards': {'type': 'character', 'length': 128},
}
FINAL_SCHEMA = {'entry_kind': {'type': 'character', 'length': 5},
                'total': 'number', 'n_in_group': 'number', **PREPARED_SCHEMA}
SCHEMAS = {'raw': RAW_SCHEMA, 'ordered': RAW_SCHEMA,
           'prepared': PREPARED_SCHEMA, 'snapshots': FINAL_SCHEMA}
LABEL = 'Synthetic text events'


def catalog(rows):
    return {'raw': {'label': LABEL, 'encoding': 'ascii',
                    'schema': copy.deepcopy(RAW_SCHEMA), 'rows': rows}}


def tiny_catalog():
    records = [
        ('B', 2, 1, ' abcdefghZ', 't', 'quote ", comma', 3),
        ('A', 1, 1, 'Alpha, "Z"', ' red ', 'NA', 2),
        ('A', 1, 1, 'beta', '', 'same-key', None),
        (' ', 1, 1, '', 'NA', '', -1),
        ('B', 1, 0, 'ignored', 'x', 'excluded', 999),
        ('A', 2, 0, 'excluded', 'x', 'excluded', 999),
        ('C', 1, 1, 'NA', '   ', 'literal NA', 0),
        ('B', 3, 1, 'x' * 128, 't' * 24, 'n' * 64, 1),
    ]
    return catalog([dict(zip(RAW_SCHEMA, row)) for row in records])


def fixed_rows():
    # Ten hand-calculated snapshots, independent of the R and Python engines.
    records = [
        (-1, 1, '        ', 'NA', ' ', 1, '', 'NA', '', -1, 0, ' ' * 128),
        (2, 1, 'Alpha, "', 'red|Alpha, "', 'A', 1, 'Alpha, "Z"', ' red ', 'NA', 2, 10,
         ' ' * 118 + '"Z" ,ahplA'),
        (2, 2, 'beta    ', 'beta', 'A', 1, 'beta', '', 'same-key', 0, 4,
         ' ' * 124 + 'ateb'),
        (3, 1, ' abcdefg', 't|abcdefg', 'B', 2, ' abcdefghZ', 't', 'quote ", comma', 3, 10,
         ' ' * 118 + 'Zhgfedcba '),
        (4, 2, 'x' * 8, 't' * 24 + '|' + 'x' * 8, 'B', 3, 'x' * 128,
         't' * 24, 'n' * 64, 1, 128, 'x' * 128),
        (0, 1, 'NA      ', 'NA', 'C', 1, 'NA', '   ', 'literal NA', 0, 2,
         ' ' * 126 + 'AN'),
    ]
    result = []
    for i, (total, position, short, combined, team, seq, payload, tag, note, value, size, backwards) in enumerate(records):
        row = dict(zip(FINAL_SCHEMA, ('row  ', total, position, short, combined.ljust(40),
                   team.ljust(12), seq, 1, payload.ljust(128), tag.ljust(24), note.ljust(64),
                   value, size, 128, backwards)))
        result.append(row)
        if i in (0, 2, 4, 5):
            result.append({**row, 'entry_kind': 'close'})
    return result


def generated_catalog(n, seed):
    rng = random.Random(seed)
    rows, group = [], 0
    while len(rows) < n:
        for member in range(1 + group % 3):
            i = len(rows)
            if i == n:
                break
            text = f'event-{i:06d}, "sample" | '
            payload = (text * 8)[:128 - i % 7]
            if i % 17 == 0:
                payload = ''
            elif i % 17 == 1:
                payload = 'NA'
            elif i % 17 == 2:
                payload = '  lead, "quote"  '
            tag = ('', 'NA', ' tag ', 't' * 24, f'tag-{i:06d}')[i % 5]
            rows.append(dict(zip(RAW_SCHEMA, (f'T{group:07d}', member // 2,
                        int(i % 11 != 0), payload, tag, (text * 4)[:64],
                        None if i % 13 == 0 else i % 11 - 5))))
        group += 1
    rng.shuffle(rows)
    return catalog(rows)


def r_expected(directory):
    expected = {}
    for name, schema in SCHEMAS.items():
        with (directory / 'r' / (name + '.csv')).open(newline='') as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(schema):
                raise ValueError(f'R column order differs for {name}: {reader.fieldnames}')
            rows = []
            for row in reader:
                rows.append({col: (value if isinstance(schema[col], dict) and schema[col]['type'] == 'character'
                                   else None if value == 'NA' else float(value))
                             for col, value in row.items()})
        expected[name] = {'label': LABEL, 'encoding': 'ascii',
                          'schema': copy.deepcopy(schema), 'rows': rows}
    return expected


def run_case(output, name, inputs, rscript, timeout, emitted):
    directory = output / name
    directory.mkdir()
    dump_inputs(directory, inputs)
    groups = Counter(row['team'].ljust(12) for row in inputs['raw']['rows'])
    record = {'name': name, 'input_rows': len(inputs['raw']['rows']),
              'input_groups': len(groups), 'largest_input_group': max(groups.values(), default=0), 'passed': False}
    try:
        record['r'] = invoke(directory, 'r', [rscript, FIXTURE / 'reference.R', directory, directory / 'r'], timeout)
        if record['r']['returncode']:
            raise ValueError('R witness failed; see r.stderr.log')
        expected = r_expected(directory)
        if name == 'hand-pinned' and not equal(expected['snapshots']['rows'], fixed_rows(), ordered_maps=True):
            raise ValueError('independent R disagrees with hand-calculated ten-row pin')
        write_json(directory / 'expected.json', expected)
        record['cli'] = invoke(directory, 'cli', [sys.executable, '-m', 'saschi', 'run', FIXTURE / 'job.sas',
                                 '--inputs', directory / 'inputs.json', '--expect', directory / 'expected.json',
                                 '--output', directory / 'cli'], timeout)
        receipt = json.loads((directory / 'cli/receipt.json').read_text())
        record['job_receipt'] = receipt
        if record['cli']['returncode'] or not receipt['accepted'] or receipt['comparison'] != 'passed':
            raise ValueError('CLI refused or disagreed; inspect receipt and observed output')
        record['emitted'] = invoke(directory, 'emitted', [sys.executable, Path(__file__).resolve(), '--emitted-worker',
                                     emitted, directory / 'inputs.json', directory / 'emitted-result.json'], timeout)
        if record['emitted']['returncode']:
            raise ValueError('emitted Python failed; see emitted.stderr.log')
        actual = json.loads((directory / 'emitted-result.json').read_text())
        cli = json.loads((directory / 'cli/result.json').read_text())
        if not equal(actual, cli, ordered_maps=True):
            raise ValueError('CLI and emitted Python complete results differ')
        for dataset, table in expected.items():
            if not table_equal(actual['datasets'].get(dataset), table):
                raise ValueError(f'emitted Python differs from R: {dataset}')
        record['output_rows'] = {n: len(t['rows']) for n, t in expected.items()}
        record['passed'] = True
    except (ValueError, OSError, KeyError, TypeError) as exc:
        record['error'] = str(exc)
    write_json(directory / 'case.json', record)
    print(f"[{'PASS' if record['passed'] else 'FAIL'}] {name}: {record.get('error', record.get('output_rows'))}", flush=True)
    return record


def refusal_probes(output, timeout):
    source = (FIXTURE / 'job.sas').read_text()
    tiny = tiny_catalog()
    overlong = copy.deepcopy(tiny)
    overlong['raw']['rows'][0]['payload'] = 'x' * 129
    invalid = copy.deepcopy(tiny)
    invalid['raw']['rows'][0]['value'] = True
    nonascii = copy.deepcopy(tiny)
    nonascii['raw']['encoding'] = 'utf-8'
    nonascii['raw']['rows'][0]['note'] = '\u00e9'
    specs = [
        ('overlong-input', source, overlong, 1, 'input exceeds declared character length'),
        ('invalid-numeric', source, invalid, 1, 'finite SAS number'),
        ('key-width-change', source.replace('  length entry_kind $5;', '  length entry_kind $5;\n  length team $8;'), tiny, 1, 'BY key width changes'),
        ('catx-overflow', source.replace('combined $40', 'combined $1'), tiny, 1, 'CATX destination'),
        ('unsorted-by', source.replace('proc sort data=raw out=ordered;\n  by team seq;\nrun;',
                                       'data ordered; set raw; run;'), tiny, 1, 'SET BY requires ascending sorted rows'),
        ('non-ascii-reverse', source.replace('backwards=reverse(payload);', 'backwards=reverse(note);'), nonascii, 1, 'REVERSE'),
        ('grouped-do', source.replace("  if last.team then entry_kind='close';\n  if last.team then output;",
                                     "  if last.team then do;\n    entry_kind='close';\n    output;\n  end;"), tiny, 2, 'unsupported'),
    ]
    records = []
    for name, program, inputs, code, error in specs:
        d = output / name
        d.mkdir()
        write_json(d / 'inputs.json', inputs)
        (d / 'job.sas').write_text(program)
        process = invoke(d, 'cli', [sys.executable, '-m', 'saschi', 'run', d / 'job.sas',
                          '--inputs', d / 'inputs.json', '--output', d / 'cli'], timeout)
        receipt_path = d / 'cli/receipt.json'
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        passed = (process['returncode'] == code and receipt.get('accepted') is False and
                  error in receipt.get('error', '') and not (d / 'cli/result.json').exists() and
                  not (d / 'cli/observed.json').exists())
        record = {'name': name, 'passed': passed, 'expected_exit': code, 'expected_error': error,
                  'process': process, 'job_receipt': receipt}
        write_json(d / 'case.json', record)
        records.append(record)
        print(f"[{'PASS' if passed else 'FAIL'}] refusal {name}: {receipt.get('error', 'missing receipt')}", flush=True)
    return records


def comparator_probes(output, expected, timeout):
    records = []
    for name in ('changed-value', 'changed-width', 'changed-order', 'changed-padding', 'changed-schema-order', 'changed-label'):
        d = output / name
        d.mkdir()
        altered = copy.deepcopy(expected)
        if name == 'changed-value':
            altered['snapshots']['rows'][0]['total'] += 1
        elif name == 'changed-width':
            altered['prepared']['schema']['short']['length'] = 9
        elif name == 'changed-order':
            rows = altered['snapshots']['rows']
            rows[2], rows[3] = rows[3], rows[2]
        elif name == 'changed-padding':
            altered['prepared']['rows'][0]['payload'] = ''
        elif name == 'changed-schema-order':
            altered['ordered']['schema'] = dict(reversed(list(altered['ordered']['schema'].items())))
        else:
            altered['prepared']['label'] = 'Changed label'
        write_json(d / 'expected.json', altered)
        process = invoke(d, 'cli', [sys.executable, '-m', 'saschi', 'run', FIXTURE / 'job.sas',
                          '--inputs', output / 'hand-pinned/inputs.json', '--expect', d / 'expected.json',
                          '--output', d / 'cli'], timeout)
        path = d / 'cli/receipt.json'
        receipt = json.loads(path.read_text()) if path.exists() else {}
        passed = (process['returncode'] == 1 and receipt.get('accepted') is False and
                  receipt.get('comparison') == 'failed' and (d / 'cli/observed.json').is_file() and
                  not (d / 'cli/result.json').exists())
        record = {'name': name, 'passed': passed, 'process': process, 'job_receipt': receipt}
        write_json(d / 'case.json', record)
        records.append(record)
        print(f"[{'PASS' if passed else 'FAIL'}] comparator {name}", flush=True)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--sizes', nargs='+', type=int, default=[1000, 10000, 50000])
    parser.add_argument('--seed', type=int, default=20261026)
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    if any(n < 1 or n > 100000 for n in args.sizes) or args.timeout < 1:
        parser.error('sizes must be 1..100000 and timeout must be positive')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = source_state(ROOT)
    report = {'status': 'Exploratory repository/base-R character workload evidence for maintainer review; no live SAS or production throughput claim.',
              'ts_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source': before,
              'environment': environment(), 'seed': args.seed, 'sizes': args.sizes,
              'comparison': 'typed exact values, row/column order, descriptors, padding and table metadata; normalized input and three generated tables',
              'measurement': 'one fresh R/CLI/emitted process per case, startup and I/O included; Linux peak RSS in KiB',
              'input_character_storage_bytes_per_row': 228, 'generated_group_size_range': [1, 3],
              'source_program_sha256': digest(FIXTURE / 'job.sas'), 'r_witness_sha256': digest(FIXTURE / 'reference.R')}
    rscript = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript')
    if not rscript:
        report.update(all_passed=False, error='base R is required; no workload case may skip its witness',
                      source_stable=before['source_sha256'] == source_state(ROOT)['source_sha256'],
                      cases=[], refusals=[], comparator_controls=[])
        write_json(output / 'report.json', report)
        print(f"WORKLOAD ENVIRONMENT FAILED -> {output / 'report.json'}", flush=True)
        return 1
    report['translation'] = invoke(output, 'translate', [sys.executable, '-m', 'saschi', 'translate', FIXTURE / 'job.sas',
                                          '--target', 'python', '--output', output / 'emitted.py'], args.timeout)
    if report['translation']['returncode']:
        report['all_passed'] = False
        write_json(output / 'report.json', report)
        print(f"WORKLOAD TRANSLATION REFUSED -> {output / 'translate.stdout.log'}", flush=True)
        return 1
    tiny = tiny_catalog()
    filtered = copy.deepcopy(tiny)
    for row in filtered['raw']['rows']:
        row['include'] = 0
    singletons = generated_catalog(12, args.seed)
    for i, row in enumerate(singletons['raw']['rows']):
        row.update(team=f'S{i:07d}', include=1)
    ties = catalog([dict(zip(RAW_SCHEMA, ('tie', 1, 1, text, 'NA', 'same key', i)))
                    for i, text in enumerate(('first', 'second', 'third', 'fourth'))])
    cases = [('hand-pinned', tiny), ('empty', catalog([])), ('all-filtered', filtered),
             ('blank-values', catalog([dict(zip(RAW_SCHEMA, ('', 1, 1, '', '', '', None)))])),
             ('singleton-groups', singletons), ('duplicate-keys', ties),
             ('max-width', catalog([dict(zip(RAW_SCHEMA, ('g' * 12, 1, 1, 'x' * 128, 't' * 24, 'n' * 64, 0)))]))]
    cases.extend((f'scale-{n}', generated_catalog(n, args.seed)) for n in dict.fromkeys(args.sizes))
    report['cases'] = [run_case(output, name, inputs, rscript, args.timeout, output / 'emitted.py') for name, inputs in cases]
    report['refusals'] = refusal_probes(output, args.timeout)
    pin = output / 'hand-pinned/expected.json'
    report['comparator_controls'] = comparator_probes(output, json.loads(pin.read_text()), args.timeout) if pin.exists() else []
    report['source_stable'] = before['source_sha256'] == source_state(ROOT)['source_sha256']
    records = report['cases'] + report['refusals'] + report['comparator_controls']
    report['all_passed'] = (report['source_stable'] and len(report['refusals']) == 7 and
                            len(report['comparator_controls']) == 6 and all(r['passed'] for r in records))
    report['artifact_sha256'] = {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
    write_json(output / 'report.json', report)
    print(f"{'ALL WORKLOAD CHECKS PASSED' if report['all_passed'] else 'WORKLOAD FINDINGS'} -> {output / 'report.json'}")
    return 0 if report['all_passed'] else 1


if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == '--emitted-worker':
        emitted_worker(*sys.argv[2:])
    else:
        raise SystemExit(main())
