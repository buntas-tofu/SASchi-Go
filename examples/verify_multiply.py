#!/usr/bin/env python3
"""B3 exact multiplication and independent base-R complete-program evidence."""
import contextlib
import csv
import io
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from sas_semantics import sas_multiply
from saschi.emit_py import translate
from saschi.plan import compile_plan
from saschi.runtime import run_plan

ORIGINAL=HERE/'numeric_composition_capture.sas'
TINY=2.**-1074
PINS=[(2.,3.,6.),(-2.,3.,-6.),(-2.,-3.,6.),(1.5,2.,3.),(.5,.5,.25),
      (1.25,2.5,3.125),(.875,-.75,-.65625),(0.,-7.,0.),(-0.,3.,0.),
      (2147483647.,1.,2147483647.),(2147483647.,.5,1073741823.5),
      (46340.,46340.,2147395600.),(TINY,1.,TINY),(2.**-1022,.5,2.**-1023),
      (2.**-537,2.**-537,TINY),(1+2.**-52,.5,.5+2.**-53),
      (None,2.,None),(2.,None,None),(None,None,None),(-0.,None,None)]
BAD_VALUES=[True,False,'2',[],{}, {'missing':'A'},float('nan'),float('inf'),
            float('-inf'),2147483648,-2147483648,10**400]
REFUSALS=[pair for value in BAD_VALUES for pair in ((value,1.),(1.,value),(None,value),(value,None))]
REFUSALS += [(1+2.**-52,1+2.**-52),(2147483647.,2147483647.),(46341.,46341.),
             (2147483647.,1+2.**-52),(2.**-538,2.**-537),(TINY,.5),(TINY,1.5),
             (2.**-1022,2.**-1022),(1e-200,1e-200),(2.**-600,2.**-600),(1.1,1.1),
             (0.,2147483648.),(2147483648.,0.)]


def kind(value):
    if value is None:return 'missing'
    if isinstance(value,bool):return 'boolean'
    if isinstance(value,(int,float)):return 'number'
    return 'other'


def literal(value):
    return '.' if value is None else repr(float(value))


def source(a,b,body=''):
    return f'data d;a={literal(a)};b={literal(b)};p=a*b;'+body+'run;'


def rrun(mode,path):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'multiply.R'),mode,str(path)],capture_output=True,
                          text=True,check=True,timeout=90).stdout


def original_expected():
    names=['first','second','third','factor','i','total','product','untouched']
    rows=[[3.,4.,None,2.,3.,7.,12.,None],[6.,4.,None,2.,3.,7.,24.,None]]
    fresh_names=['first','second','i','product']
    return {'datasets':{'capture':{'schema':{n:'number' for n in names},
                                  'rows':[dict(zip(names,row)) for row in rows]},
                        'fresh':{'schema':{n:'number' for n in fresh_names},
                                 'rows':[dict(zip(fresh_names,[6.,8.,2.,48.]))]}},
            'log':['7 24 . ','48 ']}


def original_accounting():
    expected=original_expected()
    return {'statements':28,'steps':['capture','fresh'],'trips':[3,2],
            'final_rows':[expected['datasets']['capture']['rows'][-1],
                          expected['datasets']['fresh']['rows'][-1]]}


def array_expected():
    return {'datasets':{},'log':['338350 . ']}


def array_accounting():
    # Hand arithmetic: sum of the first100 squares is100*101*201/6=338350.
    row={f'a{i}':float(i*i) for i in range(1,101)}
    row.update(i=101.,b=338350.,c=None)
    return {'statements':8,'steps':['_null_'],'trips':[100],'final_rows':[row]}


def program_witness(path):
    lines=rrun('program',path).splitlines()
    result={'datasets':{},'log':[]};accounting={'statements':int(lines[0].split(':')[1]),
                                            'steps':[],'trips':[],'final_rows':[]}
    table=None;schema=[]
    for line in lines[1:]:
        tag,value=line.split(':',1)
        if tag=='STEP':
            accounting['steps'].append(value);table={'schema':{},'rows':[]}
            if value!='_null_':result['datasets'][value]=table
        elif tag=='SCHEMA':
            schema=value.split(',') if value else [];table['schema']={n:'number' for n in schema}
        elif tag=='TRIPS':accounting['trips'].append(int(value))
        elif tag in ('FINAL','ROW'):
            row=dict(zip(schema,[None if x=='.' else float(x) for x in value.split(',')]))
            if tag=='FINAL':accounting['final_rows'].append(row)
            else:table['rows'].append(row)
        elif tag=='LOG':result['log'].append(bytes.fromhex(value).decode('ascii'))
        else:raise AssertionError(line)
    return result,accounting


def generated_cases():
    rng=random.Random(4501);cases=[]
    for _ in range(600):
        a=rng.randint(-40000,40000)/(2.**rng.randint(0,12))
        b=rng.randint(-1000,1000)/(2.**rng.randint(0,8))
        cases.append((a,b,a*b))
    for _ in range(400):
        shift=rng.randint(-300,18);power=rng.randint(-20,10)
        a=(1+rng.randint(0,1024)/1024.)*(2.**shift)
        if rng.randrange(2):a=-a
        b=2.**power
        cases.append((a,b,a*b))
    for i in range(200):
        value=rng.randint(-100000,100000)/64.
        cases.append((None,value,None) if i%2 else (value,None,None))
    return cases


def main():
    good=PINS+generated_cases()
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'cases.csv'
        with path.open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['id','a_kind','a','b_kind','b'])
            for i,(a,b) in enumerate([(a,b) for a,b,_ in good]+REFUSALS):
                writer.writerow([i,kind(a),str(a),kind(b),str(b)])
        records=rrun('cases',path).splitlines()
    assert len(records)==len(good)+len(REFUSALS)
    for i,((a,b,expected),record) in enumerate(zip(good,records)):
        observed=sas_multiply(a,b);assert observed==expected,(a,b,expected,observed)
        if observed==0:assert math.copysign(1.,observed)==1.
        expected_r='.' if expected is None else format(expected,'.17g')
        assert record.startswith(f'{i}:OK:'),(i,record)
        encoded=record.split(':',2)[2]
        assert (encoded=='.' if expected is None else float(encoded)==expected),(i,record,expected_r)
        plan=compile_plan(source(a,b));assert not plan.blocked,plan.tickets
        result=run_plan(plan.to_dict());row={'a':a,'b':b,'p':expected}
        assert result=={'datasets':{'d':{'schema':{n:'number' for n in row},'rows':[row]}},'log':[]}
        if i<len(PINS) or i%40==0:
            emitted=translate(source(a,b));assert not emitted.blocked
            namespace={}
            with contextlib.redirect_stdout(io.StringIO()):exec(emitted.code,namespace)
            assert namespace['result']==result
    for index,((a,b),record) in enumerate(zip(REFUSALS,records[len(good):]),len(good)):
        try:sas_multiply(a,b)
        except ValueError:pass
        else:raise AssertionError(('missing multiplication refusal',a,b))
        assert record==f'{index}:REFUSE',(index,record)
    independent,accounting=program_witness(ORIGINAL)
    plan=compile_plan(ORIGINAL.read_text());assert not plan.blocked,plan.tickets
    assert run_plan(plan.to_dict())==independent==original_expected()
    assert accounting==original_accounting()
    # Four plausible shortcuts lose separate hand/profile controls.
    assert int(PINS[5][0]*PINS[5][1])!=PINS[5][2]
    assert PINS[16][2] is None and 0.*PINS[16][1]!=PINS[16][2]
    assert math.isfinite((1+2.**-52)*(1+2.**-52)) and (1+2.**-52,1+2.**-52) in REFUSALS
    assert math.isfinite(2147483647.**2) and (2147483647.,2147483647.) in REFUSALS
    print(f'VERIFIED: multiplication {len(PINS)} hand pins,1200 constructive source/runtime/R cases,'
          f'{len(REFUSALS)} shared refusals,4 naive controls and original two-step/three-snapshot program; '
          'independent base-R bit-product witness; no live SAS')


if __name__=='__main__':main()
