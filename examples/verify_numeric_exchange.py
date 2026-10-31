#!/usr/bin/env python3
"""DS-062/063 independent complete-source range and exact export evidence."""
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
from saschi.compare import equal,table_equal
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.emit_py import translate
from saschi.numeric_exchange import execute_step,export_manifest

ORIGINAL=HERE/'numeric_exchange_capture.sas'
CORPUS=Path(os.environ.get('SASCHI_ROKU_CORPUS',ROOT.parent/'saschi-roku/corpus'))/'csv_data_manipulation.sas'
CORPUS_EXPORT='C1,C2,C3,C4,C5,Sum\n1,5,9,13,17,45\n2,6,10,14,18,50\n3,7,11,15,19,55\n4,8,12,16,20,60\n'
CORPUS_EXPORT_PIN='26ab6a12a8aeaa2f4e5500c2c40f3e0a81334f530a86f5dcc1af852c036f2fcb'
SOURCE_PIN='1b517518bb621de7f727029d7a5bb42694a25a65f6d5ada61f30efe299f295b9'
RESULT_PIN='f898a996f0894f8adc814477b2dd6a31690205458825a012d9d5d797489e1b23'
STDOUT_PIN='3161d14db751fa12ccf1a881326dcbcdb2f3d11089a1027fbb59f49e224857f1'
CORPUS_SOURCE_PIN='f9bf4fc393112052cb76945f6c878e8029160fce27ba223a2dc46d7cfba8fba8'


def ordered_digest(value):return hashlib.sha256(json.dumps(value,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def source(records=None,*,width=3,filename=None,header=False,firstobs=1,body=None,name='d',prefix='',terms=None):
    terms=terms or f'x1-x{width}'
    infile=("infile datalines dlm=',' firstobs="+str(firstobs)+';') if records is not None else ''
    file=(f'file "{filename}" dlm=\',\';') if filename is not None else ''
    read=('input '+terms+';') if records is not None else ''
    body=body if body is not None else 'total=sum(of '+terms+');put '+terms+' total;'
    heading='if _n_=1 then put "HEADER";' if header else ''
    raw=('datalines;\n'+''.join(r+'\n' for r in records)+';\n') if records is not None else ''
    return 'data '+name+';'+prefix+infile+file+read+heading+body+raw+'run;'


def corpus_expected():return {'datasets':{},'log':[],'exports':{'output.csv':CORPUS_EXPORT}}


def original_expected():
    names=('c1','c2','c3','total','retained_seen');values=[[1,2,3,6,6],[99,2,3,6,6],[None,4,8,12,18],[99,4,8,12,18],[None,None,None,None,18],[99,None,None,None,18]]
    return {'datasets':{'samples':{'schema':dict.fromkeys(names,'number'),'rows':[dict(zip(names,[None if v is None else float(v) for v in row])) for row in values]},
                        'lists':{'schema':dict.fromkeys(('x1','x2','x3','total'),'number'),'rows':[{'x1':7.,'x2':None,'x3':9.,'total':16.}]}},
            'log':['7 . 9 16 ','after'],'exports':{'measurements.csv':'C1,C2,C3,Total\n1,2,3,6\n.,4,8,12\n.,.,.,.\n'}}


def execute(text,emitted=False):
    parsed=compile_plan(text);assert not parsed.blocked,[vars(t) for t in parsed.tickets]
    plan=parsed.to_dict();saved=deepcopy(plan);result=run_plan(plan);assert plan==saved
    if emitted:
        scope={};stdout=io.StringIO()
        with contextlib.redirect_stdout(stdout):exec(translate(text).code,scope)
        assert equal(scope['result'],result,ordered_maps=True)
        assert stdout.getvalue()==''.join(line+'\n' for line in result['log'])
    return result


def trace_accounting(text):
    accounts=[]
    for step in compile_plan(text).to_dict()['steps']:
        if step['kind']!='exchange_data':continue
        trace=[];execute_step(step,trace=trace)
        accounts.append({'name':step['name'],'reads':sum(e['kind']=='exchange_input' and e['complete'] for e in trace),
                         'attempts':sum(e['kind']=='exchange_input' for e in trace),
                         'opens':sum(e['kind']=='file_select' for e in trace),
                         'writes':sum(e['kind'] in ('put_named_list','put_literal') for e in trace) if any(e['kind']=='file_select' for e in trace) else 0,
                         'events':len(trace)})
    return accounts


def assert_original(text,expected,answer,*,corpus=False):
    actual=execute(text,emitted=True)
    assert answer is not None and equal(actual,expected,ordered_maps=True) and equal(answer[0],expected,ordered_maps=True)
    assert hashlib.sha256(text.encode()).hexdigest()==(CORPUS_SOURCE_PIN if corpus else SOURCE_PIN)
    if corpus:
        hand=[{'name':'_null_','reads':4,'attempts':5,'opens':5,'writes':5,'events':23}]
        assert answer[1]=={'statements':9,'steps':hand}
        assert trace_accounting(text)==hand
        assert hashlib.sha256(actual['exports']['output.csv'].encode()).hexdigest()==CORPUS_EXPORT_PIN
    else:
        hand=[{'name':'samples','reads':3,'attempts':4,'opens':4,'writes':4,'events':41},
              {'name':'lists','reads':0,'attempts':0,'opens':0,'writes':0,'events':5},
              {'name':'_null_','reads':0,'attempts':0,'opens':0,'writes':0,'events':1}]
        assert answer[1]=={'statements':25,'steps':hand}
        assert trace_accounting(text)==hand[:2]
        assert ordered_digest(actual)==RESULT_PIN and ordered_digest(answer[0])==RESULT_PIN
        assert hashlib.sha256(''.join(line+'\n' for line in actual['log']).encode()).hexdigest()==STDOUT_PIN
    return actual


def decode_wire(lines):
    assert lines and lines[0].startswith('STATEMENTS:')
    result={'datasets':{},'log':[]};account={'statements':int(lines[0].split(':')[1]),'steps':[]};table=None;names=[];step=None
    for line in lines[1:]:
        kind,value=line.split(':',1)
        if kind=='STEP':
            step={'name':value};account['steps'].append(step);table={'schema':{},'rows':[]}
            if value!='_null_':result['datasets'][value]=table
        elif kind=='SCHEMA':names=value.split(',') if value else [];table['schema']=dict.fromkeys(names,'number')
        elif kind=='ROW':table['rows'].append(dict(zip(names,([] if not names else [None if v=='.' else float(v) for v in value.split(',')]))))
        elif kind=='LOG':result['log'].append(bytes.fromhex(value).decode('ascii'))
        elif kind=='EXPORT':
            name,text=value.split(':',1);result.setdefault('exports',{})[bytes.fromhex(name).decode('ascii')]=bytes.fromhex(text).decode('ascii')
        elif kind in ('READS','ATTEMPTS','OPENS','WRITES','EVENTS'):step[kind.lower()]=int(value)
        else:raise AssertionError(line)
    return result,account


def witnesses(cases,*,r_file='numeric_exchange.R'):
    with tempfile.TemporaryDirectory(prefix='saschi-exchange-R-') as td:
        folder=Path(td);paths=[]
        for index,text in enumerate(cases):
            path=folder/f'{index}.sas';path.write_text(text);paths.append(path)
        listing=folder/'files.txt';listing.write_text(''.join(str(p)+'\n' for p in paths))
        r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        run=subprocess.run([r,str(HERE/r_file),'batch',str(listing)],cwd=ROOT,capture_output=True,text=True,timeout=120)
        assert run.returncode==0,run.stderr
    answers=[];block=[]
    for line in run.stdout.splitlines():
        if line.startswith('CASE:'):block=[]
        elif line.startswith('ANSWER:'):answers.append(decode_wire(block) if line=='ANSWER:OK' else None)
        else:block.append(line)
    assert len(answers)==len(cases),(run.stdout,run.stderr)
    return answers


def hand_cases(mode):
    cases=[]
    if mode=='ranges':
        cases=[source(None,body='x1=1;x2=.;x3=3;total=sum(of x1-x3);put x1-x3 total;'),
               source(None,body='x1=.;x2=.;total=sum(of x1-x2);put x1-x2 total;'),
               source(['1,2,3','4,5,6'],body='if _n_=1 then scratch=.;before=scratch;scratch=x1;total=sum(of x1-x3);put x1-x3 total;output;x1=99;output;'),
               source(None,body='x1=0.5;x2=0.5;total=sum(of x1-x2);put total;'),
               source(None,body='x62=3;x63=4;x64=5;total=sum(of x62-x64);put x62-x64 total;'),
               source(None,body='input=1;file=2;infile=3;keep=4;drop=5;x1=6;x2=7;total=sum(of x1-x2);put x1-x2 total;')]
    else:
        cases=[source(['1,2,3'],filename='one.csv',header=True,name='_null_'),
               source([],filename='empty.csv',header=True,name='_null_'),
               source(['HEADER'],filename='skipped.csv',header=True,firstobs=2,name='_null_'),
               source(['1,2'],filename='partial.csv',header=True,name='_null_'),
               source(['1,2,3','4,5'],filename='partial.csv',header=True,name='_null_'),
               source(['1,,2','3,BAD','.,.,.'],filename='Flow.CSV',header=True,name='_null_'),
               source(None,filename='literal.csv',body='put "A,B";put "C,D";',name='_null_'),
               source(None,filename='header-only.csv',body='put "A,B";',name='d'),
               source(['1,2,3','4,5,6'],filename='retained.csv',prefix='retain x1 9;',body='if _n_=1 then scratch=.;before=scratch;scratch=x1;total=sum(of x1-x3);put x1-x3 total;',name='d')]
    return cases


def generated_cases(mode,count=160):
    rng=random.Random(62063 if mode=='ranges' else 63062);cases=[]
    for index in range(count):
        width=rng.randint(1,6);rows=[[None if rng.randrange(5)==0 else rng.randint(-99,99) for _ in range(width)] for _ in range(rng.randint(0,6))]
        records=[','.join('.' if v is None else str(v) for v in row)+(',BAD' if index%7==0 else '') for row in rows]
        firstobs=1
        if index%4==0:records.insert(0,'SKIPPED HEADER');firstobs=2
        text=source(records,width=width,filename=(f'case{index}.csv' if mode=='export' else None),header=mode=='export' and index%3==0,firstobs=firstobs,
                    body='total=sum(of x1-x'+str(width)+');'+('if _n_ ne 2 then ' if index%5==0 else '')+'put x1-x'+str(width)+' total;')
        cases.append(text)
    return cases


def refusal_cases(mode):
    numeric=[source(None,body='x1=1;x2=2;s=sum(of x2-x1);'),source(None,body='x1=1;x2=2;s=sum(of x01-x02);'),
             source(None,body='x1=1;x2=2;s=sum(of x1-y2);'),source(None,body='x1=1;x2=2;s=sum(of x1-x2 x2);'),
             source(None,body='x1=1;s=sum(of x1-x2);'),source(None,body='x1=1;x2=2;if 0 then z=1/3;s=sum(of x1-x2);'),
             source(None,body='x1=1;x2=2;if 0 then z=2147483647+1;s=sum(of x1-x2);'),
             source(None,body='x1=2147483647;x2=1;x3=-1;s=sum(of x1-x3);'),
             source(None,body='x1=1;x2=2;s=sum(of x1-x2);put x1-x2 8.;')]
    numeric += [source(None,body='x1=1;x2=2;'+body) for body in
                ('s=sum(of x1-x2)+1;','s=(sum(of x1-x2));','if sum(of x1-x2) then put x1-x2;','s+sum(of x1-x2);')]
    if mode=='ranges':return numeric
    export=[source(['1,2,3'],filename=name,name='_null_') for name in ('../out.csv','/tmp/out.csv','a/b.csv','CON.csv','result.json','exports','a.csv:stream','a space.csv')]
    export += [source(['1,2,3'],filename='out.csv',name='_null_').replace("dlm=',';input", "dlm=',' dsd;input"),
               source(['1,2,3'],filename='out.csv',name='_null_',body='if 0 then put x1-x3 8.;'),
               source(['1,2,3'],filename='out.csv',name='_null_',body='if 0 then x1=sqrt(1);put x1-x3;'),
               source(['1,2,3'],filename='out.csv',name='_null_',body='x1=0.5;put x1-x3;'),
               source(['1,2,BAD'],filename='out.csv',name='_null_'),
               source(['1,2,3'],filename='out.csv',name='_null_')+source(['4,5,6'],filename='two.csv',name='_null_')]
    export += [ORIGINAL.read_text()+'proc print;run;',
               CORPUS.read_text().rsplit('run;',1)[0],
               ORIGINAL.read_text().replace('run;','',1),
               CORPUS.read_text()+'orphan=1;']
    return numeric+export


def cli_check(text,expected,*,wrong=None):
    with tempfile.TemporaryDirectory(prefix='saschi-exchange-cli-') as td:
        folder=Path(td);source_path=folder/'job.sas';source_path.write_text(text);out=folder/'job';args=[]
        exports=expected.get('exports');datasets=expected['datasets']
        if exports is not None:
            comparison=exports if wrong is None else wrong;path=folder/'expected-exports.json';path.write_text(json.dumps(comparison));args+=['--expect-exports',str(path)]
        elif datasets:
            comparison=datasets if wrong is None else wrong;path=folder/'expected.json';path.write_text(json.dumps(comparison));args+=['--expect',str(path)]
        command=[sys.executable,'-m','saschi','run',str(source_path),*args,'--output',str(out)]
        process=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(ROOT),'PYTHONDONTWRITEBYTECODE':'1'})
        receipt=json.loads((out/'receipt.json').read_text())
        assert process.returncode==(0 if wrong is None else 1),(process.stderr,receipt)
        assert receipt['accepted'] is (wrong is None)
        if wrong is not None:
            assert not (out/'exports').exists() and not (out/'result.json').exists() and (out/'observed.json').exists()
            assert receipt['export_comparison' if exports is not None else 'comparison']=='failed'
        else:
            result=json.loads((out/'result.json').read_text());assert equal(result,expected,ordered_maps=True)
            if exports is not None:
                assert receipt['export_comparison']=='passed' and receipt['exports']==export_manifest(exports)
                assert set(p.name for p in (out/'exports').iterdir())==set(exports)
                for name,text in exports.items():assert (out/'exports'/name).read_bytes()==text.encode('ascii')
        return receipt


def wrong_controls(mode):
    if mode=='export':
        text=CORPUS.read_text();expected=corpus_expected();good=expected['exports']['output.csv']
        wrongs=[{'wrong.csv':good},{'output.csv':good[:-1]},{'output.csv':good+'\n'},
                {'output.csv':good.replace('45','46')},{'output.csv':'\n'.join(good.splitlines()[::-1])+'\n'},
                {'output.csv':'\n'.join(good.splitlines()[:-1])+'\n'}]
        for wrong in wrongs:cli_check(text,expected,wrong=wrong)
        return len(wrongs)
    text=hand_cases('ranges')[0];expected=execute(text);base=expected['datasets'];wrongs=[]
    wrong=deepcopy(base);wrong['d']['rows'][0]['total']=0;wrongs.append(wrong)
    wrong=deepcopy(base);wrong['d']['schema']=dict(reversed(list(wrong['d']['schema'].items())));wrongs.append(wrong)
    wrong=deepcopy(base);wrong['d']['rows']*=2;wrongs.append(wrong)
    wrong=deepcopy(base);wrong['d']['rows'][0]['x2']=0;wrongs.append(wrong)
    for wrong in wrongs:cli_check(text,expected,wrong=wrong)
    return len(wrongs)


def run(mode):
    hands=hand_cases(mode);generated=generated_cases(mode);refusals=refusal_cases(mode)
    cases=hands+generated;answers=witnesses(cases+refusals,r_file='numeric_ranges.R' if mode=='ranges' else 'numeric_exchange.R')
    for text,answer in zip(cases,answers):
        assert answer is not None,('R refused accepted case',text)
        actual=execute(text,emitted=True);assert equal(actual,answer[0],ordered_maps=True),(text,actual,answer)
    for text,answer in zip(refusals,answers[len(cases):]):
        try:execute(text)
        except (ValueError,AssertionError,RuntimeError):pass
        else:raise AssertionError(('Python accepted refusal',text))
        assert answer is None,('R accepted refusal',text,answer)
    cli_check(hands[0],execute(hands[0]));controls=wrong_controls(mode)
    if mode=='export':
        for path,expected in ((ORIGINAL,original_expected()),(CORPUS,corpus_expected())):
            text=path.read_text();answer,=witnesses([text]);assert answer is not None
            assert_original(text,expected,answer,corpus=path==CORPUS)
            cli_check(text,expected)
        assert hashlib.sha256(CORPUS_EXPORT.encode()).hexdigest()==CORPUS_EXPORT_PIN
        print('VERIFIED corpus: csv_data_manipulation.sas; complete unchanged source,independent R,pure emitted buffers,exact ASCII-LF export and actual CLI')
    print(f'VERIFIED: numeric-exchange-{mode} {len(hands)} hand cases,{len(generated)} generated full-source/runtime/R cases,{len(refusals)} shared refusals,{controls} actual CLI comparator controls; no live SAS')


if __name__=='__main__':run('export')
