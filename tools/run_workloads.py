#!/usr/bin/env python3
"""Exercise an original monthly ledger through the CLI and emitted Python.

Status: exploratory repository/base-R evidence for maintainer review, no live
SAS or production throughput claim. Existing verification gates are unchanged.
"""
from __future__ import annotations

import argparse
import copy
import csv
import datetime
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from saschi.compare import equal, table_equal
from saschi.provenance import digest, environment, source_state

FIXTURE = ROOT / 'examples/workloads/monthly_ledger'
ACCOUNT = {'type': 'number', 'label': 'Synthetic account'}
RAW_SCHEMA = {'account': ACCOUNT, 'period': 'number', 'seq': 'number',
              'include': 'number', 'amount': {'type': 'number', 'length': 8,
                                            'label': 'Usage units', 'format': 'BEST12.'}}
LOOKUP_SCHEMA = {'account': ACCOUNT, 'fee': {'type': 'number', 'label': 'Account adjustment'}}
JOINED_SCHEMA = {**RAW_SCHEMA, 'fee': LOOKUP_SCHEMA['fee']}
FINAL_SCHEMA = {'band': {'type': 'character', 'length': 4},
                'code': {'type': 'character', 'length': 6},
                'entry_kind': {'type': 'character', 'length': 5},
                'total': 'number', **JOINED_SCHEMA, 'previous': 'number',
                'change': 'number', 'adjusted': 'number'}
SCHEMAS = {'rounded': RAW_SCHEMA, 'ordered': RAW_SCHEMA, 'keys': LOOKUP_SCHEMA,
           'joined': JOINED_SCHEMA, 'snapshots': FINAL_SCHEMA}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def catalog(raw, lookup):
    return {name: {'label': label, 'encoding': 'ascii', 'schema': copy.deepcopy(schema), 'rows': rows}
            for name, label, schema, rows in (
                ('raw', 'Synthetic readings', RAW_SCHEMA, raw),
                ('lookup', 'Synthetic accounts', LOOKUP_SCHEMA, lookup))}


def tiny_catalog():
    records = [(2, 2, 5, 1, 10.5), (1, 1, 1, 1, 2.5),
               (1, 2, 2, 1, None), (1, 2, 3, 1, -1.5),
               (2, 1, 4, 1, 9.5), (1, 0, 0, 0, 999), (3, 1, 6, 1, 4.5)]
    return catalog([dict(zip(RAW_SCHEMA, row)) for row in records],
                   [{'account': 2, 'fee': -1}, {'account': 4, 'fee': 7}, {'account': 1, 'fee': 2}])


def fixed_rows():
    # Hand-calculated pins, independent of both implementations.
    records = [
        ('base', 'base-U', 'row  ', 3, 1, 1, 1, 1, 3, 2, None, None, 5),
        ('base', 'base-U', 'row  ', 3, 1, 2, 2, 1, 0, 2, 3, None, 2),
        ('base', 'base-U', 'row  ', 1, 1, 2, 3, 1, -2, 2, None, None, 0),
        ('base', 'base-U', 'close', 1, 1, 2, 3, 1, -2, 2, None, None, 0),
        ('high', 'high-U', 'row  ', 10, 2, 1, 4, 1, 10, -1, None, None, 9),
        ('high', 'high-U', 'row  ', 21, 2, 2, 5, 1, 11, -1, 10, 1, 10),
        ('high', 'high-U', 'close', 21, 2, 2, 5, 1, 11, -1, 10, 1, 10),
        ('base', 'base-U', 'row  ', 5, 3, 1, 6, 1, 5, None, None, None, None),
        ('base', 'base-U', 'close', 5, 3, 1, 6, 1, 5, None, None, None, None),
    ]
    return [dict(zip(FINAL_SCHEMA, row)) for row in records]


def generated_catalog(n, seed):
    rng = random.Random(seed)
    accounts = max(1, n // 12)
    raw = [{'account': rng.randrange(1, accounts + 1), 'period': rng.randrange(1, 13),
            'seq': i, 'include': int(rng.randrange(10) != 0),
            'amount': None if i % 17 == 0 else rng.randrange(-100, 501) / 2}
           for i in range(n)]
    lookup = [{'account': i, 'fee': i % 7 - 3} for i in range(1, accounts + 2) if i % 7 != 0]
    rng.shuffle(raw)
    rng.shuffle(lookup)
    return catalog(raw, lookup)


def dump_inputs(directory, inputs):
    write_json(directory / 'inputs.json', inputs)
    for name, table in inputs.items():
        with (directory / (name + '.csv')).open('w', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(table['schema'])
            writer.writerows(['NA' if row[col] is None else row[col] for col in table['schema']]
                             for row in table['rows'])


def r_expected(directory):
    expected = {}
    for name, schema in SCHEMAS.items():
        with (directory / 'r' / (name + '.csv')).open(newline='') as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(schema):
                raise ValueError(f'R column order differs for {name}: {reader.fieldnames}')
            rows = []
            for row in reader:
                rows.append({col: (value if isinstance(schema[col], dict) and
                                   schema[col]['type'] == 'character' else
                                   None if value == 'NA' else float(value))
                             for col, value in row.items()})
        expected[name] = {'label': 'Synthetic accounts' if name == 'keys' else 'Synthetic readings',
                          'encoding': 'ascii', 'schema': copy.deepcopy(schema), 'rows': rows}
    return expected


def invoke(directory, name, command, timeout):
    metrics = directory / (name + '.rss-kib.txt')
    measured = ['/usr/bin/time', '-f', '%M', '-o', str(metrics), *map(str, command)]
    start = time.perf_counter()
    try:
        run = subprocess.run(measured if Path('/usr/bin/time').exists() else command,
                             cwd=ROOT, text=True, capture_output=True, timeout=timeout,
                             env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(ROOT)})
        code, stdout, stderr = run.returncode, run.stdout, run.stderr
    except subprocess.TimeoutExpired as exc:
        code, stdout, stderr = 124, exc.stdout or '', exc.stderr or ''
        stdout = stdout.decode(errors='replace') if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode(errors='replace') if isinstance(stderr, bytes) else stderr
        stderr += '\nworkload process timed out'
    elapsed = time.perf_counter() - start
    (directory / (name + '.stdout.log')).write_text(stdout)
    (directory / (name + '.stderr.log')).write_text(stderr)
    rss = metrics.read_text().splitlines()[-1] if metrics.exists() and metrics.stat().st_size else ''
    return {'command': list(map(str, command)), 'returncode': code, 'seconds': elapsed,
            'peak_rss_kib': int(rss) if rss.isdigit() else None}


def emitted_worker(source, inputs, output):
    data = json.loads(Path(inputs).read_text())
    before = copy.deepcopy(data)
    namespace = {'inputs': data}
    exec(compile(Path(source).read_text(), str(source), 'exec'), namespace)
    if data != before:
        raise ValueError('emitted Python mutated its input catalog')
    write_json(Path(output), namespace['result'])


def run_case(output, name, inputs, rscript, timeout, emitted):
    directory = output / name
    directory.mkdir()
    dump_inputs(directory, inputs)
    record = {'name': name, 'input_rows': {n: len(t['rows']) for n, t in inputs.items()}, 'passed': False}
    try:
        record['r'] = invoke(directory, 'r', [rscript, FIXTURE / 'reference.R', directory, directory / 'r'], timeout)
        if record['r']['returncode']:
            raise ValueError('R witness failed; see r.stderr.log')
        expected = r_expected(directory)
        if name == 'hand-pinned' and not equal(expected['snapshots']['rows'], fixed_rows()):
            raise ValueError('independent R disagrees with hand-calculated nine-row pin')
        write_json(directory / 'expected.json', expected)
        record['cli'] = invoke(directory, 'cli', [sys.executable, '-m', 'saschi', 'run', FIXTURE / 'job.sas',
                                 '--inputs', directory / 'inputs.json', '--expect', directory / 'expected.json',
                                 '--output', directory / 'cli'], timeout)
        receipt = json.loads((directory / 'cli/receipt.json').read_text())
        record['job_receipt'] = receipt
        if record['cli']['returncode'] or not receipt['accepted'] or receipt['comparison'] != 'passed':
            raise ValueError('CLI refused or disagreed; see cli receipt and observed output')
        record['emitted'] = invoke(directory, 'emitted', [sys.executable, Path(__file__).resolve(), '--emitted-worker',
                                     emitted, directory / 'inputs.json', directory / 'emitted-result.json'], timeout)
        if record['emitted']['returncode']:
            raise ValueError('emitted Python failed; see emitted.stderr.log')
        actual = json.loads((directory / 'emitted-result.json').read_text())
        cli = json.loads((directory / 'cli/result.json').read_text())
        if not equal(actual, cli):
            raise ValueError('CLI and emitted Python complete results differ')
        for dataset, table in expected.items():
            if not table_equal(actual['datasets'].get(dataset), table):
                raise ValueError(f'emitted Python differs from R: {dataset}')
        for dataset, table in inputs.items():
            if not table_equal(actual['datasets'].get(dataset), table):
                raise ValueError(f'input dataset changed: {dataset}')
        record['output_rows'] = {n: len(t['rows']) for n, t in expected.items()}
        record['passed'] = True
    except (ValueError, OSError, KeyError) as exc:
        record['error'] = str(exc)
    write_json(directory / 'case.json', record)
    print(f"[{'PASS' if record['passed'] else 'FAIL'}] {name}: {record.get('error', record.get('output_rows'))}", flush=True)
    return record


def refusal_probes(output, timeout):
    source = (FIXTURE / 'job.sas').read_text()
    tiny = tiny_catalog()
    many = copy.deepcopy(tiny)
    many['lookup']['rows'].append({'account': 1, 'fee': 9})
    chars = copy.deepcopy(tiny)
    for table in chars.values():
        table['schema']['account'] = {'type': 'character', 'length': 3}
        for row in table['rows']:
            row['account'] = f"{row['account']:03d}"
    invalid = copy.deepcopy(tiny)
    invalid['raw']['rows'][-1]['amount'] = True
    specifications = [
        ('mixed-length-groups', source.replace('  length band $4;\n  length code $6;\n  length entry_kind $5;',
                                              '  length band $4 code $6 entry_kind $5;'), tiny, 2, 'unsupported'),
        ('grouped-do', source.replace("  if last.account then entry_kind='close';\n  if last.account then output;",
                                     "  if last.account then do;\n    entry_kind='close';\n    output;\n  end;"), tiny, 2, 'unsupported'),
        ('sum-statement', source.replace('total=total+amount;', 'total+amount;'), tiny, 2, 'unsupported'),
        ('many-to-many', source, many, 1, 'many-to-many MERGE'),
        ('character-merge', source, chars, 1, 'restricted to numeric'),
        ('catx-overflow', source.replace('code $6', 'code $5'), tiny, 1, 'CATX destination'),
        ('unsorted-merge', source.replace('proc sort data=rounded out=ordered;\n  by account period seq;\nrun;',
                                         'data ordered; set rounded; run;'), tiny, 1, 'ascending BY-sorted'),
        ('invalid-numeric', source, invalid, 1, 'finite SAS number'),
    ]
    results = []
    for name, program, inputs, code, error in specifications:
        directory = output / name
        directory.mkdir()
        write_json(directory / 'inputs.json', inputs)
        (directory / 'job.sas').write_text(program)
        process = invoke(directory, 'cli', [sys.executable, '-m', 'saschi', 'run', directory / 'job.sas',
                                          '--inputs', directory / 'inputs.json', '--output', directory / 'cli'], timeout)
        receipt_path = directory / 'cli/receipt.json'
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        passed = (process['returncode'] == code and receipt.get('accepted') is False and
                  error in receipt.get('error', '') and not (directory / 'cli/result.json').exists() and
                  not (directory / 'cli/observed.json').exists())
        record = {'name': name, 'passed': passed, 'expected_exit': code, 'expected_error': error,
                  'process': process, 'job_receipt': receipt}
        write_json(directory / 'case.json', record)
        results.append(record)
        print(f"[{'PASS' if passed else 'FAIL'}] refusal {name}: {receipt.get('error', 'missing receipt')}", flush=True)
    return results


def comparator_probes(output, expected, timeout):
    results = []
    for name in ('changed-value', 'changed-width'):
        directory = output / name
        directory.mkdir()
        altered = copy.deepcopy(expected)
        if name == 'changed-value':
            altered['snapshots']['rows'][0]['total'] += 1
        else:
            altered['snapshots']['schema']['code']['length'] = 7
        write_json(directory / 'expected.json', altered)
        process = invoke(directory, 'cli', [sys.executable, '-m', 'saschi', 'run', FIXTURE / 'job.sas',
                                          '--inputs', output / 'hand-pinned/inputs.json', '--expect', directory / 'expected.json',
                                          '--output', directory / 'cli'], timeout)
        receipt_path = directory / 'cli/receipt.json'
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        passed = (process['returncode'] == 1 and receipt.get('accepted') is False and
                  receipt.get('comparison') == 'failed' and (directory / 'cli/observed.json').is_file() and
                  not (directory / 'cli/result.json').exists())
        record = {'name': name, 'passed': passed, 'process': process, 'job_receipt': receipt}
        write_json(directory / 'case.json', record)
        results.append(record)
        print(f"[{'PASS' if passed else 'FAIL'}] comparator {name}", flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--sizes', type=int, nargs='+', default=[1000, 10000, 50000])
    parser.add_argument('--seed', type=int, default=20261025)
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    if any(n < 1 or n > 100000 for n in args.sizes) or args.timeout < 1:
        parser.error('sizes must be 1..100000 and timeout must be positive')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rscript = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript')
    if not rscript:
        raise RuntimeError('base R is required; no workload case may skip its witness')
    before = source_state(ROOT)
    report = {'status': 'Exploratory repository/base-R workload evidence for maintainer review; no live SAS or production throughput claim.',
              'ts_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source': before,
              'environment': environment(), 'seed': args.seed, 'sizes': args.sizes,
              'comparison': 'typed exact values, ordered rows and columns, descriptors and table metadata; five generated tables',
              'measurement': 'one fresh process per path per case, startup and file I/O included; peak RSS in KiB on Linux',
              'source_program_sha256': digest(FIXTURE / 'job.sas'), 'r_witness_sha256': digest(FIXTURE / 'reference.R')}
    translation = invoke(output, 'translate', [sys.executable, '-m', 'saschi', 'translate', FIXTURE / 'job.sas',
                                               '--target', 'python', '--output', output / 'emitted.py'], args.timeout)
    report['translation'] = translation
    if translation['returncode']:
        report['all_passed'] = False
        write_json(output / 'report.json', report)
        print(f"WORKLOAD TRANSLATION REFUSED -> {output / 'translate.stdout.log'}", flush=True)
        return 1
    tiny = tiny_catalog()
    filtered = copy.deepcopy(tiny)
    for row in filtered['raw']['rows']:
        row['include'] = 0
    no_lookup = copy.deepcopy(tiny)
    no_lookup['lookup']['rows'] = []
    cases = [('hand-pinned', tiny), ('both-empty', catalog([], [])),
             ('empty-readings', catalog([], tiny['lookup']['rows'])), ('all-filtered', filtered),
             ('no-lookup', no_lookup),
             ('singleton-zero', catalog([{'account': 1, 'period': 1, 'seq': 1, 'include': 1, 'amount': 0}],
                                        [{'account': 1, 'fee': 2}]))]
    cases.extend((f'scale-{n}', generated_catalog(n, args.seed)) for n in dict.fromkeys(args.sizes))
    report['cases'] = [run_case(output, name, inputs, rscript, args.timeout, output / 'emitted.py')
                       for name, inputs in cases]
    report['refusals'] = refusal_probes(output, args.timeout)
    pin = output / 'hand-pinned/expected.json'
    report['comparator_controls'] = comparator_probes(output, json.loads(pin.read_text()), args.timeout) if pin.exists() else []
    after = source_state(ROOT)
    report['source_stable'] = before['source_sha256'] == after['source_sha256']
    records = report['cases'] + report['refusals'] + report['comparator_controls']
    report['all_passed'] = report['source_stable'] and len(report['comparator_controls']) == 2 and all(r['passed'] for r in records)
    report['artifact_sha256'] = {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
    write_json(output / 'report.json', report)
    print(f"{'ALL WORKLOAD CHECKS PASSED' if report['all_passed'] else 'WORKLOAD FINDINGS'} -> {output / 'report.json'}")
    return 0 if report['all_passed'] else 1


if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == '--emitted-worker':
        emitted_worker(*sys.argv[2:])
    else:
        raise SystemExit(main())
