#!/usr/bin/env python3
"""Original fixed-character reversal pins and base-R evidence, no live SAS."""
import csv
import io
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_reverse
from saschi.plan import compile_plan
from saschi.runtime import run_plan

PINS = [('a','a'), ('ab','ba'), (' ab','ba '), ('ab  ','  ba'),
        (' Qz    ','    zQ '), ('a b','b a'), ('   ','   '),
        ('level','level'), ('09!?','?!90'), ('\'"','"\'')]
REFUSALS = ['', None, 7, True, {'missing':'A'}, 'é', 'a\tb', 'a\nb', 'a\x00b', 'x'*32768]


def rrun(mode, path):
    r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r, str(HERE/'length_reverse.R'), mode, str(path)],
                          capture_output=True,text=True,check=True,timeout=60).stdout


def program_records(path):
    lines = rrun('program',path).splitlines()
    if any(not line.startswith('RECORD:') for line in lines):
        raise AssertionError('independent program witness protocol')
    return [bytes.fromhex(line[7:]).decode('ascii') for line in lines]


def main():
    for value, expected in PINS:
        assert sas_reverse(value) == expected
    rng = random.Random(280)
    generated = [''.join(chr(rng.randrange(32,127)) for _ in range(rng.randrange(1,81))) for _ in range(1000)]
    values = [x[0] for x in PINS] + generated + ['x'*32767] + REFUSALS
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'cases.csv'
        with path.open('w',newline='') as stream:
            writer = csv.writer(stream);writer.writerow(['id','kind','hex'])
            for i,value in enumerate(values):
                writer.writerow([i,'character' if isinstance(value,str) else 'other',value.encode('utf-8').hex() if isinstance(value,str) else ''])
        rows = list(csv.DictReader(io.StringIO(rrun('cases',path))))
    assert len(rows)==len(values)
    accepted = len(values)-len(REFUSALS)
    for value,row in zip(values[:accepted],rows[:accepted]):
        assert sas_reverse(value).encode('ascii').hex()==row['value']
    for value,row in zip(REFUSALS,rows[accepted:]):
        try: sas_reverse(value)
        except ValueError: pass
        else: raise AssertionError('unsupported reverse input accepted')
        assert row['value']=='REFUSE'
    plan = compile_plan("data reversed; length raw rev $7; raw=' Qz'; rev=reverse(raw); seen=lengthc(rev); output; run;")
    assert not plan.blocked,plan.tickets
    result = run_plan(plan.to_dict())['datasets']['reversed']
    assert list(result['schema'])==['raw','rev','seen']
    assert result['rows']==[{'raw':' Qz    ','rev':'    zQ ','seen':7.}]
    naive = [lambda x:x.strip()[::-1],lambda x:x.rstrip()[::-1],lambda x:x[::-1].lstrip()]
    assert all(any(function(value)!=expected for value,expected in PINS) for function in naive)
    print(f'VERIFIED: LENGTH/REVERSE {len(PINS)} pins, 1000 generated cases, max-width boundary, {len(REFUSALS)} shared refusals, {len(naive)} naive errors caught; independent base R; no live SAS')


if __name__=='__main__': main()
