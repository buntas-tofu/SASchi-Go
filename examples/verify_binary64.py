#!/usr/bin/env python3
"""Rounded scalar arithmetic, independent base-R source and logical-output evidence."""
import contextlib
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
ORIGINAL=HERE/'binary64_capture.sas'
ROKU=Path(os.environ.get('SASCHI_ROKU_CORPUS',ROOT.parent/'saschi-roku'/'corpus'))
EPS=2.**-52
LIMIT=2147483647.
PINS=[('+',.1,.2,.30000000000000004),('-',1.,.9,.09999999999999998),
      ('*',1.1,1.1,1.2100000000000002),('/',1.,3.,.3333333333333333),
      ('**',2.,3.,8.),('**',-2.,3.,-8.),('**',-2.,2.,4.),
      ('**',1.25,2.,1.5625),('**',7.,0.,1.),('**',0.,3.,0.),
      ('+',LIMIT,-1.,LIMIT-1),('sin',0.,0.,0.),('cos',0.,0.,1.),
      ('tan',0.,0.,0.),('atan',1.,0.,.7853981633974483),
      ('arsin',0.,0.,0.),('arcos',1.,0.,0.),('arcos',0.,0.,1.5707963267948966),
      ('+',None,2.,None),('*',None,0.,None),('/',2.,None,None),
      ('**',None,2.,None),('sin',None,0.,None),('+',-0.,0.,0.)]
FORMAT_PINS=[(None,'.'),(0.,'0'),(-0.,'0'),(12.,'12'),(-12.,'-12'),
             (99999999999.,'99999999999'),(.5,'0.5'),(-.5,'-0.5'),
             (1/3,'0.3333333333'),(math.pi,'3.1415926536'),
             (-.00099950016666494612,'-0.0009995'),
             (11.536959032815489,'11.536959033'),(.0001,'0.0001')]
BAD_VALUES=[True,False,'2',[],{}, {'missing':'A'},float('nan'),float('inf'),
            float('-inf'),2147483648.,-2147483648.,2.**-1074,10**400]
REFUSALS=[(op,a,b) for value in BAD_VALUES for op,a,b in
          (('+',value,1.),('*',None,value),('*',value,0.))]
REFUSALS += [('/',1.,0.),('**',0.,0.),('**',2.,.5),('**',2.,-1.),
             ('/',None,0.),('**',None,33.),('**',None,.5),
             ('**',1.,33.),('**',1000.,4.),('*',LIMIT,2.),('+',LIMIT,1.),
             ('-',-LIMIT,1.),('/',1e-300,1e8),('*',1e-300,1e-100),
             ('**',1e-300,2.),('sin',math.pi+.01,0.),('cos',-math.pi-.01,0.),
             ('tan',math.pi/4+.01,0.),('arsin',1.01,0.),('arcos',-1.01,0.)]
FORMAT_REFUSALS=[True,'1',float('nan'),float('inf'),{'missing':'A'},1e-5,
                 -.00001,1000000000.5,100000000000.,1.23456789005,
                 9.99999999999]


def kind(value):
    if value is None:return 'missing'
    if isinstance(value,bool):return 'boolean'
    if isinstance(value,(int,float)):return 'number'
    return 'other'


def literal(value):
    return '.' if value is None else repr(float(value))


def rrun(mode,path,check=True):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'binary64.R'),mode,str(path)],capture_output=True,
                          text=True,check=check,timeout=90)


def metric(a,b):
    return abs(a-b)/(EPS*max(1.,abs(a),abs(b)))


def close(a,b,budget=32):
    if a is None or b is None:return a is b
    return math.isfinite(a) and math.isfinite(b) and metric(a,b)<=budget


def assert_tree(a,b,budget=32):
    if isinstance(a,dict):
        assert isinstance(b,dict) and list(a)==list(b),(a,b)
        for key in a:assert_tree(a[key],b[key],budget)
    elif isinstance(a,list):
        assert isinstance(b,list) and len(a)==len(b),(a,b)
        for x,y in zip(a,b):assert_tree(x,y,budget)
    elif isinstance(a,(int,float)) and not isinstance(a,bool):assert close(a,b,budget),(a,b)
    else:assert a==b,(a,b)


def case_source(op,a,b):
    expression=f'a{op}b' if op in ('+','-','*','/','**') else f'{op}(a)'
    return f'data d;trigger=1**1;a={literal(a)};b={literal(b)};p={expression};run;'


def generated_cases():
    rng=random.Random(4801);cases=[]
    for i in range(600):
        op=('+','-','*','/')[i%4]
        a=rng.uniform(-1000,1000);b=rng.uniform(.125,1000)
        value={'+':lambda:a+b,'-':lambda:a-b,'*':lambda:a*b,'/':lambda:a/b}[op]()
        cases.append((op,a,b,value))
    for _ in range(200):
        a=rng.uniform(-4,4);b=float(rng.randrange(0,10));cases.append(('**',a,b,a**b))
    for i in range(400):
        op=('sin','cos','tan','arsin','arcos','atan')[i%6]
        a=rng.uniform(-.7,.7) if op=='tan' else rng.uniform(-.95,.95) if op in ('arsin','arcos') else rng.uniform(-3,3)
        fun={'arsin':math.asin,'arcos':math.acos}.get(op,getattr(math,op,None))
        cases.append((op,a,0.,fun(a)))
    return cases


def generated_formats():
    rng=random.Random(4802)
    return [rng.uniform(-1000.,1000.) for _ in range(400)]


def r_cases(cases):
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'cases.csv'
        with path.open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['id','op','a_kind','a','b_kind','b'])
            for index,(op,a,b) in enumerate(cases):writer.writerow([index,op,kind(a),str(a),kind(b),str(b)])
        records=rrun('cases',path).stdout.splitlines()
    assert len(records)==len(cases)
    return [line.split(':',2)[1:] for line in records]


def program_witness(path):
    lines=rrun('program',path).stdout.splitlines()
    result={'datasets':{},'log':[]}
    accounting={'statements':int(lines[0].split(':')[1]),'steps':[],'trips':[],'final_rows':[]}
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


def original_expected():
    first={'pi':math.pi,'total':1.3611111111111112,'i':4.,'selected':.49999999999999994,'missing':None}
    second={**first,'total':1.6944444444444444}
    fresh={'pi':math.pi,'answer':math.pi}
    return {'datasets':{'capture':{'schema':{n:'number' for n in first},'rows':[first,second]},
                        'fresh':{'schema':{n:'number' for n in fresh},'rows':[fresh]}},
            'log':['1.3611111111 0.5 . ','1.6944444444 ','3.1415926536 ']}


def original_accounting():
    expected=original_expected()
    return {'statements':21,'steps':['capture','fresh'],'trips':[3,0],
            'final_rows':[expected['datasets']['capture']['rows'][-1],expected['datasets']['fresh']['rows'][-1]]}


def series_expected():return {'datasets':{},'log':['1.6439345667 -0.0009995 ']}


def series_accounting():
    return {'statements':8,'steps':['_null_'],'trips':[1000],
            'final_rows':[{'s':1.6439345666815615,'n':1001.,'e':-.00099950016666494612}]}


def trig_expected():
    return {'datasets':{},'log':['0.5 0.5 ','0.8660254038 0.8660254038 ',
        '0.5773502692 0.5773502692 ','0.2013579208 11.536959033 ',
        '1.369438406 78.463040967 ','0.1973955598 11.309932474 ']}


def trig_accounting():
    return {'statements':25,'steps':['_null_'],'trips':[0],
            'final_rows':[{'pi':math.pi,'deg':30.,'rad':.5235987755982988,
                           'k':.017453292519943295,'x':.2,'a':.19739555984988078,
                           'b':11.309932474020215}]}


SOURCE_PINS={'binary64_capture.sas':'073e624986a2bb979567e8fff507dd111ff15b68061bf0c9f5024b60f49de526',
             'sum_of_a_series.sas':'0fd04c9914fcd4d1a517e20aef2fc271602b3c545f6a277f04065c3b745f7c68',
             'trigonometric_functions.sas':'d99125f923ad821c5d97754acf14c444841f088a9cfa6da617cd89c6edbf7b5a'}


def check_program(path,expected,accounting,budget=32):
    from saschi.emit_py import translate
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    independent,seen=program_witness(path)
    assert_tree(independent,expected,budget);assert_tree(seen,accounting,budget)
    text=path.read_text();plan=compile_plan(text);assert not plan.blocked,plan.tickets
    observed=run_plan(plan.to_dict());assert_tree(observed,expected,budget)
    translation=translate(text);assert not translation.blocked
    namespace={};stdout=io.StringIO()
    with contextlib.redirect_stdout(stdout):exec(translation.code,namespace)
    assert_tree(namespace['result'],expected,budget)
    assert stdout.getvalue()==''.join(log+'\n' for log in expected['log'])
    if accounting['steps']==['_null_']:
        # A separate in-memory observation variant exposes the numeric state.
        # Complete unchanged source acceptance above remains a distinct check.
        probe=text.replace('data _null_;','data observed;',1)
        probe_plan=compile_plan(probe);assert not probe_plan.blocked,probe_plan.tickets
        probe_result=run_plan(probe_plan.to_dict())
        final=accounting['final_rows'][0]
        assert_tree(probe_result,{'datasets':{'observed':{
            'schema':{n:'number' for n in final},'rows':[final]}},'log':expected['log']},budget)
    with tempfile.TemporaryDirectory() as directory:
        out=Path(directory)/'job'
        result=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--output',str(out)],
                              cwd=ROOT,capture_output=True,text=True,timeout=45)
        assert result.returncode==0,(result.stdout,result.stderr)
        assert_tree(json.loads((out/'result.json').read_text()),expected,budget)
        receipt=json.loads((out/'receipt.json').read_text());assert receipt['accepted']
        assert receipt['source_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    if path.name in SOURCE_PINS:assert hashlib.sha256(path.read_bytes()).hexdigest()==SOURCE_PINS[path.name]
    # A partial parser must fail on both unconsumed and truncated source.
    with tempfile.TemporaryDirectory() as directory:
        for index,bad in enumerate((text+'proc print;run;',text.rsplit('run;',1)[0])):
            changed=Path(directory)/f'bad{index}.sas';changed.write_text(bad)
            assert rrun('program',changed,check=False).returncode!=0


def main():
    from saschi.binary64 import arithmetic,apply,render_numeric_list
    from saschi.emit_py import translate
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    good=PINS+generated_cases()
    records=r_cases([(op,a,b) for op,a,b,_ in good]+REFUSALS)
    max_error=0.
    for index,((op,a,b,expected),record) in enumerate(zip(good,records)):
        observed=arithmetic(op,a,b) if op in ('+','-','*','/','**') else apply(op,[a])
        assert close(observed,expected),(op,a,b,expected,observed)
        assert record[0]=='OK',(index,record)
        independent=None if record[1]=='.' else float(record[1])
        assert close(observed,independent),(index,observed,independent)
        if observed is not None:max_error=max(max_error,metric(observed,independent))
        if observed==0:assert math.copysign(1.,observed)==1.
        source=case_source(op,a,b);plan=compile_plan(source);assert not plan.blocked,plan.tickets
        result=run_plan(plan.to_dict());assert close(result['datasets']['d']['rows'][0]['p'],independent)
        if index<len(PINS) or index%40==0:
            emitted=translate(source);assert not emitted.blocked
            namespace={}
            with contextlib.redirect_stdout(io.StringIO()):exec(emitted.code,namespace)
            assert_tree(namespace['result'],result)
    for (op,a,b),record in zip(REFUSALS,records[len(good):]):
        try:arithmetic(op,a,b) if op in ('+','-','*','/','**') else apply(op,[a])
        except (ValueError,TypeError):pass
        else:raise AssertionError(('missing refusal',op,a,b))
        assert record==['REFUSE'],(op,a,b,record)
    assert apply('constant',['pi'])==math.pi
    for values in ([],['e'],['pi',1.],[1.],[None]):
        try:apply('constant',values)
        except (ValueError,TypeError):pass
        else:raise AssertionError(('constant refusal',values))
    formatting=r_cases([('put',value,0.) for value,_ in FORMAT_PINS]+[('put',value,0.) for value in FORMAT_REFUSALS])
    for (value,expected),record in zip(FORMAT_PINS,formatting):
        assert render_numeric_list([value])==expected+' '
        assert record==['OK',expected.encode().hex()],(value,record)
    for value,record in zip(FORMAT_REFUSALS,formatting[len(FORMAT_PINS):]):
        try:render_numeric_list([value])
        except (ValueError,TypeError):pass
        else:raise AssertionError(('format refusal',value))
        assert record==['REFUSE'],(value,record)
    values=generated_formats();formatted=r_cases([('put',value,0.) for value in values])
    for value,record in zip(values,formatted):
        assert record[0]=='OK',(value,record)
        expected=bytes.fromhex(record[1]).decode()+' '
        assert render_numeric_list([value])==expected
        source=f'data _null_;trigger=1**1;a={literal(value)};put a;run;'
        plan=compile_plan(source);assert not plan.blocked,plan.tickets
        assert run_plan(plan.to_dict())=={'datasets':{},'log':[expected]}
    assert render_numeric_list([0.]*32)=='0 '*32
    try:render_numeric_list([0.]*33)
    except ValueError:pass
    else:raise AssertionError('logical row width refusal')
    for expression,value in (('2**3**2',512.),('-2**2',-4.),('(-2)**2',4.),('1/3**2',1/9)):
        plan=compile_plan(f'data d;p={expression};run;');assert not plan.blocked,plan.tickets
        assert close(run_plan(plan.to_dict())['datasets']['d']['rows'][0]['p'],value)
    check_program(ORIGINAL,original_expected(),original_accounting())
    check_program(ROKU/'sum_of_a_series.sas',series_expected(),series_accounting(),2048)
    check_program(ROKU/'trigonometric_functions.sas',trig_expected(),trig_accounting())
    for name in ('sum_of_a_series.sas', 'trigonometric_functions.sas'):
        print('VERIFIED corpus: '+name+'; complete unchanged source/runtime/emitted/CLI and sequential base-R witness; bounded binary64 numerical tolerance and inferred logical text policy, not exact SAS BEST12; no live SAS')
    # Five distinct naive implementations lose independent hand/profile controls.
    assert int(1/3)!=PINS[3][3]
    assert 2.**(3.**2.)!=(2.**3.)**2.
    assert abs(math.sin(30.)-.5)>.1
    assert math.isfinite(LIMIT*2) and ('*',LIMIT,2.) in REFUSALS
    assert format(1/3,'.17g')+' '!=render_numeric_list([1/3])
    print(f'VERIFIED: binary64 {len(PINS)} hand pins,1200 generated source/runtime/R cases,'
          f'{len(REFUSALS)} shared refusals,{len(FORMAT_PINS)} logical-format pins,'
          f'400 generated source/runtime/R decimal records,{len(FORMAT_REFUSALS)} format refusals,'
          f'5 naive controls; max normalized R error {max_error:g}; '
          'original21-statement witness and complete unchanged8-statement/1000-trip series,'
          '25-statement trigonometric programs, source/runtime/emitted/CLI; no live SAS')


if __name__=='__main__':main()
