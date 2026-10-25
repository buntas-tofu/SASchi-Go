#!/usr/bin/env python3
"""Original DS-007 compiled execution/base-R evidence, no live SAS claim."""
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
from sas_semantics import sas_lag_numeric
from saschi.plan import compile_plan
from saschi.runtime import run_plan

PINS=[(1,[10.,20.,30.,40.],[0.,1.,0.,1.]),
      (1,[10.,None,30.,40.],[1.,1.,1.,1.]),
      (2,[10.,25.,31.,40.],[1.,1.,1.,1.]),
      (100,[float(i) for i in range(1,104)],[1.]*103)]
INVALID=[True,False,'1',{'missing':'A'},float('nan'),float('inf'),float('-inf'),10**400]


def token(value):
    if value is None:return 'M'
    if isinstance(value,bool):return 'B:'+str(value)
    if isinstance(value,(int,float)):return 'N:'+str(value)
    if isinstance(value,str):return 'S:'+value.encode().hex()
    return 'T:A'


def source(depth,alias=False):
    suffix='' if alias and depth==1 else str(depth)
    return ('data d; set raw; '
            f'if flag then cond_lag=lag{suffix}(x); if flag then cond_dif=dif{suffix}(x); '
            f'full_lag=lag{suffix}(x); full_dif=dif{suffix}(x); '
            'if flag then used=full_lag; run;')


def rrun(mode,path):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'lag_execution.R'),mode,str(path)],capture_output=True,text=True,check=True,timeout=60).stdout


def main():
    rng=random.Random(7007);cases=list(PINS)
    for repeat in range(3):
        for depth in range(1,101):
            count=2*depth+7
            values=[None if rng.randrange(8)==0 else rng.randrange(-8000,8001)/8 for _ in range(count)]
            flags=[rng.choice((None,0.,1.,1.,-1.)) for _ in range(count)]
            cases.append((depth,values,flags))
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'cases.csv'
        with path.open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['id','depth','row','x','flag'])
            for i,(depth,values,flags) in enumerate(cases):
                writer.writerows((i,depth,row,token(value),token(flag)) for row,(value,flag) in enumerate(zip(values,flags)))
        rows=list(csv.DictReader(io.StringIO(rrun('cases',path))))
        invalid_path=Path(directory)/'invalid.txt';invalid_path.write_text(''.join(token(value)+'\n' for value in INVALID))
        refused=rrun('values',invalid_path).splitlines()
    assert len(refused)==len(INVALID)
    for value,status in zip(INVALID,refused):
        try:sas_lag_numeric(value)
        except ValueError:pass
        else:raise AssertionError('invalid finite-numeric queue input accepted')
        assert status=='REFUSE'
    expected={i:[] for i in range(len(cases))}
    for row in rows:
        i=int(row.pop('id'));ordinal=int(row.pop('row'));assert ordinal==len(expected[i])+1
        expected[i].append({name:None if value=='.' else float(value) for name,value in row.items()})
    for i,(depth,values,flags) in enumerate(cases):
        plan=compile_plan(source(depth,alias=i%2==0));assert not plan.blocked,plan.tickets
        inputs={'raw':{'schema':{'x':'number','flag':'number'},'rows':[{'x':x,'flag':f} for x,f in zip(values,flags)]}}
        result=run_plan(plan.to_dict(),inputs)
        assert result=={'datasets':{'raw':inputs['raw'],'d':{
            'schema':{name:'number' for name in ('x','flag','cond_lag','cond_dif','full_lag','full_dif','used')},
            'rows':expected[i]}},'log':[]},(i,depth)
    first=expected[0]
    assert first[3]['cond_lag']==20 and first[3]['cond_lag']!=30 # Row shift is wrong.
    assert expected[1][0]['cond_lag'] is None and expected[1][0]['full_lag'] is None # Shared queue is wrong.
    assert expected[2][2]['full_dif']==21 and expected[2][2]['full_dif']!=-9 # Repeated DIF1 is wrong.
    assert expected[1][2]['full_lag'] is None # Missing arguments must advance.
    print(f'VERIFIED: LAG/DIF execution4 pins,300 generated complete-runtime/R cases across depths1..100,8 shared value refusals,4 naive errors caught; {len(rows)} typed rows; prior-invoked-index R model; no live SAS')


if __name__=='__main__':main()
