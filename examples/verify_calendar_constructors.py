#!/usr/bin/env python3
"""Explicit civil constructors and seven-digit ordinal conversion gate."""
from pathlib import Path
import random,sys
HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'calendar_constructors','16bf11597a16548ea0f91db59e60d5f423308a9940b07b5c661e3b4677beeec6',11)
REFUSALS=[('hms',[24,0,0]),('hms',[0,60,0]),('hms',[0,0,-1]),('hms',[None,60,0]),('yyq',[24,1]),('yyq',[2024,0]),('yyq',[2024,5]),('yyq',[4000,1]),('datejul',[24001]),('datejul',[2023000]),('datejul',[2023366]),('datejul',[1900366]),('juldate7',[.5]),('juldate7',[True])]
def main():
 GATE.qualify(REFUSALS)
 if '--qualify-only' in sys.argv:
  print('QUALIFIED: civil calendar hand/base-R epoch/leap/year/quarter original and refusals');return
 import sas_semantics as sem
 functions={name:getattr(sem,'sas_'+name) for name in ('hms','yyq','datejul','juldate7')}
 rng=random.Random(11413);cases=[]
 for _ in range(100):
  year=rng.randrange(1753,4000);day=rng.randrange(1,366);quarter=rng.randrange(1,5)
  cases.extend([('hms',[rng.randrange(24),rng.randrange(60),rng.randrange(60)]),('yyq',[year,quarter]),('datejul',[year*1000+day]),('juldate7',[rng.randrange(-75604,745095)])])
 GATE.verify(functions,cases,REFUSALS)
if __name__=='__main__':main()
