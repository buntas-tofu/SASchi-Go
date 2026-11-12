#!/usr/bin/env python3
"""Independent calendar components, discrete boundaries and alignment gates."""
from datetime import date
from pathlib import Path
import random
import sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'calendar_intervals','361064c0a1c950cb18d2cb01ef549cb2bfaeac9c88f4c633742bdcbb44e7657c',13)
REFUSALS=[('year',[True]),('month',['0']),('day',[{'missing':'A'}]),('day',[.5]),('year',[-1000000]),
 ('intck',['WEEK',0,1]),('intck',['MONTH',0,1,'C']),('intnx',['MONTH',0,1,'M']),
 ('intnx',['MONTH',0,.5]),('intnx',['MONTH',0,10001]),('intnx',['YEAR',0,3000]),('intnx',['DAY',0,float('inf')])]

def main():
    GATE.qualify(REFUSALS)
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: calendar component/boundary/alignment pins,shared refusals and complete original hand/R oracle before implementation');return
    from sas_semantics import sas_year,sas_month,sas_day,sas_source_intck,sas_source_intnx
    rng=random.Random(10111);cases=[];epoch=date(1960,1,1)
    for _ in range(100):
        d=(date(rng.randrange(2000,2031),rng.randrange(1,13),rng.randrange(1,29))-epoch).days
        end=(date(rng.randrange(2000,2031),rng.randrange(1,13),rng.randrange(1,29))-epoch).days
        interval=rng.choice(['DAY','MONTH','QTR','YEAR'])
        cases.extend([('year',[d]),('month',[d]),('day',[d]),('intck',[interval,d,end]),('intnx',[interval,d,rng.randrange(-24,25),rng.choice(['B','E','S'])])])
    GATE.verify({'year':sas_year,'month':sas_month,'day':sas_day,'intck':sas_source_intck,'intnx':sas_source_intnx},cases,REFUSALS)

if __name__=='__main__':main()
