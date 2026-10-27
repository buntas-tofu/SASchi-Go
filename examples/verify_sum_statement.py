#!/usr/bin/env python3
"""DS-034 original pins and independent base R, no live SAS."""
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
from sas_semantics import sas_sum_statement
from saschi.plan import compile_plan
from saschi.runtime import run_plan

PINS = [(None,None,0.), (None,3.,3.), (7.,None,7.), (0.,0.,0.),
        (3.,-3.,0.), (-2.,-.5,-2.5), (.25,.5,.75), (2**52,1.,2**52+1)]


def rrun(mode, path='unused'):
    r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'sum_statement.R'),mode,str(path)],
                          capture_output=True,text=True,check=True,timeout=60).stdout


def main():
    rng = random.Random(3401)
    good = PINS + [(a/8,b/8,(a+b)/8) for a,b in
                   [(rng.randint(-100000,100000),rng.randint(-100000,100000)) for _ in range(1000)]]
    bad = [(value,1.,None) for value in (True,False,'1',[],{}, {'missing':'A'},
                                       float('nan'),float('inf'),float('-inf'),10**400)]
    bad += [(1.,a,None) for a,_,_ in bad] + [(1e308,1e308,None)]
    def kind(value):
        if value is None: return 'missing'
        if isinstance(value,bool): return 'boolean'
        if isinstance(value,(int,float)): return 'number'
        return 'other'
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'cases.csv'
        with path.open('w',newline='') as stream:
            w=csv.writer(stream); w.writerow(['id','a_kind','a','b_kind','b'])
            for i,(a,b,_) in enumerate(good+bad): w.writerow([i,kind(a),str(a),kind(b),str(b)])
        independent=rrun('cases',path).splitlines()
    assert len(independent)==len(good)+len(bad)
    for i,((a,b,expected),answer) in enumerate(zip(good+bad,independent)):
        if i<len(good):
            assert sas_sum_statement(a,b)==expected,(i,a,b)
            assert answer.startswith(f'{i}:OK:') and float(answer.split(':')[2])==expected,(i,answer)
        else:
            try: sas_sum_statement(a,b)
            except ValueError: pass
            else: raise AssertionError(('missing sum refusal',i))
            assert answer==f'{i}:REFUSE',(i,answer)
    source='data d; set raw; total+x; retain total 10; run;'
    plan=compile_plan(source); assert not plan.blocked,plan.tickets
    catalog={'raw':{'schema':{'x':'number'},'rows':[{'x':x} for x in (None,2.,-.5,None,4.)]}}
    result=run_plan(plan.to_dict(),catalog)['datasets']['d']
    expected=[10.,12.,11.5,11.5,15.5]
    assert [r['total'] for r in result['rows']]==expected
    assert list(map(float,rrun('program').strip().split('|')))==expected
    # Naive assignment misses retention, initialization, and missing increments.
    assert [None]*5 != expected and None != sas_sum_statement(None,None)
    print(f'VERIFIED: sum statement {len(PINS)} pins,1000 dyadic R cases,{len(bad)} shared refusals, '
          'explicit RETAIN/prefix witness and naive controls; repository/base-R only')


if __name__=='__main__': main()
