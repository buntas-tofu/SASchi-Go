#!/usr/bin/env python3
"""DS-058/059 whole-source comma/range witnesses and actual comparison controls."""
from copy import deepcopy
import contextlib
import hashlib
import io
import json
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
from saschi.compare import equal
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.emit_py import translate
from saschi.input_numeric import expand_terms

ORIGINAL=HERE/'inline_csv_capture.sas'
SOURCE_PIN='e4ef1b6fc8ca978bb789acf834b2d61277a2646e1372809019aa8739c50527c2'
RESULT_PIN='f66eb9179e91325ba6512bc871a66543758a6d9f1cff7af25bf5c3d97e81f735'
STDOUT_PIN='66b5baec970c71d09eda39dbd16da8501f5b173278c03d76b573ada7bdf69d31'


def source(records,names='x1-x2',body='',prefix='',comma=True,firstobs=1,header='datalines'):
    infile=("infile "+header+" dlm=',' firstobs="+str(firstobs)+';') if comma else ''
    return 'data d;'+prefix+infile+'input '+names+';'+body+header+';\n'+''.join(r+'\n' for r in records)+';\nrun;'


def table(names,rows,log=None):
    return {'datasets':{'d':{'schema':dict.fromkeys(names,'number'),
            'rows':[dict(zip(names,row)) for row in rows]}},'log':[] if log is None else log}


def original_expected():
    names=('total','x1','x2','before','scratch','seq')
    rows=[[1.,1.,2.,None,1.,1.],[1.,99.,2.,None,1.,1.],
          [1.,None,5.,None,None,2.],[1.,99.,5.,None,None,2.],[5.,4.,None,None,4.,3.]]
    return {'datasets':{'capture':{'schema':dict.fromkeys(names,'number'),'rows':[dict(zip(names,row)) for row in rows]},
            'ranges':{'schema':dict.fromkeys(('v62','v63','v64','summed'),'number'),
                      'rows':[{'v62':1.,'v63':None,'v64':3.,'summed':4.},dict.fromkeys(('v62','v63','v64','summed'))]}},
            'log':['total=1 seq=1','total=1 seq=2','total=5 seq=3']}


def execute(text,emitted=False):
    parsed=compile_plan(text);assert not parsed.blocked,parsed.tickets
    plan=parsed.to_dict();before=deepcopy(plan);observed=run_plan(plan);assert plan==before
    if emitted:
        namespace={};stdout=io.StringIO()
        with contextlib.redirect_stdout(stdout):exec(translate(text).code,namespace)
        assert equal(namespace['result'],observed,ordered_maps=True)
        assert stdout.getvalue()==''.join(line+'\n' for line in observed['log'])
    return observed


def rrun(*args):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'inline_csv.R'),*map(str,args)],capture_output=True,text=True,check=True,timeout=60)


def decode_program(lines):
    result={'datasets':{},'log':[]};steps=[];reads=[];current=None;names=[]
    assert lines and lines[0].startswith('STATEMENTS:')
    for line in lines[1:]:
        kind,value=line.split(':',1)
        if kind=='STEP':
            steps.append(value);current={'schema':{},'rows':[]}
            if value!='_null_':result['datasets'][value]=current
        elif kind=='SCHEMA':names=value.split(',');current['schema']=dict.fromkeys(names,'number')
        elif kind=='READS':reads.append(int(value))
        elif kind=='ROW':current['rows'].append(dict(zip(names,[None if x=='.' else float(x) for x in value.split(',')])))
        elif kind=='LOG':result['log'].append(bytes.fromhex(value).decode('ascii'))
        else:raise AssertionError(line)
    return result,{'statements':int(lines[0].split(':')[1]),'steps':steps,'reads':reads}


def program_witness(path):
    return decode_program(rrun('program',path).stdout.splitlines())


def witnesses(cases):
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);paths=[]
        for i,text in enumerate(cases):
            path=folder/f'{i}.sas';path.write_text(text);paths.append(str(path))
        listing=folder/'files.txt';listing.write_text(''.join(p+'\n' for p in paths))
        lines=rrun('batch',listing).stdout.splitlines()
    answers=[];current=[]
    for line in lines:
        if line.startswith('CASE:'):current=[]
        elif line.startswith('ANSWER:'):answers.append(decode_program(current) if line=='ANSWER:OK' else None)
        else:current.append(line)
    assert len(answers)==len(cases)
    return answers


def hand_cases(mode='csv'):
    if mode=='csv':
        return [(source([],names='a b'),table(('a','b'),[])),
            (source(['header'],names='a b',firstobs=2),table(('a','b'),[])),
            (source(['91,87,95','97,,92',',1,1'],names='a b c'),table(('a','b','c'),[[91.,87.,95.],[97.,92.,1.]])),
            (source([',,1,,,2,,ignored','3','4,99'],names='a b'),table(('a','b'),[[1.,2.],[3.,4.]])),
            (source([' ., -2.5 ','+1.25,5e-1'],names='a b'),table(('a','b'),[[None,-2.5],[1.25,.5]])),
            (source(['bad,header','1,2','3'],names='a b',firstobs=2),table(('a','b'),[[1.,2.]])),
            (source(['','   ', ',,,','1,2'],names='a b',firstobs=1),table(('a','b'),[[1.,2.]])),
            (source(['invalid'],names='a',firstobs=10001),table(('a',),[]))]
    return [(source(['1 2 3 4'],names='a8 x1-x3',comma=False),table(('a8','x1','x2','x3'),[[1.,2.,3.,4.]])),
            (source(['1 . 3'],names='v62-v64',comma=False),table(('v62','v63','v64'),[[1.,None,3.]])),
            (source(['1 2 3'],names='abc11-abc13',comma=False),table(('abc11','abc12','abc13'),[[1.,2.,3.]])),
            (source([' '.join('1' for _ in range(32))],names='x1-x32',comma=False),table(tuple('x'+str(i) for i in range(1,33)),[[1.]*32])),
            (source(['1 2'],names='X1 - X2',comma=False,body='if 0 then future=1;'),table(('x1','x2','future'),[[1.,2.,None]]))]


def generated(mode):
    rng=random.Random(5800 if mode=='csv' else 5900);cases=[]
    for _ in range(240 if mode=='csv' else 180):
        width=rng.randint(1,4);start=rng.randint(1,65-width);names=f'x{start}-x{start+width-1}'
        if mode=='csv' and rng.randrange(2):names=' '.join(f'x{i}' for i in range(start,start+width))
        records=[];rows=[]
        headers=rng.randrange(3) if mode=='csv' else 0
        records.extend('not,numeric,header' for _ in range(headers))
        for _ in range(rng.randint(0,5)):
            values=[None if rng.randrange(4)==0 else rng.randint(-50,50)/4 for _ in range(width)];rows.append(values)
            fields=['.' if v is None else str(v) for v in values]
            if mode=='csv':
                separator=','*rng.randint(1,3)
                if width>1 and rng.randrange(2):records.append(separator+fields.pop(0)+separator)
                records.append(separator.join(fields)+separator+'ignored')
            else:
                if width>1 and rng.randrange(2):records.append(fields.pop(0))
                records.append('  '.join(fields)+' ignored')
        if width>1:records.append('7')
        cases.append((source(records,names=names,comma=mode=='csv',firstobs=headers+1),
                      table(tuple('x'+str(i) for i in range(start,start+width)),rows)))
    return cases


def refusal_cases(mode='csv'):
    if mode=='csv':
        cases=[source([x],names='a') for x in ('bad','"1"','.A','NaN','0.1','2147483648','1e16','1\t2','é','1'*81)]
        cases += [source(['1, ,2'],names='a b'),source(['bad'],names='a b'),
                  source(['x'*81],names='a',firstobs=2)]
        base=source(['1,2'])
        for option in ("dlm=';'","dsd","dlm=',' dsd","dlm=',' firstobs=0","dlm=',' firstobs=10002",
                       "dlm=',' firstobs=02","dlm=',' firstobs=2 firstobs=3","dlm=',' missover"):
            cases.append(base.replace("dlm=',' firstobs=1",option))
        cases.append(base.replace('infile datalines',"infile 'outside.csv'"))
        return cases
    bad=['a-b','x2-x1','x0-x2','x1-x65','x01-x02','x1-y2','x1--x3','x:','x1-x2 x2',
         'x1-x33','_n_','x1-x2 _error_','x9999999999999999999999999999-x9999999999999999999999999999',
         'x1-x2 x01-x02','x1.5-x2','x1-x2,','K1-K2']
    cases=[source(['1 2'],names=n,comma=False) for n in bad]
    cases += [source([],comma=False,body=body) for body in ('array a{1} x;','do while(0);x1=1;end;',
              'trigger=1**1;','if 0 then bad=sqrt(x1);')]
    return cases


def cli_check(text,expected):
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);path=folder/'program.sas';path.write_text(text);out=folder/'out'
        expect=folder/'expected.json';expect.write_text(json.dumps(expected['datasets']))
        process=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--expect',str(expect),'--output',str(out)],cwd=ROOT,capture_output=True,text=True,timeout=45)
        receipt=json.loads((out/'receipt.json').read_text())
        assert process.returncode==0 and receipt['accepted'] and receipt['comparison']=='passed',(process.stdout,process.stderr)
        assert equal(json.loads((out/'result.json').read_text()),expected,ordered_maps=True)
        assert receipt['source_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
        return receipt


def wrong_expectations():
    expected=original_expected();cases=[]
    for damage in ('delimiter','firstobs','retained','scratch','missing','eof','schema','snapshot'):
        wrong=deepcopy(expected['datasets']);rows=wrong['capture']['rows']
        if damage=='delimiter':rows[0]['x2']=None
        elif damage=='firstobs':rows[0]['seq']=2.
        elif damage=='retained':rows[4]['total']=4.
        elif damage=='scratch':rows[2]['before']=1.
        elif damage=='missing':rows[2]['x1']=0.
        elif damage=='eof':rows.append({'total':12.,'x1':7.,'x2':None,'before':None,'scratch':7.,'seq':4.})
        elif damage=='schema':wrong['capture']['schema']=dict(reversed(list(wrong['capture']['schema'].items())))
        else:rows.pop(1)
        cases.append((damage,wrong))
    return cases


def cli_wrong_controls():
    expected=original_expected()
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);path=folder/'source.sas';path.write_text(ORIGINAL.read_text())
        for i,(damage,wrong) in enumerate(wrong_expectations()):
            expect=folder/f'bad{i}.json';expect.write_text(json.dumps(wrong));out=folder/f'out{i}'
            process=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--expect',str(expect),'--output',str(out)],cwd=ROOT,capture_output=True,text=True,timeout=45)
            receipt=json.loads((out/'receipt.json').read_text())
            assert process.returncode==1 and not receipt['accepted'] and receipt['comparison']=='failed',damage
            assert not (out/'result.json').exists() and (out/'observed.json').is_file()
            assert equal(json.loads((out/'observed.json').read_text()),expected,ordered_maps=True)
    wrong=deepcopy(expected);wrong['log'].reverse();assert not equal(wrong,expected,ordered_maps=True)
    return 9


def range_comparator_controls():
    text=source(['1 2 3'],names='x9-x11',comma=False)
    expected=table(('x9','x10','x11'),[[1.,2.,3.]])
    damages=[]
    for damage in ('lexical_order','endpoint','reverse_values','padding'):
        wrong=deepcopy(expected['datasets']);target=wrong['d']
        if damage=='lexical_order':target['schema']={n:'number' for n in ('x10','x11','x9')}
        elif damage=='endpoint':
            del target['schema']['x11'];del target['rows'][0]['x11']
        elif damage=='reverse_values':target['rows'][0].update(x9=3.,x11=1.)
        else:
            target['schema']={'x09':'number','x10':'number','x11':'number'}
            target['rows'][0]['x09']=target['rows'][0].pop('x9')
        damages.append((damage,wrong))
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);path=folder/'ranges.sas';path.write_text(text)
        for i,(damage,wrong) in enumerate(damages):
            expect=folder/f'wrong{i}.json';expect.write_text(json.dumps(wrong));out=folder/f'out{i}'
            process=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--expect',str(expect),'--output',str(out)],cwd=ROOT,capture_output=True,text=True,timeout=45)
            receipt=json.loads((out/'receipt.json').read_text())
            assert process.returncode==1 and not receipt['accepted'] and receipt['comparison']=='failed',damage
            assert not (out/'result.json').exists()
            assert equal(json.loads((out/'observed.json').read_text()),expected,ordered_maps=True)
    return len(damages)


def main(mode='csv'):
    pins=hand_cases(mode);cases=pins+generated(mode);independent=witnesses([s for s,_ in cases])
    for i,((text,expected),answer) in enumerate(zip(cases,independent)):
        assert answer is not None,(mode,i,text)
        observed=execute(text,emitted=i<len(pins) or i%40==0)
        assert equal(observed,expected,ordered_maps=True),(mode,i,observed,expected)
        assert equal(answer[0],expected,ordered_maps=True),(mode,i,answer,expected)
    refused=refusal_cases(mode)
    for text,answer in zip(refused,witnesses(refused)):
        try:execute(text)
        except (ValueError,AssertionError,RuntimeError):pass
        else:raise AssertionError(('missing refusal',text))
        assert answer is None,('R missing refusal',text)
    expected=original_expected();observed=execute(ORIGINAL.read_text(),emitted=True);r,accounting=program_witness(ORIGINAL)
    assert equal(observed,expected,ordered_maps=True) and equal(r,expected,ordered_maps=True)
    assert accounting=={'statements':20,'steps':['capture','ranges'],'reads':[3,2]},accounting
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==SOURCE_PIN
    assert hashlib.sha256(json.dumps(expected,separators=(',',':')).encode()).hexdigest()==RESULT_PIN
    assert hashlib.sha256(''.join(line+'\n' for line in expected['log']).encode()).hexdigest()==STDOUT_PIN
    cli_check(ORIGINAL.read_text(),expected)
    controls=cli_wrong_controls() if mode=='csv' else range_comparator_controls()
    print(f'VERIFIED: inline-{mode} {len(pins)} hand pins,{len(cases)-len(pins)} generated full-source/runtime/R cases,'
          f'{len(refused)} shared refusals,{controls} comparator controls; original20-statement/5-read/7-snapshot source,'
          'exact values/schema/order/logical text,emitted/actual CLI;2opaque data events;0 prior source promotions;no live SAS or general CSV')


if __name__=='__main__':main()
