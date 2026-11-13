#!/usr/bin/env python3
"""Independent original text/quoting gate and discriminating byte cases."""
from pathlib import Path
import random,sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'text_quoting','c6583c460437424c72412255118b02ca80e9611b5f016c3b535fa656201ee68f',11)
REFUSALS=[(name,args) for name,args in [('propcase',['a','']),('propcase',['é',' ']),('quote',['a','x']),('quote',['x'*199]),('dequote',[None]),('countc',['abc','a','d']),('countc',['abc','x'*65]),('transtrn',['abc','','x']),('transtrn',['a','a','x'*65]),('transtrn',['a'*101,'a','xx'])]]
def main():
 GATE.qualify(REFUSALS)
 if '--qualify-only' in sys.argv:
  print('QUALIFIED: independent hand/R text quoting original, pins and refusals before translator implementation');return
 import sas_semantics as sem
 functions={name:getattr(sem,'sas_'+name) for name in ('propcase','quote','dequote','countc','transtrn')}
 # Zero-length replacement is a helper pin. Source deletion belongs to the separate consumer phase.
 helper_pins=GATE.pins;GATE.pins=[p for p in helper_pins if not any(v=='' for v in p[1])]
 assert functions['transtrn']('a-b-','-','')=='ab'
 rng=random.Random(10913);cases=[]
 for _ in range(80):
  value=''.join(rng.choice(' aAbB-._9"') for _ in range(rng.randrange(1,20)))
  cases.extend([('propcase',[value,' -']),('quote',[value]),('dequote',[value]),('countc',[value,'ab','ivt']),('transtrn',[value,'-','__'])])
 widths={'propcase':lambda a:len(a[0]),'quote':lambda a:200,'dequote':lambda a:len(a[0]),'transtrn':lambda a:200}
 GATE.verify(functions,cases,REFUSALS,widths)
 GATE.pins=helper_pins
if __name__=='__main__':main()
