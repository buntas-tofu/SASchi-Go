#!/usr/bin/env python3
"""Original CAT family gate with independent byte-oriented base R."""
from pathlib import Path
import random,sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'cat_functions','abd53487ea4cbe61ff41d849e95bf86271581e3d0aa3876566e2a69f3013b5d2',9)
REFUSALS=[(name,[value]) for name in ('cat','cats','catt') for value in (None,True,1,{'missing':'A'},'é','a\tb','x'*201)]
REFUSALS += [(name,args) for name in ('cat','cats','catt') for args in ([],['x']*33,['x',None],[' '*32768])]

def main():
    GATE.qualify(REFUSALS)
    assert GATE.r_cases([(name,['']) for name in ('cat','cats','catt')])==['']*3
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: CAT hand pins,empty helpers,refusals and whole original hand/R before implementation');return
    from sas_semantics import sas_cat,sas_cats,sas_catt
    functions=dict(zip(('cat','cats','catt'),(sas_cat,sas_cats,sas_catt)))
    assert [f('') for f in functions.values()]==['']*3
    rng=random.Random(10311);cases=[]
    for _ in range(120):
        args=[''.join(rng.choice('  abAB-_.') for _ in range(rng.randrange(1,13))) for _ in range(rng.randrange(1,6))]
        cases.extend((name,args) for name in functions)
    cases.extend([('cats',[' '*32767]),('catt',[' '*32767])])
    GATE.verify(functions,cases,REFUSALS,{name:lambda a:200 for name in functions})

if __name__=='__main__':main()
