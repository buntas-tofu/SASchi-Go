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
assert main(['inspect', sys.argv[4]]) == 0
print('VERIFIED: isolated installed wheel, canonical rulebook, all web assets, CLI entry point, MOD-to-PUT output and calendar calls')
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
