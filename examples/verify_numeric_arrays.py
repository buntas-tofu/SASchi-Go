#!/usr/bin/env python3
"""DS-039 original alias/snapshot pins and independent native base R."""
import csv
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import (sas_numeric_array_value, sas_numeric_array_index,
                           sas_numeric_array_add, sas_numeric_array_sum)
from saschi.plan import compile_plan
from saschi.runtime import run_plan

ORIGINAL_PROGRAM = '''data d;
array score{0:2} first second third;
first=3;
score[1]=5;
mirror=score{0};
if score{1}>3 then score[2]=score[0]+score[1];
total=sum(of score{*});
output;
first=11;
reverse=score[0];
output;
run;'''
PINS = [dict(first=3., second=5., third=8., mirror=3., total=16., reverse=None),
        dict(first=11., second=5., third=8., mirror=3., total=16., reverse=11.)]


def rrun(*args):
    r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r, str(HERE/'numeric_arrays.R'), *map(str, args)],
                          capture_output=True, text=True, check=True, timeout=60).stdout


def kind(value):
    if value is None: return 'missing'
    if isinstance(value, bool): return 'boolean'
    if isinstance(value, (int, float)): return 'number'
    if isinstance(value, str): return 'character'
    return 'other'


def main():
    plan = compile_plan(ORIGINAL_PROGRAM)
    assert not plan.blocked, plan.tickets
    result = run_plan(plan.to_dict())['datasets']['d']
    assert result == {'schema': dict.fromkeys(PINS[0], 'number'), 'rows': PINS}
    lines = rrun('alias').splitlines()
    assert lines == ['3|5|8|3|16|NA', '11|5|8|3|16|11']
    assert PINS[0]['mirror'] != None and PINS[1]['reverse'] != 3, 'copied-list controls must differ'
    assert PINS[0]['reverse'] is None, 'future descriptor must exist before its assignment'
    cases = []
    def case(operation, a=None, b=None, lower=1, size=3, values=None, expected=None, refused=False):
        cases.append(dict(operation=operation,a=a,b=b,lower=lower,size=size,values=values,
                          expected=expected,refused=refused))
    # Hand pins cover the missing-function contract, signed/custom bounds,
    # exact fractions, cancellation, subnormal storage and boundary values.
    for values, want in [([None,None],None),([None,3.,-1.],2.),([.5,None,-.25],.25),
                         ([-0.],0.),([2147483647.,-2147483647.],0.),([5e-324],5e-324)]:
        case('sum',values=values,expected=want)
    for lo,n,i,want in [(1,3,1,0),(1,3,3,2),(0,3,0,0),(-2,3,0,2),(1990,6,1993,3),
                        (-2147483647,1,-2147483647,0),(2147483647,1,2147483647,0),(1,1024,1024,1023)]:
        case('index',i,lower=lo,size=n,expected=want)
    for x in (None,.1,5e-324,2147483647.,-2147483647.):
        case('value',x,expected=x)
    pins = len(cases)
    rng = random.Random(3901)
    for _ in range(1000):
        values=[None if rng.randrange(5)==0 else rng.randint(-100000,100000)/64 for _ in range(rng.randint(1,32))]
        present=[x for x in values if x is not None]
        case('sum',values=values,expected=sum(present) if present else None)
    for _ in range(200):
        lo=rng.randint(-1990,1990); n=rng.randint(1,1024); i=rng.randrange(n)
        case('index',lo+i,lower=lo,size=n,expected=i)
        a,b=rng.randint(-100000,100000)/128,rng.randint(-100000,100000)/128
        case('add',a,b,expected=a+b); case('subtract',a,b,expected=a-b)
    constructive=len(cases)-pins
    for x in (True,False,'3',[],{}, {'missing':'A'},float('nan'),float('inf'),float('-inf'),2147483648,10**400):
        case('value',x,refused=True)
    for x in (None,True,'1',.5,0,4,2147483648):
        case('index',x,refused=True)
    for lo,n in ((1,0),(1,1025),(2147483647,2)):
        case('index',lo,lower=lo,size=n,refused=True)
    for xs in ([.1,.2],[2147483647,1,-1],[2147483647,1e-300,-2147483647]):
        case('sum',values=xs,refused=True)
    case('add',.1,.2,refused=True)
    case('subtract',1.,.1,refused=True)
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'cases.csv'
        with path.open('w',newline='') as stream:
            w=csv.writer(stream);w.writerow(['id','operation','a_kind','a','b_kind','b','lower','size','values'])
            for i,c in enumerate(cases):
                values='|'.join('M' if x is None else repr(x) for x in c['values']) if c['values'] is not None else 'M'
                w.writerow([i,c['operation'],kind(c['a']),str(c['a']),kind(c['b']),str(c['b']),c['lower'],c['size'],values])
        witness=rrun('cases',path).splitlines()
    assert len(witness)==len(cases)
    for i,(c,line) in enumerate(zip(cases,witness)):
        def actual():
            if c['operation']=='sum':return sas_numeric_array_sum(c['values'])
            if c['operation']=='value':return sas_numeric_array_value(c['a'])
            if c['operation']=='index':return sas_numeric_array_index(c['a'],c['lower'],c['size'])
            return sas_numeric_array_add(c['a'],c['b'],c['operation']=='subtract')
        if c['refused']:
            try:actual()
            except ValueError:pass
            else:raise AssertionError(('missing refusal',i,c))
            assert line==f'{i}:REFUSE',(i,line,c)
        else:
            want=c['expected'];got=actual();assert got==want,(i,got,want)
            assert line.startswith(f'{i}:OK:'),(i,line,c)
            field=line.split(':',2)[2]
            assert (None if field=='M' else float.fromhex(field))==want,(i,line,want)
    print(f'VERIFIED: numeric arrays{pins} pins,{constructive} constructive R cases,{sum(c["refused"] for c in cases)} shared refusals; original alias/OUTPUT source pins and independent base R; no live SAS or external-program promotion')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
