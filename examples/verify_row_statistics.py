#!/usr/bin/env python3
"""Original bounded row-statistics gate with exact pairwise base-R witness."""
from pathlib import Path
import math,random,sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT/'examples'));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'row_statistics','d5a8f4a77b4a5c6062f7cfa0d9b3874566796476fb5d47fa0dea88ecf73d8c70',9)
REFUSALS=[(name,[value]) for name in ('median','range','var','std') for value in (True,{'missing':'A'},'1',.5,1000001,float('inf'),float('nan'))]
REFUSALS += [(name,args) for name in ('median','range','var','std') for args in ([],[1]*33,[None,'x'])]

def close(actual,wanted):
    if actual is None or wanted is None:return actual is wanted
    return type(actual) in (int,float) and type(wanted) in (int,float) and math.isfinite(actual) and abs(actual-wanted)<=32*sys.float_info.epsilon*max(1,abs(wanted))

def main():
    GATE.qualify(REFUSALS)
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: row-statistics hand pins,refusals and whole original pairwise-R oracle before implementation');return
    from sas_semantics import sas_median,sas_range,sas_row_var,sas_row_std
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    functions=dict(zip(('median','range','var','std'),(sas_median,sas_range,sas_row_var,sas_row_std)))
    rng=random.Random(10611);cases=[]
    for _ in range(100):
        args=[rng.choice([None,rng.randrange(-500,501)]) for _ in range(rng.randrange(1,10))]
        cases.extend((name,args) for name in functions)
    cases.extend((name,[1000000,-1000000]*16) for name in functions)
    all_cases=[(name,args) for name,args,_ in GATE.pins]+cases
    for (name,args),wanted in zip(all_cases,GATE.r_cases(all_cases)):
        actual=functions[name](*args);assert close(actual,wanted),(name,args,actual,wanted)
        literals=','.join('.' if x is None else repr(x) for x in args)
        source='data d;x='+name+'('+literals+');run;';plan=compile_plan(source);assert not plan.blocked,plan.tickets
        observed=run_plan(plan.to_dict())['datasets']['d']['rows'][0]['x']
        assert close(observed,wanted),(name,args,observed,wanted)
    GATE.verify(functions,cases,REFUSALS)

if __name__=='__main__':main()
