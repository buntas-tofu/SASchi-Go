#!/usr/bin/env python3
"""Original whitespace/alignment gate with independent byte-oriented base R."""
from pathlib import Path
import random
import sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'whitespace_alignment','09bfbe256f42ad97cc4ddb9faaf2ab0229f2d21c50c47fb86f214a8618605f7b',10)
REFUSALS=[(name,[value]) for name in ('left','right','compbl','trimn') for value in (None,True,1,{'missing':'A'},'é','a\tb','x'*32768)]

def main():
    GATE.qualify(REFUSALS)
    assert GATE.r_cases([(name,['']) for name in ('left','right','compbl','trimn')])==['']*4
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: whitespace hand pins,empty helper results,refusals and whole original hand/R before implementation');return
    from sas_semantics import sas_left,sas_right,sas_compbl,sas_trimn
    functions=dict(zip(('left','right','compbl','trimn'),(sas_left,sas_right,sas_compbl,sas_trimn)))
    assert [f('') for f in functions.values()]==['']*4
    rng=random.Random(10211);cases=[]
    for _ in range(100):
        text=''.join(rng.choice('   abAB-_.') for _ in range(rng.randrange(1,41)))
        cases.extend((name,[text]) for name in functions)
    cases.extend((name,[' '*32767]) for name in functions)
    cases.extend((name,['x'*32767]) for name in functions)
    GATE.verify(functions,cases,REFUSALS,{name:lambda a:len(a[0]) for name in functions})

if __name__=='__main__':main()
