#!/usr/bin/env python3
"""DS-031 original branch/loop Python/base-R evidence for maintainer review."""
import csv
import io
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from saschi.plan import compile_plan
from saschi.runtime import run_plan

# start,stop,by,first divisor,second divisor; all source here is original.
PINS=[(1,15,1,3,5),(5,-1,-2,2,3),(4,1,1,3,5),(2,2,-3,2,2),(-4,3,1,2,3)]
REFUSALS=[(1,2,0,3,5),(0,10000,1,3,5),(2147483648,2147483648,1,3,5),(1,2,1,0,5),(1,2,1,3,0)]


def original_program(case):
    start,stop,by,first,second=case
    return (f'data d; total=0; do i={start} to {stop} by {by}; '
            f'if mod(i,{first})=0 then branch=11; else if mod(i,{second})=0 then branch=13; '
            'else branch=17; total=total+branch; seen=_n_; output; end; after=i; output; run;')


def rrun(mode,path):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'do_if.R'),mode,str(path)],capture_output=True,text=True,check=True,timeout=60).stdout


def program_records(path):
    lines=rrun('program',path).splitlines();head=lines[0].split(':')
    assert len(head)==3 and head[0]=='STATE'
    records=[]
    for line in lines[1:]:
        assert line.startswith('RECORD:')
        records.append(bytes.fromhex(line[7:]).decode('ascii'))
    assert len(records)==int(head[2]);return records,int(head[1])


def main():
    rng=random.Random(31001)
    cases=PINS+[(rng.randrange(-8,9),rng.randrange(-8,9),rng.choice((-3,-2,-1,1,2,3)),rng.randrange(1,8),rng.randrange(1,8)) for _ in range(1000)]
    accepted=len(cases);cases+=REFUSALS
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'cases.csv'
        with path.open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['id','start','stop','by','first','second']);writer.writerows((i,*case) for i,case in enumerate(cases))
        raw=list(csv.DictReader(io.StringIO(rrun('cases',path))))
    rows={i:[] for i in range(len(cases))};refused=set()
    for row in raw:
        key=int(row.pop('id'))
        if row.pop('status')=='REFUSE':refused.add(key)
        else:rows[key].append({name:float(value) if value else None for name,value in row.items()})
    assert set(rows)==set(range(len(cases)))
    for i,case in enumerate(cases):
        plan=compile_plan(original_program(case))
        if i>=accepted:
            if not plan.blocked:
                try:run_plan(plan.to_dict())
                except ValueError:pass
                else:raise AssertionError(('missing refusal',case))
            assert i in refused,case
            continue
        assert not plan.blocked,plan.tickets
        result=run_plan(plan.to_dict());table=result['datasets']['d']
        assert table['schema']=={'total':'number','i':'number','branch':'number','seen':'number','after':'number'}
        assert table['rows']==rows[i],(case,table['rows'],rows[i])
        assert result['log']==[] and i not in refused
    # First matching branch wins even when both predicates are true.
    result=run_plan(compile_plan(original_program(PINS[0])).to_dict())['datasets']['d']['rows']
    assert next(row['branch'] for row in result if row['i']==15)==11
    assert result[-1]['i']==16 and result[-1]['after']==16
    # Evaluating the unreachable condition would raise instead of returning7.
    short=compile_plan('data d; if 1 then x=7; else if mod(1,0)=0 then x=9; else x=11; run;')
    assert not short.blocked and run_plan(short.to_dict())['datasets']['d']['rows']==[{'x':7.}]
    print('VERIFIED: DO/IF 5 pins,1000 generated complete-runtime/R cases,5 shared refusals,3 naive errors caught; first-match/lazy predicates and final control state; no live SAS')


if __name__=='__main__':main()
