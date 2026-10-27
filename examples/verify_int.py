#!/usr/bin/env python3
"""DS-037 safe INT pins and native base-R truncation, no live SAS."""
import csv
import math
from pathlib import Path
import random
import tempfile
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from examples.verify_division import kind,rrun
from sas_semantics import sas_int

PINS=[(0.,0),(2.1,2),(-2.4,-2),(1+1e-11,1),(-1.6,-1),(.5,0),(-.5,0),
      (1.999,1),(-1.999,-1),(2147483647.,2147483647),(-2147483647.,-2147483647),
      (1-4e-12,0),(1+4e-12,1),(-1+4e-12,0),(-1-4e-12,-1)]


def main():
    rng=random.Random(3701)
    good=list(PINS)
    for _ in range(1000):
        integer=rng.randint(0,1000000); fraction=rng.randrange(8)/8; sign=rng.choice((-1,1))
        good.append((sign*(integer+fraction),sign*integer))
    bad=[None,True,False,'1',[],{}, {'missing':'A'},float('nan'),float('inf'),float('-inf'),10**400,
         2147483648.,-2147483648.,1e-13,-1e-13,1.9999999999995,-1.9999999999995,
         math.nextafter(1,0),math.nextafter(1,2),math.nextafter(-1,0),math.nextafter(-1,-2)]
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'cases.csv'
        with path.open('w',newline='') as stream:
            w=csv.writer(stream);w.writerow(['id','kind','value'])
            for i,x in enumerate([x for x,_ in good]+bad):w.writerow([i,kind(x),str(x)])
        witness=rrun('int',path).splitlines()
    assert len(witness)==len(good)+len(bad)
    for i,record in enumerate(witness):
        if i<len(good):
            x,expected=good[i]; assert sas_int(x)==expected
            assert record.startswith(f'{i}:OK:') and float(record.split(':')[2])==expected,(i,record)
        else:
            try:sas_int(bad[i-len(good)])
            except ValueError:pass
            else:raise AssertionError(('missing INT refusal',i))
            assert record==f'{i}:REFUSE',(i,record)
    assert math.floor(-2.4)!=PINS[2][1]
    print(f'VERIFIED: INT{len(PINS)} pins,1000 constructive R cases,{len(bad)} shared refusals; '
          'truncation outside conservative2e-12 fuzz band, independent base R; no live SAS')


if __name__=='__main__':main()
