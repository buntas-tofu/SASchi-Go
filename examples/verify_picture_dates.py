#!/usr/bin/env python3
"""Original date PICTURE composition with independently qualified whole R output."""
from pathlib import Path
import hashlib
import json
import random
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from picture_dates_hand import build
from format_gate_common import witness,frozen,execute,complete_cli_controls,ordered_equal

FROZEN={'result.json':'682283b069b14c2da97fcf66580ab248f513600fdbe125f9312d7145d91db055',
        'accounting.json':'88c8ca2d3f7a2d142a225f9386def8034dc34123c97acc8e0694a620bfb3fca8',
        'trace.json':'3f6905f682cea51507112e33ebe3674a3cf398ce650abad392096fd8db83dd2d'}
SOURCE_SHA='1f3b091c00a572d776fc561ac9f913497f1515032145fcf7aac655b871b8928b'


def record_source(cards):
    text=(HERE/'picture_dates.sas').read_text();before,after=text.split('\ncards;\n',1);_,tail=after.split('\n;\n',1)
    return before+'\ncards;\n'+('\n'.join(cards)+'\n' if cards else '')+';\n'+tail


def qualify():
    text=(HERE/'picture_dates.sas').read_text();assert hashlib.sha256(text.encode()).hexdigest()==SOURCE_SHA
    original=build(text);frozen(original,FROZEN)
    assert ordered_equal(original[0],json.loads((HERE/'picture_dates_expected.json').read_text()))
    assert all(ordered_equal(a,b) for a,b in zip(original,witness(text,'picture_dates.R'),strict=True))
    rng=random.Random(8203);cases=[(text,original)]
    pairs=['31DEC1989','01APR1990','31MAR1993','01APR1993','01JAN1753','31DEC3999','29FEB2000','.']
    for size in [0,1,8,1000]+[rng.randrange(2,31) for _ in range(12)]:
        cards=[f'{chr(65+i%26)} {rng.choice(pairs)} {i}' for i in range(size)]
        candidate=record_source(cards)
        if 1<size<1000:
            candidate=candidate.replace("'%Y|%b|%0d   '","'%d %B %Y %%   '")
            candidate=candidate.replace('var id label arrived;','var arrived label id;')
        hand=build(candidate);independent=witness(candidate,'picture_dates.R')
        assert all(ordered_equal(a,b) for a,b in zip(hand,independent,strict=True)),'constructive whole hand/R differs'
        cases.append((candidate,hand))
    return cases


def main():
    cases=qualify()
    from saschi.picture_dates import run_program,REPORT_CONTRACT
    for text,(expected,accounting,trace) in cases:execute(text,expected,accounting,trace,run_program)
    text,(expected,accounting,_)=cases[0]
    wrong=complete_cli_controls(text,expected,accounting,REPORT_CONTRACT)
    print(f'VERIFIED: date-picture original composition,{len(cases)} whole independent R cases,complete traces/runtime/emitted/CLI,{wrong} wrong controls; no live SAS or physical layout claim')


if __name__=='__main__':main()
