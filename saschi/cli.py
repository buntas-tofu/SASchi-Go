"""Operator commands for inspection, translation, execution, and environment checks."""
from __future__ import annotations
import argparse
import json
import tempfile
from pathlib import Path
from . import __version__
from .emit_cpp import translate as cpp_translate
from .emit_py import translate as python_translate
from .job import build_job
from .plan import compile_plan
from .provenance import digest, environment
from .numeric_exchange import validate_exports


def write_json(path, value):
    # Preserve validation before opening the destination, without retaining
    # the complete encoded string. Job files still publish together by rename.
    encoder = json.JSONEncoder(indent=2, allow_nan=False)
    for chunk in encoder.iterencode(value):
        del chunk
    with path.open('w') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


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
    job = build_job(source, args.inputs, args.expect, expect_exports=getattr(args, 'expect_exports', None))
    receipt, result = job.receipt, job.result
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.saschi-', dir=output.parent) as temporary:
        staging = Path(temporary) / 'job'
        staging.mkdir()
        write_json(staging / 'plan.json', job.plan.to_dict())
        if result is not None:
            name = 'result.json' if receipt['accepted'] else 'observed.json'
            write_json(staging / name, result)
            receipt['result_sha256'] = digest(staging / name)
        if receipt['accepted'] and result is not None and 'exports' in result:
            validate_exports(result['exports'])
            export_directory = staging / 'exports'
            export_directory.mkdir()
            for name, text in result['exports'].items():
                with (export_directory / name).open('xb') as stream:
                    stream.write(text.encode('ascii'))
        write_json(staging / 'receipt.json', receipt)
        staging.rename(output)
    print(json.dumps({'accepted': receipt['accepted'], 'receipt': str(output / 'receipt.json')}))
    return job.code


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
    run.add_argument('--expect-exports', type=Path, help='compare the complete export basename-to-text map as exact UTF8 bytes')
    run.add_argument('--output', required=True, type=Path)
    tui = sub.add_parser('tui', help='open the rich console interface')
    tui.add_argument('source', nargs='?', type=Path)
    showcase = sub.add_parser('showcase', help='render a job as a self-contained showcase document')
    showcase.add_argument('source', type=Path)
    showcase.add_argument('--inputs', type=Path)
    showcase.add_argument('--expect', type=Path)
    showcase.add_argument('--target', choices=('python', 'cpp'), default='python')
    showcase.add_argument('--output', required=True, type=Path)
    showcase.add_argument('--name', default=None, help='document title (default: the source file name)')
    serve = sub.add_parser('serve', help='run the web workbench (standard library only)')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8070)
    serve.add_argument('--root', type=Path, default=None)
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
        if args.command == 'showcase':
            from .showcase import build_showcase
            source = args.source.read_text(encoding='utf-8')
            job = build_job(source, args.inputs, args.expect, args.target)
            name = args.name or args.source.stem
            html = build_showcase(job, name, args.source.name)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x') as handle:
                handle.write(html)
            print(json.dumps({'accepted': job.receipt['accepted'], 'showcase': str(args.output)}))
            return job.code
        if args.command == 'serve':
            from .web import main as serve_main
            argv = ['--host', args.host, '--port', str(args.port)]
            if args.root:
                argv += ['--root', str(args.root)]
            return serve_main(argv)
        return execute_job(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}))
        return 1
