#!/usr/bin/env python3
"""Original ASCII character editing gate with independent base-R witnesses."""
from pathlib import Path
import random
import sys
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT))
from wave_gate_common import FamilyGate
GATE=FamilyGate(HERE,'character_rewriting','2ef78674aa176ee94aa9c3dad65d1f14581b2eb8cfc3e8d113b25e71a30f9ede',10)
REFUSALS=[('compress',['']),('compress',[None]),('compress',['é']),('compress',['abc','']),('compress',['abc','a','Q']),
 ('translate',['abc','x','ab']),('translate',['abc','xy','aa']),('translate',['abc','x','']),
 ('tranwrd',['abc','','x']),('tranwrd',['abc','a','x'*65]),('tranwrd',['aaaa','a','x'*64]),
 ('tranwrd',['x'*201,'a','b']),('tranwrd',['abc','a','é'])]

def main():
    GATE.qualify(REFUSALS)
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: character rewrite hand pins,shared refusals and complete original hand/R oracle before implementation');return
    from sas_semantics import sas_compress,sas_translate,sas_tranwrd
    rng=random.Random(9811);cases=[]
    for _ in range(120):
        text=''.join(rng.choice(' abAB-_.') for _ in range(rng.randrange(1,25)))
        cases.extend([('compress',[text,'aB',rng.choice(['','I','K','IK'])]),('translate',[text,'12','ab']),('tranwrd',[text,'ab',rng.choice(['','X','zz'])])])
    cases.extend([('compress',['x'*32767]),('translate',['x'*32767,'y','x'])])
    GATE.verify({'compress':sas_compress,'translate':sas_translate,'tranwrd':sas_tranwrd},cases,REFUSALS,{'compress':lambda a:len(a[0]),'translate':lambda a:len(a[0]),'tranwrd':lambda a:200})

if __name__=='__main__':main()
