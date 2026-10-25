#!/usr/bin/env python3
"""DS-029 repository/R gate for maintainer review, not live SAS evidence."""
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_concat, sas_catx

PINS = [
    ('concat', ' ', ['a ', ' b'], 'a  b'),
    ('concat', ' ', [' ', '  '], '   '),
    ('concat', ' ', ['a', ' ', 'b'], 'a b'),
    ('concat', ' ', ['!!', '||'], '!!||'),
    ('catx', ',', [' a ', ' ', ' b '], 'a,b'),
    ('catx', ' / ', [' a ', 'b ', ' c'], 'a / b / c'),
    ('catx', ' ', [' ', '  '], ''),
    ('catx', ' ', [' x '], 'x'),
    ('catx', ' ', ['x' * 99, 'y' * 100], 'x' * 99 + ' ' + 'y' * 100),
    ('concat', ' ', ['x' * 16383, 'y' * 16384], 'x' * 16383 + 'y' * 16384),
]
REFUSALS = [
    ('concat',' ',['a'],None), ('concat',' ',['a']*33,None),
    ('concat',' ',['','b'],None), ('concat',' ',['é','b'],None),
    ('concat',' ',['a\tb','c'],None), ('concat',' ',[7,'a'],None),
    ('concat',' ',[None,'a'],None), ('concat',' ',['x'*16384,'y'*16384],None),
    ('catx',' ',[],None), ('catx',' ',['x']*33,None),
    ('catx','', ['a','b'],None), ('catx',7,['a'],None),
    ('catx',' ',[None,'b'],None), ('catx',' ',['a',''],None),
    ('catx',' ',['x'*100,'y'*100],None),
]


def apply(mode, delimiter, fields):
    return sas_concat(fields) if mode == 'concat' else sas_catx(delimiter, *fields)


def main():
    generated=[];rng=random.Random(2901)
    for _ in range(1000):
        values=[''.join(rng.choice(' abXY012,') for _ in range(rng.randint(1,12))) for _ in range(rng.randint(2,8))]
        for mode in ('concat','catx'):
            delimiter=rng.choice([' ', ',', ' / ']);trimmed=[value.strip(' ') for value in values]
            expected=''.join(values) if mode=='concat' else delimiter.join(value for value in trimmed if value)
            generated.append((mode,delimiter,values,expected))
    cases=PINS+generated+REFUSALS
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'cases.tsv'
        def field(value):return 'C:'+value.encode().hex() if isinstance(value,str) else 'N:'+repr(value)
        path.write_text(''.join('\t'.join([mode,field(delimiter),*[field(value) for value in values]])+'\n' for mode,delimiter,values,_ in cases))
        r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        run=subprocess.run([r,str(HERE/'concat_catx.R'),'fixtures',str(path)],capture_output=True,text=True,check=True,timeout=60)
    records=run.stdout.splitlines();assert len(records)==len(cases)
    for index,((mode,delimiter,values,expected),record) in enumerate(zip(cases,records)):
        if expected is None:
            try:apply(mode,delimiter,values)
            except ValueError:pass
            else:raise AssertionError((index,'missing refusal'))
            assert record=='ERROR',(index,record)
        else:
            assert apply(mode,delimiter,values)==expected,(index,'Python')
            assert record.startswith('OK:') and bytes.fromhex(record[3:]).decode('ascii')==expected,(index,record)
    assert ''.join(value.strip(' ') for value in PINS[0][2])!=PINS[0][3]
    assert ','.join(value.strip(' ') for value in PINS[4][2])!=PINS[4][3]
    assert ' '.join(PINS[5][2])!=PINS[5][3]
    assert PINS[6][3]!=' '
    print('VERIFIED: concat/CATX 10 pins, 2000 generated cases, 15 shared refusals, four naive errors caught; independent base R; no live SAS')


if __name__=='__main__':main()
