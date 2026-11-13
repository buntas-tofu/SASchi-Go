#!/usr/bin/env python3
"""Independent masks, signed positions and complete identifier program."""
from pathlib import Path
import random,sys
HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'ascii_positions','1c168e597f6c9c7c11e9851c12272af016072d53f5252cd7054c81c3fda86b5a',14)
NAMES=('anylower','anyupper','anypunct','anyxdigit','notalpha','notalnum','notspace')
REFUSALS=[(name,[value]) for name in NAMES for value in (None,True,1,{'missing':'A'},'é','a\tb','x'*32768)]
REFUSALS += [(name,['a',value]) for name in NAMES for value in (True,'1',{'missing':'A'},.5,2147483648)]
REFUSALS += [('anypunct',['_',None])]
def main():
 GATE.qualify(REFUSALS)
 if '--qualify-only' in sys.argv:
  print('QUALIFIED: ASCII masks, signed positions, hand/R original and refusals before implementation');return
 import sas_semantics as sem
 functions={name:getattr(sem,'sas_'+name) for name in NAMES}
 cases=[(name,[chr(c)]) for c in range(32,127) for name in NAMES]
 rng=random.Random(11013)
 for _ in range(80):
  value=''.join(chr(rng.randrange(32,127)) for _ in range(rng.randrange(1,25)));start=rng.choice([-99,-5,-1,0,1,5,99])
  cases.extend((name,[value,start]) for name in NAMES)
 GATE.verify(functions,cases,REFUSALS)
if __name__=='__main__':main()
