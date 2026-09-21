"""Operator commands for inspection, translation, execution, and environment checks."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from . import __version__
from .emit_py import translate as python_translate
from .emit_cpp import translate as cpp_translate
from .plan import compile_plan
from .provenance import digest, environment, implementation_hashes
from .runtime import run_plan
from .compare import table_equal


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def doctor():
    info = environment()
    missing = [name for name, version in info['packages'].items() if version is None]
    if not info['r_version']:
        missing.append('Rscript')
    if not info['cpp_version']:
        missing.append('C++17 compiler')
    info['missing'] = missing
    print(json.dumps(info, indent=2))
    return 1 if missing else 0


def execute_job(args):
    output = args.output.resolve()
    if output.exists():
        raise ValueError(f'output directory already exists: {output}')
    source = args.source.read_text(encoding='utf-8')
    plan = compile_plan(source)
    receipt = {'schema_version': 1, 'package_version': __version__,
               'ts_utc': datetime.now(timezone.utc).isoformat(), 'target': 'python',
               'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(), 'environment': environment(),
               'implementation_sha256': implementation_hashes(),
               'evidence': 'repository behavior contracts; no live SAS',
               'plan_sha256': hashlib.sha256(json.dumps(plan.to_dict(), sort_keys=True).encode()).hexdigest(),
               'tickets': [vars(t) for t in plan.tickets], 'accepted': False,
               'comparison': 'not requested', 'comparison_contract': 'typed-exact-values-ordered-rows-and-columns-metadata-v1'}
    result, code = None, 2 if plan.blocked else 1
    try:
        if plan.blocked:
            raise ValueError('translation blocked by unsupported statements')
        input_bytes = args.inputs.read_bytes() if args.inputs else None
        catalog = json.loads(input_bytes) if input_bytes is not None else {}
        receipt['input_sha256'] = hashlib.sha256(input_bytes).hexdigest() if input_bytes is not None else None
        result = run_plan(plan.to_dict(), catalog)
        if args.expect:
            expected_bytes = args.expect.read_bytes()
            expected = json.loads(expected_bytes)
            receipt['expected_sha256'] = hashlib.sha256(expected_bytes).hexdigest()
            if not isinstance(expected, dict) or not expected:
                raise ValueError('expected output must name at least one dataset')
            for name, table in expected.items():
                if not table_equal(result['datasets'].get(name), table):
                    receipt['comparison'] = 'failed'
                    raise ValueError(f'expected dataset differs: {name}')
            receipt['comparison'] = 'passed'
        receipt['accepted'], code = True, 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        receipt['error'] = str(exc)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.saschi-', dir=output.parent) as temporary:
        staging = Path(temporary) / 'job'
        staging.mkdir()
        write_json(staging / 'plan.json', plan.to_dict())
        if result is not None:
            name = 'result.json' if receipt['accepted'] else 'observed.json'
            write_json(staging / name, result)
            receipt['result_sha256'] = digest(staging / name)
        write_json(staging / 'receipt.json', receipt)
        staging.rename(output)
    print(json.dumps({'accepted': receipt['accepted'], 'receipt': str(output / 'receipt.json')}))
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(prog='saschi')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor', help='check the complete verification environment')
    inspect = sub.add_parser('inspect', help='show operations, dependencies, and review tickets')
    inspect.add_argument('source', type=Path)
    translate = sub.add_parser('translate', help='emit a checked target or a blocked inspection artifact')
    translate.add_argument('source', type=Path)
    translate.add_argument('--target', choices=('python', 'cpp'), default='python')
    translate.add_argument('--output', required=True, type=Path)
    run = sub.add_parser('run', help='execute a bounded typed dataset workflow and write a receipt')
    run.add_argument('source', type=Path)
    run.add_argument('--inputs', type=Path)
    run.add_argument('--expect', type=Path)
    run.add_argument('--output', required=True, type=Path)
    tui = sub.add_parser('tui', help='open the rich console interface')
    tui.add_argument('source', nargs='?', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'doctor':
            return doctor()
        if args.command == 'inspect':
            plan = compile_plan(args.source.read_text(encoding='utf-8'))
            print(json.dumps(plan.to_dict(), indent=2, allow_nan=False))
            return 2 if plan.blocked else 0
        if args.command == 'translate':
            source = args.source.read_text(encoding='utf-8')
            translation = (python_translate if args.target == 'python' else cpp_translate)(source)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation protects an existing source or generated program.
            with args.output.open('x') as handle:
                handle.write(translation.code)
            print(json.dumps({'blocked': translation.blocked, 'tickets': [vars(t) for t in translation.tickets]}))
            return 2 if translation.blocked else 0
        if args.command == 'tui':
            try:
                from .tui import main as tui_main
            except ImportError:
                print(json.dumps({'error': 'the rich package is required for the interface: pip install "rich>=13,<14"'}))
                return 1
            return tui_main([] if args.source is None else [str(args.source)])
        return execute_job(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}))
        return 1
