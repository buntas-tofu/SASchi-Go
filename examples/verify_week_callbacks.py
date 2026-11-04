#!/usr/bin/env python3
"""Original week FCMP/format/report qualification, bound to pre-engine pins."""
from pathlib import Path
from datetime import date,timedelta
import hashlib
import json
import random
import sys

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from week_callbacks_hand import build,callback
from picture_dates_hand import read_date
from format_gate_common import witness,frozen,execute,complete_cli_controls,ordered_equal

PINS={'result.json':'8c718b3de1f0db03ddda11571bd655412e9b5a05b978944978282e2c31132801','accounting.json':'152d75cf3b679a14da44d9c3867b81ac71de7040185cc67264f65b6a9a329b6d','trace.json':'d7c6ecf86155999556d8ecde098c85e1d1f01b2fd255b2918d71de22ea48f210'}


def source(records):
    before,rest=(HERE/'week_callbacks.sas').read_text().split('\n cards;\n',1);_,after=rest.split('\n;\n',1)
    return before+'\n cards;\n'+('\n'.join(records)+'\n' if records else '')+';\n'+after


def qualify():
    for token,monday,friday in [('02JAN1960','28DEC1959','08JAN1960'),('03JAN1960','28DEC1959','08JAN1960'),('04JAN1960','04JAN1960','08JAN1960'),('29FEB2000','28FEB2000','03MAR2000'),('31DEC2023','25DEC2023','05JAN2024'),('01JAN2024','01JAN2024','05JAN2024')]:
        assert callback(read_date(token),(2,0,0))==monday and callback(read_date(token),(7,1,-1))==friday
    text=(HERE/'week_callbacks.sas').read_text();assert hashlib.sha256(text.encode()).hexdigest()=='337ccc9da05df1e9b837d622f755ceee83e7844c009fd88d5fa06c61755bc9b8'
    hand=build(text);frozen(hand,PINS);assert ordered_equal(hand[0],json.loads((HERE/'week_callbacks_expected.json').read_text()));cases=[]
    rng=random.Random(8905);months=['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']
    texts=[text,source([]),source(['10 . 1']),source(['10 '+d+' '+str(i+1) for i,d in enumerate(['28DEC1959','29DEC1959','30DEC1959','31DEC1959','01JAN1960','02JAN1960','03JAN1960','04JAN1960'])])]
    for size in [1,1000]+[rng.randrange(2,35) for _ in range(10)]:
        rows=[]
        for i in range(size):
            day=date(1800,1,1)+timedelta(days=rng.randrange(700000));token=f'{day.day:02}{months[day.month-1]}{day.year:04}'
            rows.append(f'{10+i*80//size} {token} {i+1}')
        texts.append(source(rows))
    for text in texts:
        hand=build(text);assert all(ordered_equal(a,b) for a,b in zip(hand,witness(text,'week_callbacks.R'),strict=True));cases.append((text,hand))
    return cases


def main():
    cases=qualify()
    from saschi.week_callbacks import run_program,REPORT_CONTRACT
    from saschi.catalog import record_pass
    from saschi.plan import compile_plan
    for text,(expected,accounting,trace) in cases:
        execute(text,expected,accounting,trace,run_program)
        cat,c=record_pass(text,compile_plan(text))
        with cat:assert c.n_functions==accounting['functions']*2+accounting['formats'] and c.n_functions==c.n_matched
    text,(expected,accounting,_)=cases[0];wrong=complete_cli_controls(text,expected,accounting,REPORT_CONTRACT)
    print(f'VERIFIED: week FCMP/CMPLIB/callbacks/ORDER/span,{len(cases)} complete independent R cases,six literal calendar pins,all traces/runtime/emitted/CLI,{wrong} wrong controls; no live SAS')


if __name__=='__main__':main()
