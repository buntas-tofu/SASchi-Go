#!/usr/bin/env python3
"""Independent numeric helper and fuzz-boundary evidence, no native SAS."""
from pathlib import Path
import random
import sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'numeric_helpers','733c7d260922ff2b0c8bfccf0359d43513969f0bb870bd4dd6492d6a76187267',10)
REFUSALS=[(name,[value]) for name in ('abs','sign','ceil','floor') for value in (True,'1',{'missing':'A'},float('inf'),float('nan'),2147483648,1e-320)]

def main():
    GATE.qualify(REFUSALS)
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: numeric hand pins,fuzz boundaries,shared refusals and complete original hand/R oracle before implementation');return
    from sas_semantics import sas_abs,sas_sign,sas_ceil,sas_floor
    rng=random.Random(10011);cases=[]
    for _ in range(150):
        base=rng.randrange(-1000,1001);value=rng.choice([None,base/4,base+2**-40,base-2**-40,base+2**-30,base-2**-30])
        cases.extend((name,[value]) for name in ('abs','sign','ceil','floor'))
    GATE.verify({'abs':sas_abs,'sign':sas_sign,'ceil':sas_ceil,'floor':sas_floor},cases,REFUSALS)

if __name__=='__main__':main()
