#!/usr/bin/env python3
"""DS-036 exact-quotient pins and independent native base R, no live SAS."""
import csv
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from sas_semantics import sas_divide

PINS=[(9.,2.,4.5),(-7.,2.,-3.5),(7.,-2.,-3.5),(-7.,-2.,3.5),
      (.5,2.,.25),(3.,1.5,2.),(6.,3.,2.),(0.,3.,0.),(-0.,2.,-0.),
      (2147483647.,1.,2147483647.),(2147483647.,2147483647.,1.),
      (5e-324,1.,5e-324), (1+2**-52,2.,.5+2**-53), (2**-1022,2.,2**-1023)]


def kind(value):
    if isinstance(value,bool): return 'boolean'
    if isinstance(value,(int,float)): return 'number'
    if value is None: return 'missing'
    return 'other'


def rrun(stem,*args):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/(stem+'.R')),*map(str,args)],
                          capture_output=True,text=True,check=True,timeout=60).stdout


def main():
    rng=random.Random(3601); good=list(PINS)
    for _ in range(500):
        q=rng.randint(-100000,100000)/64; denominator=2.**rng.randint(-10,10)
        good.append((q*denominator,denominator,q))
    for _ in range(500):
        n=rng.randint(-100000,100000); odd=rng.choice((3,5,7,9,11)); power=2**rng.randint(0,10)
        good.append((n*odd,odd*power,n/power))
    bad=[(v,1.,None) for v in (None,True,False,'1',[],{}, {'missing':'A'},float('nan'),float('inf'),float('-inf'),10**400)]
    bad += [(1.,a,None) for a,_,_ in bad]
    bad += [(a,b,None) for a,b in ((1,0),(0,0),(1,3),(2,3),(1,10),(5e-324,2),
                                  (2147483647,.5),(2147483648,1),(1,1e-320))]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'cases.csv'
        with path.open('w',newline='') as stream:
            w=csv.writer(stream); w.writerow(['id','a_kind','a','b_kind','b'])
            for i,(a,b,_) in enumerate(good+bad):w.writerow([i,kind(a),str(a),kind(b),str(b)])
        witness=rrun('division',path).splitlines()
    assert len(witness)==len(good)+len(bad)
    for i,((a,b,expected),record) in enumerate(zip(good+bad,witness)):
        if i<len(good):
            assert sas_divide(a,b)==expected,(i,a,b)
            assert record.startswith(f'{i}:OK:') and float(record.split(':')[2])==expected,(i,record)
        else:
            try:sas_divide(a,b)
            except ValueError:pass
            else:raise AssertionError(('missing division refusal',i,a,b))
            assert record==f'{i}:REFUSE',(i,record)
    assert 9//2!=PINS[0][2] and -7//2!=PINS[1][2]
    print(f'VERIFIED: division{len(PINS)} pins,1000 constructive R cases,{len(bad)} shared refusals; '
          'exact bounded binary64 quotients, independent native R/hex witness; no live SAS')


if __name__=='__main__':main()
