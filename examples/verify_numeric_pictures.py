#!/usr/bin/env python3
"""Original whole-source numeric PICTURE evidence, including explicit BOM framing."""
from pathlib import Path
import hashlib
import json
import random
import re
import sys

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from numeric_pictures_hand import build
from format_gate_common import witness,frozen,execute,complete_cli_controls,ordered_equal

PINS={
 'result.json':'4112fb71e3ba8b01a82897dfaf3986ccb7754ed37744590e9d3b7480efe30bf3',
 'accounting.json':'d75f7db6e2d398704f94dce822e86f60ff63b02b6c3a4fb24625ac2f632511e1',
 'trace.json':'bf9a67d939eb7f8b7f06dbae0acac803eabdf619be0207680d250e90b48bd697'}
BOM_PINS={**PINS,'accounting.json':'d821116fceb9874cc552b212fccb2d02b08e5aab3fdb4be0af8d538cb7d7d0d9','trace.json':'e96187c95581813e845a2b29179775fa90372ab387b436d3a002407320d0eb28'}


def source(records):
    before,rest=(HERE/'numeric_pictures.sas').read_text().split('\ndatalines;\n',1);_,tail=rest.split('\n;\n',1)
    return before+'\ndatalines;\n'+('\n'.join(records)+'\n' if records else '')+';\n'+tail


def qualify():
    text=(HERE/'numeric_pictures.sas').read_text();assert hashlib.sha256(text.encode()).hexdigest()=='279f4a2d9a386586d4eae70ed6a9c161a5d0b879af93b7d51c48767d19f126e9'
    cases=[]
    for prefix,pins in [('',PINS),('\ufeff',BOM_PINS)]:
        item=prefix+text;hand=build(item);frozen(hand,pins)
        assert ordered_equal(hand[0],json.loads((HERE/'numeric_pictures_expected.json').read_text()))
        assert all(ordered_equal(a,b) for a,b in zip(hand,witness(item,'numeric_pictures.R'),strict=True));cases.append((item,hand))
    for spec in ["'09 minutes'","'99 minutes'","'9999999999 value'","' Message 10' (noedit)"]:
        item=re.sub(r'picture (usr_[a-z]+) .*?;',lambda m:'picture '+m[1]+' low-high='+spec+';',text,flags=re.S)
        hand=build(item);assert all(ordered_equal(a,b) for a,b in zip(hand,witness(item,'numeric_pictures.R'),strict=True));cases.append((item,hand))
    rng=random.Random(8704)
    for size in [0,1,1000]+[rng.randrange(2,30) for _ in range(10)]:
        records=[str(rng.choice([-999999999,-100,-1,0,1,2,9,10,11,19,20,26,99,100,101,999999999]))+' ABC' for _ in range(size)]
        text=source(records);text=('\ufeff' if size%2 else '')+text
        hand=build(text);assert all(ordered_equal(a,b) for a,b in zip(hand,witness(text,'numeric_pictures.R'),strict=True));cases.append((text,hand))
    return cases


def main():
    cases=qualify()
    from saschi.numeric_pictures import run_program,REPORT_CONTRACT
    for text,(expected,accounting,trace) in cases:execute(text,expected,accounting,trace,run_program)
    wrong=0
    for text,(expected,accounting,_) in cases[:2]:wrong+=complete_cli_controls(text,expected,accounting,REPORT_CONTRACT)
    print(f'VERIFIED: numeric PICTURE,{len(cases)} full independent R cases,ASCII/BOM,all rows/traces/runtime/emitted/CLI,{wrong} wrong controls; held vendor original excluded; no live SAS')


if __name__=='__main__':main()
