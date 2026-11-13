#!/usr/bin/env python3
"""Supplied integer datetime and independent UTC civil-calendar gate."""
from pathlib import Path
import random,sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'datetime_components','e353dd33296a50276162a2f962a716088f8911d3dabc8fd51ff224550e2063d5',13)
MIN_DAY=-75604;MAX_DAY=745094
MIN_STAMP=MIN_DAY*86400;MAX_STAMP=MAX_DAY*86400+86399
REFUSALS=[(name,[value]) for name in ('qtr','datepart','timepart','hour','minute','second') for value in (True,{'missing':'A'},'1',.5,float('inf'),float('nan'))]
REFUSALS += [('qtr',[MIN_DAY-1]),('qtr',[MAX_DAY+1])]
REFUSALS += [(name,[value]) for name in ('datepart','timepart','hour','minute','second') for value in (MIN_STAMP-1,MAX_STAMP+1)]
REFUSALS += [('dhms',args) for args in ([0,24,0,0],[0,0,60,0],[0,0,0,60],[0,-1,0,0],[MIN_DAY-1,0,0,0],[None,24,0,0],[0,None,60,0],[0,0,0,.5],[0,True,0,0],[0,0,0,'1'])]

def main():
    GATE.qualify(REFUSALS)
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: datetime hand pins,negative epoch boundaries,refusals and whole original civil-R before implementation');return
    from sas_semantics import sas_qtr,sas_dhms,sas_datepart,sas_timepart,sas_hour,sas_minute,sas_second
    functions=dict(zip(('qtr','dhms','datepart','timepart','hour','minute','second'),(sas_qtr,sas_dhms,sas_datepart,sas_timepart,sas_hour,sas_minute,sas_second)))
    rng=random.Random(10711);cases=[]
    for _ in range(80):
        day=rng.randrange(MIN_DAY,MAX_DAY+1);h=rng.randrange(24);m=rng.randrange(60);s=rng.randrange(60)
        stamp=day*86400+h*3600+m*60+s
        cases.extend([('qtr',[day]),('dhms',[day,h,m,s])])
        cases.extend((name,[stamp]) for name in ('datepart','timepart','hour','minute','second'))
    GATE.verify(functions,cases,REFUSALS)

if __name__=='__main__':main()
