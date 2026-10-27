#!/usr/bin/env python3
"""DS-035 body-first hand pins and independent base R, no live SAS."""
import csv
import itertools
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from sas_semantics import sas_do_until
from saschi.plan import compile_plan
from saschi.runtime import run_plan


def rrun(mode,path):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'do_until.R'),mode,str(path)],
                          capture_output=True,text=True,check=True,timeout=60).stdout


def program_records(path):
    lines=rrun('program',path).splitlines()
    state=lines[0].split(':'); assert state[0]=='STATE' and len(state)==3
    assert all(s.startswith('RECORD:') for s in lines[1:])
    return [bytes.fromhex(s[7:]).decode('ascii') for s in lines[1:]],int(state[1]),int(state[2])


def main():
    pins=[(0,1,0,1,1),(0,1,6,6,6),(5,2,6,1,7),(-3,2,3,3,3)]
    cases=[(a,b,z) for a,b,z,_,_ in pins]+list(itertools.product(range(-3,4),(1,2,3),range(-3,7)))
    cases += [(0,1,10000),(0,1,10001),(0,0,1),(2,-1,3)]
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'cases.csv'
        with path.open('w',newline='') as stream:
            w=csv.writer(stream); w.writerow(['start','increment','stop']); w.writerows(cases)
        witness=rrun('cases',path).splitlines()
    assert len(witness)==len(cases)
    for i,((a,b,z),answer) in enumerate(zip(cases,witness)):
        # Independent integer arithmetic count, no translated loop/helper.
        expected=max(1,(z-a+b-1)//b) if b>0 else None
        state=[a]; records=[]
        def body(): state[0]+=b; records.append(state[0])
        if expected is None or expected>10000:
            try: sas_do_until(body,lambda:state[0]>=z)
            except ValueError: pass
            else: raise AssertionError(('missing budget refusal',i))
            assert answer==f'{i}:REFUSE'
        else:
            count=sas_do_until(body,lambda:state[0]>=z)
            assert count==expected and state[0]==a+b*count
            parts=answer.split(':')
            assert parts[:4]==[str(i),'OK',str(count),str(state[0])]
            assert list(map(int,parts[4].split('|')))==records
        if i<len(pins): assert (count,state[0])==pins[i][3:]
    source='data d; n=0; do until(n>=3); n+1; output; end; final=n; run;'
    plan=compile_plan(source); assert not plan.blocked,plan.tickets
    table=run_plan(plan.to_dict())['datasets']['d']
    assert table=={'schema':{'n':'number','final':'number'},'rows':[{'n':float(n),'final':None} for n in (1,2,3)]}
    assert pins[0][3]==1, 'pre-test zero-trip implementation must fail'
    print(f'VERIFIED: DO UNTIL4 pins,{len(cases)} independent R schedules including10000/10001 limits, '
          'explicit OUTPUT snapshots and pre-test discriminator; repository/base-R only')


if __name__=='__main__': main()
