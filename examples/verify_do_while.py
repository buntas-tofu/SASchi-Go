#!/usr/bin/env python3
"""DS-038 pre-test schedule pins and independent R, no live SAS."""
import csv
import itertools
from pathlib import Path
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from examples.verify_division import rrun
from sas_semantics import sas_do_while
from saschi.plan import compile_plan
from saschi.runtime import run_plan


def program_records(path):
    lines=rrun('do_while','program',path).splitlines()
    state=lines[0].split(':'); assert len(state)==3 and state[0]=='STATE'
    assert all(s.startswith('RECORD:') for s in lines[1:])
    return [bytes.fromhex(s[7:]).decode('ascii') for s in lines[1:]],int(state[1]),int(state[2])


def main():
    pins=[(5,1,3,0,5),(0,1,3,3,3),(-3,2,3,3,3),(2,-1,-1,3,-1)]
    cases=[p[:3] for p in pins]+list(itertools.product(range(-3,4),(-3,-2,-1,1,2,3),range(-3,7)))
    cases += [(0,1,10000),(0,1,10001),(0,0,1)]
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'cases.csv'
        with path.open('w',newline='') as stream:
            w=csv.writer(stream); w.writerow(['start','increment','stop']);w.writerows(cases)
        witness=rrun('do_while','cases',path).splitlines()
    assert len(witness)==len(cases)
    for i,((a,b,z),record) in enumerate(zip(cases,witness)):
        expected=max(0,(z-a+b-1)//b) if b>0 else max(0,(a-z-b-1)//(-b)) if b<0 else None
        state=[a]; seen=[]
        def body():seen.append(state[0]);state[0]+=b
        def test():return state[0]>z if b<0 else state[0]<z
        if expected is None or expected>10000:
            try:sas_do_while(body,test)
            except ValueError:pass
            else:raise AssertionError(('missing WHILE budget refusal',i))
            assert record==f'{i}:REFUSE'
        else:
            count=sas_do_while(body,test); assert count==expected and state[0]==a+b*count
            parts=record.split(':');assert parts[:4]==[str(i),'OK',str(count),str(state[0])]
            assert ([] if not parts[4] else list(map(int,parts[4].split('|'))))==seen
            if i<len(pins):assert (count,state[0])==pins[i][3:]
    p=compile_plan('data d; n=0; do while(n<3); output; n+1; end; final=n; run;')
    assert not p.blocked,p.tickets
    table=run_plan(p.to_dict())['datasets']['d']
    assert table=={'schema':{'n':'number','final':'number'},'rows':[{'n':float(n),'final':None} for n in (0,1,2)]}
    print(f'VERIFIED: DO WHILE4 pins,{len(cases)} independent R schedules including zero-trip and10000/10001; '
          'explicit OUTPUT and pre-test discriminator; repository/base-R only')


if __name__=='__main__':main()
