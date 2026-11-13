#!/usr/bin/env python3
"""Exact integer-domain rank/squares oracle with cancellation-sensitive pins."""
from pathlib import Path
import random,sys
HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'rank_squares','fb7e609f79f76cf9d3f5a3cac6fd8daf1a6cf678e61744af0295f59f07023c68',10)
REFUSALS=[(name,args) for name in ('largest','smallest') for args in ([0,1,2],[None,1,2],[-1,1,2],[.5,1,2],[3,1,2],[1,1,'2'],[1,1,True])]
REFUSALS += [(name,[value]) for name in ('css','uss') for value in (True,'1',{'missing':'A'},.5,1000001)]
def main():
 GATE.qualify(REFUSALS)
 if '--qualify-only' in sys.argv:
  print('QUALIFIED: independent pairwise CSS, USS, rank/missing hand pins and complete original');return
 import sas_semantics as sem
 functions={name:getattr(sem,'sas_'+name) for name in ('largest','smallest','css','uss')}
 rng=random.Random(11213);cases=[]
 for _ in range(120):
  values=[rng.choice([None,-1000000,-2,0,1,2,999998,999999,1000000]) for _ in range(rng.randrange(1,33))];k=rng.randrange(1,len(values)+1)
  cases.extend([('largest',[k,*values]),('smallest',[k,*values]),('css',values),('uss',values)])
 GATE.verify(functions,cases,REFUSALS)
if __name__=='__main__':main()
