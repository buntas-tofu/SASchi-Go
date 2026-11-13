#!/usr/bin/env python3
"""Exact binary64 zero-fuzz slice with tie-neighbor discriminators."""
from pathlib import Path
import math,random,sys
HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'zero_fuzz_numeric','7f48de126249be4cd0c9b50f70f532bb9286a3681c04fba69f4396fee73b8024',11)
REFUSALS=[(name,[value]) for name in ('ceilz','floorz','intz','roundz') for value in (True,'1',{'missing':'A'},1000001,2**-41)]
REFUSALS += [(name,[1,unit]) for name in ('roundz','modz') for unit in (0,.1,3,2**11,2**-11)]
REFUSALS += [('roundz',[1,-1]),('modz',[True,1])]
for exponent in range(-10,11):
 unit=2.**exponent
 for neighbor in (math.nextafter(unit,0.),math.nextafter(unit,math.inf)):
  REFUSALS.extend([('roundz',[1,neighbor]),('modz',[1,neighbor]),('modz',[1,-neighbor])])
def main():
 GATE.qualify(REFUSALS)
 if '--qualify-only' in sys.argv:
  print('QUALIFIED: zero-fuzz hand/base-R exact ties, neighbors, signed remainders, bounded original');return
 import sas_semantics as sem
 functions={name:getattr(sem,'sas_'+name) for name in ('ceilz','floorz','intz','roundz','modz')}
 rng=random.Random(11313);cases=[]
 for _ in range(100):
  x=rng.randrange(-10000,10001)/8;unit=2.**rng.randrange(-10,11)
  cases.extend([(name,[x]) for name in ('ceilz','floorz','intz')]+[('roundz',[x,unit]),('modz',[x,unit*rng.choice([-1,1])])])
 for tie in [-3.5,-2.5,-.5,.5,2.5,3.5]:
  cases.extend(('roundz',[x]) for x in (math.nextafter(tie,-math.inf),tie,math.nextafter(tie,math.inf)))
 GATE.verify(functions,cases,REFUSALS)
 for name in functions:
  result=functions[name](-0.,1) if name=='modz' else functions[name](-0.)
  assert result==0 and math.copysign(1.,result)==1
if __name__=='__main__':main()
