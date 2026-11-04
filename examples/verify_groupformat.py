#!/usr/bin/env python3
"""Original GROUPFORMAT/detail REPORT, with independent complete hand/base-R output."""
from pathlib import Path
import hashlib
import json
import random
import sys

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from groupformat_hand import build
from format_gate_common import witness,frozen,execute,complete_cli_controls,ordered_equal

FROZEN={'result.json':'1750dede98132286c28f6b22ce127d938f53153e99e4accb941b9f3c58ccbb8b',
        'accounting.json':'e2b4b7d763da2da0e754604d7672ce26751e1ddfc6f89e51864b932e917304bf',
        'trace.json':'cae944426edc731f2402ffc09542860a8964c939e54df66443fd4df44570955c'}
SOURCE_SHA='a14d6f87d2dcb3aa352896f450bd1dd5f9c2e5dd72649205cd75088fb27cf063'


def source(records):
    text=(HERE/'groupformat.sas').read_text();before,after=text.split('\ncards;\n',1);_,tail=after.split('\n;\n',1)
    return before+'\ncards;\n'+('\n'.join(records)+'\n' if records else '')+';\n'+tail


def qualify():
    text=(HERE/'groupformat.sas').read_text();assert hashlib.sha256(text.encode()).hexdigest()==SOURCE_SHA
    original=build(text);frozen(original,FROZEN)
    assert ordered_equal(original[0],json.loads((HERE/'groupformat_expected.json').read_text()))
    assert all(ordered_equal(a,b) for a,b in zip(original,witness(text,'groupformat.R'),strict=True))
    # Literal row identities distinguish raw-key grouping from formatted grouping
    # and preserve two OUTPUT calls for the one-row final formatted group.
    assert [row['id'] for row in original[0]['datasets']['ends']['rows']]==[1.,3.,4.,5.,6.,6.]
    cases=[(text,original)];rng=random.Random(8503)
    for size in [0,1,500]+[rng.randrange(2,45) for _ in range(15)]:
        salaries=sorted(rng.choices([0,1,4,8,9,10,11,19,20,21,22,30],k=size))
        records=[f'{i+1} {salary} {rng.choice(["01JAN1960","31DEC1959","29FEB2000","."])}' for i,salary in enumerate(salaries)]
        text=source(records)
        if 1<size<500 and size%2:text=text.replace("10-<20='Mid'","10-<20='Low'")
        hand=build(text);independent=witness(text,'groupformat.R')
        assert all(ordered_equal(a,b) for a,b in zip(hand,independent,strict=True)),'whole GROUPFORMAT hand/R differs'
        cases.append((text,hand))
    return cases


def main():
    cases=qualify()
    from saschi.groupformat import run_program,REPORT_CONTRACT
    for text,(expected,accounting,trace) in cases:execute(text,expected,accounting,trace,run_program)
    text,(expected,accounting,_)=cases[0];wrong=complete_cli_controls(text,expected,accounting,REPORT_CONTRACT)
    print(f'VERIFIED: numeric GROUPFORMAT/detail REPORT,{len(cases)} full independent R cases,raw/formatted boundaries,ties,dual OUTPUT,complete traces/runtime/emitted/CLI,{wrong} wrong controls; no live SAS')


if __name__=='__main__':main()
