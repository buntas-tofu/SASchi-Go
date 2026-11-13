#!/usr/bin/env python3
"""Original ASCII character validation and directional search gate."""
from pathlib import Path
import random,sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'character_validation','c923d7686d3227e3ff95409ce0bb2ba11d0e13d585db996451b9891a38815b76',14)
ANY=('anyalpha','anydigit','anyalnum','anyspace','notdigit')
REFUSALS=[(name,[value]) for name in ANY for value in (None,True,1,{'missing':'A'},'é','a\tb','x'*32768)]
REFUSALS += [(name,['x',value]) for name in ANY for value in (True,{'missing':'A'},'1',.5,2147483648)]
REFUSALS += [('verify',args) for args in (['x'],['x',None],['x','x',1],['é','x'],['x']*33)]

def main():
    GATE.qualify(REFUSALS)
    empty=[('verify',['','x'])]+[(name,['']) for name in ANY]
    assert GATE.r_cases(empty)==[0]*6
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: character position hand pins,empty helper results,refusals and whole original hand/R before implementation');return
    from sas_semantics import sas_verify,sas_anyalpha,sas_anydigit,sas_anyalnum,sas_anyspace,sas_notdigit
    functions=dict(zip(('verify',)+ANY,(sas_verify,sas_anyalpha,sas_anydigit,sas_anyalnum,sas_anyspace,sas_notdigit)))
    assert [functions[name](*args) for name,args in empty]==[0]*6
    rng=random.Random(10411);cases=[]
    for _ in range(100):
        text=''.join(rng.choice(' abAZ09-_.') for _ in range(rng.randrange(1,41)))
        start=rng.choice([None,-99,-5,-1,0,1,4,99])
        cases.append(('verify',[text,'abAZ','09',' -_.']))
        cases.extend((name,[text,start]) for name in ANY)
    cases.extend((name,['x'*32767]) for name in ANY)
    GATE.verify(functions,cases,REFUSALS)

if __name__=='__main__':main()
