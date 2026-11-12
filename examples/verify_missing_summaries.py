#!/usr/bin/env python3
"""Independent typed row-summary and missing-value gates, no live SAS."""
from pathlib import Path
import random
import sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'missing_summaries','0a3b48ea0cf17a58a334303523e2d66169cd4c35dbc885098b71e9e9502c0383',12)
REFUSALS=[('n',['1']),('nmiss',[True]),('cmiss',[{'missing':'?'}]),('missing',['é']),('missing',[float('inf')]),
 ('coalesce',[None,'1']),('coalesce',[{'missing':'A'},1]),('coalescec',['A',None]),('coalescec',['X'*201]),
 ('mean',[1.5,2]),('mean',[{'missing':'A'},2]),('mean',[2147483648]),('n',[0]*33)]

def main():
    GATE.qualify(REFUSALS)
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: missing/summary scalar pins,shared refusals and complete original hand/R oracle before implementation');return
    from sas_semantics import sas_missing_function,sas_n,sas_nmiss,sas_cmiss,sas_coalesce,sas_coalescec,sas_row_mean
    rng=random.Random(9911);cases=[]
    for _ in range(100):
        values=[rng.choice([None,rng.randrange(-100,101)]) for _ in range(rng.randrange(1,9))]
        text=rng.choice(['',' ',' A ','X'])
        cases.extend([('missing',[text]),('n',values),('nmiss',values),('cmiss',[text,*values]),('coalesce',values),('coalescec',[text,'fallback']),('mean',values)])
    GATE.verify({'missing':sas_missing_function,'n':sas_n,'nmiss':sas_nmiss,'cmiss':sas_cmiss,'coalesce':sas_coalesce,'coalescec':sas_coalescec,'mean':sas_row_mean},cases,REFUSALS,{'coalescec':lambda a:200})

if __name__=='__main__':main()
