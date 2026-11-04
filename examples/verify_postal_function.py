#!/usr/bin/env python3
"""Full original country/format/DSD/SORT/computed-report evidence, external results."""
from pathlib import Path
import hashlib
import json
import os
import random
import sys
import tempfile
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from postal_function_hand import build
from format_gate_common import witness,frozen,execute,complete_cli_controls,external_temporary,ordered_equal,encode
from verify_postal_reference import qualify as qualify_reference

PINS={'result.json':'c1d1a3b558a58b771342c8d5f9765f39775ea191d18f26d802e663310da002b8','accounting.json':'d04525d97af03b392e737e4ec7b5e6c6b1c64df9411659fcad116c0ec1601e2a','trace.json':'a127c5ef89447d2ae23727124363cabf9d7fe4f1357608363d618e270c7c1c2f'}


def source(records):
    before,rest=(HERE/'postal_function.sas').read_text().split('\n cards;\n',1);_,after=rest.split('\n;\n',1)
    return before+'\n cards;\n'+('\n'.join(records)+'\n' if records else '')+';\n'+after


def qualification(reference_path):
    text=(HERE/'postal_function.sas').read_text();assert hashlib.sha256(text.encode()).hexdigest()=='164119cf628c47a470e07071dd077020a81c2b754e6c90b4daf91ec81186bb2f'
    hand=build(text,reference_path);frozen(hand,PINS);texts=[text,source([]),source(['1,Person,Place,0200,AU']),source(['1,Person,Place,01040,US']),source(['1,Person,Place,00000,ZZ']),source(['1,"A, B",Place,0299,AU','2,"C ""D""",Place,0899,AU'])]
    from saschi.postal_reference import DOMAIN
    texts.append(source([f'{i+1},Person,Place,{code},US' for i,code in enumerate(DOMAIN)]))
    rng=random.Random(9306)
    for size in [1000]+[rng.randrange(2,25) for _ in range(4)]:
        records=[]
        for i in range(size):
            country,code=rng.choice([('US',c) for c in DOMAIN]+[('AU',c) for c in ['0200','0299','0800','0899','0900','0999','1225','8001']]+[('ZZ','00000')]);records.append(f'{i+1},Person,Place,{code},{country}')
        texts.append(source(records))
    cases=[]
    for text in texts:
        values=build(text,reference_path);assert all(ordered_equal(a,b) for a,b in zip(values,witness(text,'postal_function.R'),strict=True));cases.append((text,values))
    return cases


def main():
    raw,mapping=qualify_reference();os.environ['SASCHI_POSTAL_REFERENCE']=str(raw)
    from saschi.postal_function import run_program,REPORT_CONTRACT
    from saschi.catalog import record_pass
    from saschi.plan import compile_plan
    with external_temporary('saschi-postal-expectations-') as temp:
        path=Path(temp)/'reference.json';path.write_text(json.dumps(mapping,sort_keys=True,separators=(',',':'))+'\n')
        cases=qualification(path)
        for text,(expected,accounting,trace) in cases:
            execute(text,expected,accounting,trace,run_program);cat,c=record_pass(text,compile_plan(text))
            with cat:assert c.n_functions==c.n_matched==4*accounting['functions']+accounting['reports']
        text,(expected,accounting,_)=cases[0];wrong=complete_cli_controls(text,expected,accounting,REPORT_CONTRACT)
    print(f'VERIFIED: postal format/function/quoted DSD/owned SORT/computed REPORT,{len(cases)} whole independent R cases,all19ZIPs,1000rows,full traces/runtime/emitted/CLI,{wrong} wrong controls; all reference-derived results external; no live SAS')


if __name__=='__main__':main()
