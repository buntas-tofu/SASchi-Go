#!/usr/bin/env python3
"""Verify the complete pinned Roku program against an independent base-R sieve."""
from contextlib import redirect_stdout
from copy import deepcopy
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from saschi.compare import equal
from saschi.emit_py import translate
from saschi.flow_control import COUNTED_LINK_PROFILE
from saschi.plan import compile_plan
from saschi.runtime import run_plan

PROGRAM = 'primality_by_trial_division.sas'
SOURCE_SHA256 = 'd8813e29852d5932149a60886a1846027e04dab66d34868b2489e690c12ad860'
R_RESULT_SHA256 = '55542ac8f84d3c795ac05ea7dc3e382353c4bdd519d97e178d3f17a7f97fb25f'


def reference_result():
    rscript = os.environ.get('ROSETTA_RSCRIPT') or 'Rscript'
    numbers = subprocess.run(
        [rscript, '--vanilla', str(ROOT / 'examples/primality.R')],
        check=True, capture_output=True, timeout=30,
    ).stdout
    assert sha256(numbers).hexdigest() == R_RESULT_SHA256
    primes = [int(row) for row in numbers.splitlines()]
    assert len(primes) == 168 and primes[:3] == [2, 3, 5] and primes[-1] == 997
    return {'datasets': {'primes': {'schema': {'n': 'number'}, 'rows': [
        {'n': n} for n in primes
    ]}}, 'log': []}


def verify_cli(source, folder, expected, *, matches):
    expected_path = folder.with_suffix('.json')
    expected_path.write_text(json.dumps(expected['datasets']))
    process = subprocess.run(
        [sys.executable, '-m', 'saschi', 'run', str(source),
         '--expect', str(expected_path), '--output', str(folder)],
        cwd=ROOT, capture_output=True, text=True, timeout=45,
    )
    assert process.returncode == (0 if matches else 1), (process.stdout, process.stderr)
    receipt = json.loads((folder / 'receipt.json').read_text())
    assert receipt['accepted'] is matches and receipt['comparison'] == ('passed' if matches else 'failed')
    assert receipt['source_sha256'] == SOURCE_SHA256
    assert receipt['expected_sha256'] == sha256(expected_path.read_bytes()).hexdigest()
    result_file = folder / ('result.json' if matches else 'observed.json')
    assert (folder / 'result.json').exists() is matches
    result_bytes = result_file.read_bytes()
    assert receipt['result_sha256'] == sha256(result_bytes).hexdigest()
    return json.loads(result_bytes)


def main():
    corpus = Path(os.environ.get('SASCHI_ROKU_CORPUS', ROOT.parent / 'saschi-roku/corpus'))
    source_path = corpus / PROGRAM
    raw = source_path.read_bytes()
    assert sha256(raw).hexdigest() == SOURCE_SHA256
    source = raw.decode('utf-8')
    expected = reference_result()

    compiled = compile_plan(source)
    assert not compiled.blocked, compiled.tickets
    plan = json.loads(json.dumps(compiled.to_dict()))
    assert len(plan['steps']) == 1
    assert plan['steps'][0]['operations'][0]['args']['name'] == COUNTED_LINK_PROFILE
    assert compiled.matched == [('scalar-counted-link', 'DS-127', 5)]
    assert equal(run_plan(plan), expected, ordered_maps=True)

    translation = translate(source)
    assert not translation.blocked, translation.tickets
    namespace = {}
    stream = io.StringIO()
    with redirect_stdout(stream):
        exec(translation.code, namespace)
    assert not stream.getvalue()
    assert equal(namespace['result'], expected, ordered_maps=True)

    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        actual = verify_cli(source_path, folder / 'matched', expected, matches=True)
        assert equal(actual, expected, ordered_maps=True)

        wrong = deepcopy(expected)
        rows = wrong['datasets']['primes']['rows']
        rows[83], rows[84] = rows[84], rows[83]
        observed = verify_cli(source_path, folder / 'swapped', wrong, matches=False)
        assert equal(observed, expected, ordered_maps=True)

    print(f'VERIFIED corpus: {PROGRAM}; unchanged source and all 168 ordered primes '
          'agree with base R through portable execution, emitted Python and actual CLI; '
          'a swapped pair fails comparison')


if __name__ == '__main__':
    main()
