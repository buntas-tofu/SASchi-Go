#!/usr/bin/env python3
"""Original explicit-delimiter SCAN/COUNTW gates, no live SAS comparison."""
from pathlib import Path
import random
import sys

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate

GATE=FamilyGate(HERE,'word_functions','b632a76d330ea6ce1e71057ffd58b52492163859f2e7b3b060c34f13b5c2f2e0',10)
REFUSALS=[('scan',['a b',0,' ']),('scan',['a b',1.5,' ']),('scan',['a b',None,' ']),
    ('scan',['a b',True,' ']),('scan',['a b',1,'','M']),('scan',['a b',1,' ','Q']),
    ('countw',['',' ']),('countw',[{'missing':'A'},' ']),('countw',['é',' ']),
    ('countw',['a\tb',' ']),('countw',['abc','x'*65]),('countw',['abc',' ','I'])]


def main():
    GATE.qualify(REFUSALS)
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: word hand pins,shared refusals and complete independent original hand/R expectation before implementation')
        return
    from sas_semantics import sas_scan,sas_countw
    rng=random.Random(9711);cases=[]
    for _ in range(160):
        text=''.join(rng.choice(' abXY|,') for _ in range(rng.randrange(1,25)))
        delimiters=rng.choice([' ','|',',',' |']);modifier=rng.choice(['','M'])
        count=rng.choice([-8,-2,-1,1,2,8])
        cases.extend([('scan',[text,count,delimiters,modifier]),('countw',[text,delimiters,modifier])])
    cases.extend([('scan',['x'*32767,1,'|']),('countw',['|'*32767,'|','M'])])
    GATE.verify({'scan':sas_scan,'countw':sas_countw},cases,REFUSALS,{'scan':lambda args:len(args[0])})


if __name__=='__main__':main()
