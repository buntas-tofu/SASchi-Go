#!/usr/bin/env python3
"""Build and run the current tree's wheel offline, away from the checkout.

Maintainer packaging evidence, not live SAS verification. Build tools belong
to the verify profile; the installed wheel must execute with standard library
alone. No global installation, editable import, or source-checkout fallback.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent

SMOKE = r'''
import contextlib
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import sys

# -I -S disables user paths, PYTHONPATH, and every installed site package.
installed = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(installed))
import saschi
import sas_semantics
from saschi.emit_py import translate
from saschi.rules import load_rulebook, RULEBOOK_DEFAULT
from saschi.cli import main

for module in (saschi, sas_semantics):
    assert Path(module.__file__).resolve().is_relative_to(installed)
assert RULEBOOK_DEFAULT.resolve() == installed / 'saschi/data/sasconversionrulebook.json'
assert hashlib.sha256(RULEBOOK_DEFAULT.read_bytes()).hexdigest() == sys.argv[2]
for relative, expected in json.loads(sys.argv[3]).items():
    assert hashlib.sha256((installed / relative).read_bytes()).hexdigest() == expected
entry, = [e for e in importlib.metadata.distribution('saschi-go').entry_points
          if e.group == 'console_scripts' and e.name == 'saschi']
assert entry.load() is main
source = "data d; length c $5; c='plus'; if mod(-7,3)=-1 then c='minus'; put '[' c ']'; run;"
translation = translate(source)
assert not translation.blocked, translation.tickets
namespace = {}
printed = io.StringIO()
with contextlib.redirect_stdout(printed):
    exec(translation.code, namespace)
assert printed.getvalue() == '[minus ]\n'
assert namespace['result'] == {
    'datasets': {'d': {'schema': {'c': {'type': 'character', 'length': 5}},
                      'rows': [{'c': 'minus'}]}}, 'log': ['[minus ]']}
calendar = translate('data d; x=mdy(1,1,1960); w=weekday(x); run;')
assert not calendar.blocked, calendar.tickets
namespace = {}
exec(calendar.code, namespace)
assert namespace['result'] == {'datasets': {'d': {
    'schema': {'x': 'number', 'w': 'number'}, 'rows': [{'x': 0., 'w': 6.}]}}, 'log': []}
loop = translate('data d; do until(n=3); n+1; end; run;')
assert not loop.blocked, loop.tickets
namespace = {}
exec(loop.code, namespace)
assert namespace['result'] == {'datasets': {'d': {
    'schema': {'n': 'number'}, 'rows': [{'n': 3.}]}}, 'log': []}
loop = translate('data d; n=8; do while(n>0); n=int(n/2); end; run;')
assert not loop.blocked, loop.tickets
namespace = {}
exec(loop.code, namespace)
assert namespace['result'] == {'datasets': {'d': {
    'schema': {'n': 'number'}, 'rows': [{'n': 0.}]}}, 'log': []}
array = translate('data d; array a[0:1] x y; a[0]=3; y=4; t=sum(of a[*]); run;')
assert not array.blocked, array.tickets
namespace = {}
exec(array.code, namespace)
assert namespace['result'] == {'datasets': {'d': {
    'schema': {'x': 'number', 'y': 'number', 't': 'number'},
    'rows': [{'x': 3., 'y': 4., 't': 7.}]}}, 'log': []}
assert main(['inspect', sys.argv[4]]) == 0
over = translate('data d; array a x y; n=1; do over a; a=n; n=n+1; end; run;')
assert not over.blocked, over.tickets
namespace = {}
exec(over.code, namespace)
assert namespace['result'] == {'datasets': {'d': {
    'schema': {'x': 'number', 'y': 'number', 'n': 'number'},
    'rows': [{'x': 1., 'y': 2., 'n': 3.}]}}, 'log': []}
nested = translate('data d; n=2; total=0; do i=1 to n; do j=i to n; total=total+j; end; end; run;')
assert not nested.blocked, nested.tickets
namespace = {}
exec(nested.code, namespace)
assert namespace['result'] == {'datasets': {'d': {
    'schema': {'n': 'number', 'total': 'number', 'i': 'number', 'j': 'number'},
    'rows': [{'n': 2., 'total': 5., 'i': 3., 'j': 3.}]}}, 'log': []}
mixed = translate("data d; do i=1 to 2; do j=1 to i; put '[' i j ']'; end; end; run;")
assert not mixed.blocked, mixed.tickets
namespace = {}; printed = io.StringIO()
with contextlib.redirect_stdout(printed):
    exec(mixed.code, namespace)
assert printed.getvalue() == '[1 1 ]\n[2 1 ]\n[2 2 ]\n'
assert namespace['result'] == {'datasets': {'d': {
    'schema': {'i': 'number', 'j': 'number'}, 'rows': [{'i': 3., 'j': 3.}]}},
    'log': ['[1 1 ]', '[2 1 ]', '[2 2 ]']}
trimmed = translate("data d; length a $4; do i=1 to 2; a=strip(a)||'*'; output; end; b='['||trim(' ')||']'; c='['||strip(' ')||']'; output; run;")
assert not trimmed.blocked, trimmed.tickets
namespace = {}
exec(trimmed.code, namespace)
assert namespace['result'] == {'datasets': {'d': {
    'schema': {'a': {'type': 'character', 'length': 4}, 'i': 'number',
               'b': {'type': 'character', 'length': 3}, 'c': {'type': 'character', 'length': 3}},
    'rows': [{'a': '*   ', 'i': 1., 'b': '   ', 'c': '   '},
             {'a': '**  ', 'i': 2., 'b': '   ', 'c': '   '},
             {'a': '**  ', 'i': 3., 'b': '[ ]', 'c': '[] '}]}}, 'log': []}
inline = translate('data d; input a b; seq=_n_; datalines;\n1\n2 99\n. 4\n5\n;\nrun;')
assert not inline.blocked, inline.tickets
namespace = {}
exec(inline.code, namespace)
assert namespace['result'] == {'datasets': {'d': {
    'schema': {'a': 'number', 'b': 'number', 'seq': 'number'},
    'rows': [{'a': 1., 'b': 2., 'seq': 1.}, {'a': None, 'b': 4., 'seq': 2.}]}}, 'log': []}
multiplied = translate('data d;array a{2} x y;x=3;y=4;a[1]=x*y;p=a[1]*a[2];put p unseen;run;')
assert not multiplied.blocked, multiplied.tickets
namespace = {}
exec(multiplied.code, namespace)
assert namespace['result'] == {'datasets': {'d': {
    'schema': {'x': 'number', 'y': 'number', 'p': 'number', 'unseen': 'number'},
    'rows': [{'x': 12., 'y': 4., 'p': 48., 'unseen': None}]}}, 'log': ['48 . ']}
print('VERIFIED: isolated installed wheel, canonical rulebook, all web assets, CLI entry point, MOD-to-PUT output, calendar, sum/UNTIL, division/INT/WHILE and numeric inline INPUT and exact multiplication/output discovery')
'''


def run(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"wheel smoke subprocess failed ({result.returncode})\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main():
    with tempfile.TemporaryDirectory(prefix='saschi-wheel-') as directory:
        root = Path(directory)
        source = root / 'source'
        source.mkdir()
        # Use current file bytes, including uncommitted changes, not HEAD or a
        # stale build directory. The explicit build inputs exclude telemetry.
        for name in ('pyproject.toml', 'setup.py', 'MANIFEST.in', 'README.md', 'LICENSE', 'sas_semantics.py'):
            shutil.copy2(ROOT / name, source / name)
        shutil.copytree(ROOT / 'saschi', source / 'saschi',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        (source / 'docs').mkdir()
        for name in ('sasconversionrulebook.json', 'capability-manifest.json'):
            shutil.copy2(ROOT / 'docs' / name, source / 'docs' / name)
        wheels = root / 'wheels'
        wheels.mkdir()
        run([sys.executable, '-I', '-c',
             'import setuptools.build_meta as backend; import sys; backend.build_wheel(sys.argv[1])',
             str(wheels)], source)
        wheel, = wheels.glob('*.whl')
        installed = root / 'installed'
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(installed)
        rulebook = hashlib.sha256((ROOT / 'docs/sasconversionrulebook.json').read_bytes()).hexdigest()
        assets = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted((ROOT / 'saschi/web/static').iterdir()) if p.is_file()}
        assert assets, 'no web assets found'
        program = root / 'smoke.sas'
        program.write_text('data d; x=mod(-7,3); run;')
        print(run([sys.executable, '-I', '-S', '-c', SMOKE, str(installed), rulebook,
                   json.dumps(assets), str(program)], root).splitlines()[-1])
        print(json.dumps({'wheel': wheel.name, 'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
                          'network': False, 'source': 'current working tree', 'site_packages': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
