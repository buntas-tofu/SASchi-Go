#!/usr/bin/env python3
"""Independent selection/lookup original with eager validation and missing pins."""
from pathlib import Path
import random,sys
HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'selection_lookup','6332cdb260f782ab8b47e2785e9b4d08bb924e5f8b8a293f840c3c4a33ea8bc8',14)
REFUSALS=[('ifn',[1,2,'bad']),('ifc',[1,'ok',2]),('ifc',[0,'x'*201,'ok']),('whichn',[1,1,True]),('whichc',['a','a','é'])]
REFUSALS += [(name,[index,1,2] if name=='choosen' else [index,'a','b']) for name in ('choosen','choosec') for index in (0,None,.5,3,-3,True)]
def main():
 GATE.qualify(REFUSALS)
 if '--qualify-only' in sys.argv:
  print('QUALIFIED: selection/lookup hand pins, invalid-index/eager refusals and complete hand/R original');return
 import sas_semantics as sem
 functions={name:getattr(sem,'sas_'+name) for name in ('ifn','ifc','choosen','choosec','whichn','whichc')}
 rng=random.Random(11113);cases=[]
 for _ in range(100):
  f=rng.choice([None,0,1,-2,.5]);values=[rng.choice([None,-5,0,2,9]) for _ in range(3)];idx=rng.choice([-3,-2,-1,1,2,3]);chars=[rng.choice(['A','B ',' C',' ']) for _ in range(3)]
  cases.extend([('ifn',[f,*values]),('ifc',[f,*chars]),('choosen',[idx,*values]),('choosec',[idx,*chars]),('whichn',values),('whichc',chars)])
 GATE.verify(functions,cases,REFUSALS,{'ifc':lambda a:200,'choosec':lambda a:200})
if __name__=='__main__':main()
