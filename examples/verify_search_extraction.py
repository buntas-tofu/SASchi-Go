#!/usr/bin/env python3
"""Original search/extraction gate with explicit word and substring contracts."""
from pathlib import Path
import random,sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'search_extraction','9e962f99480c75c3be4ab8e4a3c3a98d02f78ec21c41ff62f11daa678cd51842',10)
REFUSALS=[('findc',args) for args in (['x'],['x',None],['x','x','Q'],['x','x',None],['x','x',.5],['x','x','I','I'],['x','x'*65])]
REFUSALS += [('findw',args) for args in (['x','x'],['x','x','a'],['x','',' '],['x','x',' ' , 'Q'],['x','x',' ',None],['x','x',' ',.5])]
REFUSALS += [('indexw',['x','x',',']),('indexc',['x']),('indexc',['x',1]),('substrn',['abcd',.5,2]),('substrn',['abcd',None,'x']),('substrn',['abcd',True,2])]
REFUSALS += [(name,args) for name,args in [('findc',['é','x']),('findw',['é','x',' ']),('indexc',['é','x']),('indexw',['é','x']),('substrn',['é',1])]]

def main():
    GATE.qualify(REFUSALS)
    empty=[('findc',['','x']),('findw',['','x',' ']),('indexc',['','x']),('indexw',['','']),('substrn',['',1,1])]
    assert GATE.r_cases(empty)==[0,0,0,1,'']
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: search/extraction hand pins,empty helper boundaries,refusals and whole original hand/R before implementation');return
    from sas_semantics import sas_findc,sas_findw,sas_indexc,sas_indexw,sas_substrn
    functions=dict(zip(('findc','findw','indexc','indexw','substrn'),(sas_findc,sas_findw,sas_indexc,sas_indexw,sas_substrn)))
    assert [functions[name](*args) for name,args in empty]==[0,0,0,1,'']
    rng=random.Random(10511);cases=[]
    for _ in range(80):
        text=''.join(rng.choice(' abAB,xyz-_') for _ in range(rng.randrange(1,31)))
        cases.extend([('findc',[text,'aB',rng.choice(['','I','K','IK']),rng.choice([-99,-3,0,1,5,99])]),
                      ('findw',[text,rng.choice(['a','ab','A']),' ,',rng.choice(['','I']),rng.choice([-99,-3,0,1,5,99])]),
                      ('indexc',[text,'x','Z']),('indexw',[text,'ab']),
                      ('substrn',[text,rng.choice([None,-5,0,1,5,99]),rng.choice([None,-1,0,2,99])])])
    GATE.verify(functions,cases,REFUSALS,{'substrn':lambda a:len(a[0])})

if __name__=='__main__':main()
