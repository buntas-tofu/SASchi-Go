#!/usr/bin/env python3
"""Bounded procedure source, exact statistics and logical-report evidence."""
from copy import deepcopy
import contextlib
import csv
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
from examples.verify_scalar_jump import catalog_files
from saschi.compare import equal
from saschi.emit_py import translate
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.procedures import execute_means,execute_print
from saschi.values import normalize_catalog

ORIGINAL=HERE/'procedures_capture.sas'
PAIRS=[(2,10),(1,1),(4,None),(None,2),(3,7),(1,3),(2,None),(3,7),(4,None),(None,4),(5,9),(1,5)]
ORDERED_IDS=[4,10,2,6,12,1,7,5,8,3,9,11]
SUMMARY_NAMES=['g','_type_','_freq_','nobs','nmissing','avg','variance']
SUMMARY_ROWS=[(None,0,2,2,0,3,2),(1,0,3,3,0,3,4),(2,0,2,1,1,10,None),
              (3,0,2,2,0,7,0),(4,0,2,0,2,None,None),(5,0,1,1,0,9,None)]
REPORT='g _type_ _freq_ nobs nmissing avg variance\n. 0 2 2 0 3 2\n1 0 3 3 0 3 4\n2 0 2 1 1 10 .\n3 0 2 2 0 7 0\n4 0 2 0 2 . .\n5 0 1 1 0 9 .\n'
SOURCE_PIN='218299d7dfc832e90fe779dbb0fc33a9a86b06d7418ba5272388fc4618be11f4'
RESULT_PIN='22fef21864280b5f7b8b7af0478694786acc2731f3f100b9d401a257246e41a6'
REPORT_PIN='aa480918e13b31d6fd8643b167fc7e9c9c29ed4779b71eb42d2ac9a9370ca323'
TRACE_PIN='92c702d6528f46832a23bbd850fc81b0a3b3c4ac861be4968a9b934641b89e04'


def assert_tree(actual,expected):
    assert equal(actual,expected,ordered_maps=True),(actual,expected)


def ordered_digest(value):
    return hashlib.sha256(json.dumps(value,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def incoming(rows=True):
    return {'raw':{'encoding':'latin-1','label':'supplied sample',
        'schema':{'id':'number','g':{'type':'number','length':8,'label':'Group','format':''},
                  'x':{'type':'number','length':8,'label':'Measurement','format':''}},
        'rows':[{'id':float(i),'g':None if g is None else float(g),'x':None if x is None else float(x)} for i,(g,x) in enumerate(PAIRS,1)] if rows else []}}


def original_expected():
    catalog=incoming();ordered=deepcopy(catalog['raw']);ordered['rows']=[deepcopy(catalog['raw']['rows'][i-1]) for i in ORDERED_IDS]
    schema={'g':deepcopy(catalog['raw']['schema']['g'])}
    schema.update((name,{'type':'number','length':8}) for name in SUMMARY_NAMES[1:])
    summary={'schema':schema,'rows':[dict(zip(SUMMARY_NAMES,[None if x is None else float(x) for x in row])) for row in SUMMARY_ROWS]}
    return {'datasets':{**catalog,'ordered':ordered,'summary':summary},'log':[],'reports':{'print.txt':REPORT}}


def original_trace():
    trace=['sort|input|raw|12','sort|output|ordered|12','means|input|ordered|12']
    trace.extend(['group|.|2|2|0','group|1|3|3|0','group|2|2|1|1','group|3|2|2|0','group|4|2|0|2','group|5|1|1|0'])
    trace.extend(['means|output|summary|6','print|input|summary|6','print|header|'+REPORT.splitlines()[0].encode().hex()])
    trace.extend('print|row|'+line.encode().hex() for line in REPORT.splitlines()[1:])
    trace.append('print|output|print.txt|128');return trace


def means_source(input='raw',output='summary',*,sort=False,printed=False,stats=None):
    statements=(f'proc sort data={input} out=ordered;by g;run;' if sort else '')
    source='ordered' if sort else input
    stats=stats or 'n=nobs nmiss=nmissing mean=avg var=variance'
    statements+=f'proc means data={source} noprint vardef=df;by g;var x;output out={output} {stats} / noinherit;run;'
    if printed:statements+=f'proc print data={output} noobs;var g _type_ _freq_ nobs nmissing avg variance;run;'
    return statements


def print_source(names='x',input='raw'):
    return f'proc print data={input} noobs;var {names};run;'


def plain(rows,schema=None):
    return {'raw':{'schema':schema or {'g':'number','x':'number'},'rows':[{'g':g,'x':x} for g,x in rows]}}


def decode(lines):
    result={'datasets':{},'log':[]};accounting={'statements':None,'steps':[]};trace=[];table=None;table_keys={};column_keys={};row_keys=None
    for line in lines:
        tag,value=line.split(':',1)
        if tag=='STATEMENTS':accounting['statements']=int(value)
        elif tag=='TABLE':table={'schema':{},'rows':[]};result['datasets'][value]=table;name=value;column_keys[name]={};row_keys=None
        elif tag=='META':
            encoding,label=value.split('|');schema,rows=table['schema'],table['rows'];table.clear()
            if encoding!='-':table['encoding']=encoding
            if label!='-':table['label']=bytes.fromhex(label).decode()
            table.update(schema=schema,rows=rows)
        elif tag=='TABLEKEYS':table_keys[name]=value.split('|')
        elif tag=='COLUMN':
            key,kind,length,label,fmt=value.split('|')
            if kind=='number':spec='number'
            else:
                spec={'type':'number' if kind=='typed-number' else kind}
                if length!='-':spec['length']=int(length)
                if label!='-':spec['label']=bytes.fromhex(label).decode()
                if fmt!='-':spec['format']=bytes.fromhex(fmt).decode()
            table['schema'][key]=spec
        elif tag=='COLUMNKEYS':
            key,*keys=value.split('|');column_keys[name][key]=keys
        elif tag=='ROWKEYS':row_keys=value.split('|') if value else []
        elif tag=='ROW':
            cells=value.split(',') if value else [];values=[None if c=='M' else bytes.fromhex(c[1:]).decode() if c.startswith('C') else {'missing':c[1:]} if c.startswith('T') else float(c[1:]) for c in cells]
            table['rows'].append(dict(zip(row_keys if row_keys is not None else table['schema'],values)))
        elif tag=='REPORT':
            key,text=value.split('|');result.setdefault('reports',{})[key]=bytes.fromhex(text).decode()
        elif tag=='PROCACCOUNT':
            kind,read,written,groups,records=value.split('|');accounting['steps'].append({'kind':kind,'input_rows':int(read),'output_rows':int(written),'groups':int(groups),'records':int(records)})
        elif tag=='TRACE':trace.append(bytes.fromhex(value).decode())
        else:raise AssertionError(line)
    for name,table in list(result['datasets'].items()):
        for key,keys in column_keys[name].items():table['schema'][key]={field:table['schema'][key][field] for field in keys}
        if name in table_keys:result['datasets'][name]={key:table[key] for key in table_keys[name]}
    return {'result':result,'accounting':accounting,'trace':trace}


def batch_witness(cases):
    with tempfile.TemporaryDirectory() as temp:
        folder=Path(temp)
        with (folder/'cases.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['source','catalog'])
            for i,case in enumerate(cases):
                source,catalog=(case['source'],case.get('catalog',{})) if isinstance(case,dict) else case
                (folder/f'{i}.sas').write_text(source);catalog_files(folder/f'cat{i}',catalog);writer.writerow([f'{i}.sas',f'cat{i}'])
        r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        process=subprocess.run([r,str(HERE/'procedures.R'),'batch',str(folder)],capture_output=True,text=True,check=True,timeout=180)
    results=[];current=[]
    for line in process.stdout.splitlines():
        if line.startswith('CASE:'):current=[]
        elif line.startswith('REASON:'):pass
        elif line.startswith('ANSWER:'):results.append(decode(current) if line=='ANSWER:OK' else None)
        else:current.append(line)
    assert len(results)==len(cases),(process.stdout,process.stderr)
    return results


def program_witness(path=ORIGINAL,catalog=None):
    return batch_witness([(path.read_text(),incoming() if catalog is None else catalog)])[0]


def execute(source,catalog=None,emitted=False):
    catalog={} if catalog is None else deepcopy(catalog);before=deepcopy(catalog);p=compile_plan(source);assert not p.blocked,p.tickets
    plan=p.to_dict();saved=deepcopy(plan);result=run_plan(plan,catalog);assert_tree(catalog,before);assert_tree(plan,saved)
    tables=normalize_catalog(catalog);reports={};trace=[]
    for step in plan['steps']:
        if step['kind']=='sort':
            trace.append('sort|input|'+step['inputs'][0]+'|'+str(len(tables[step['inputs'][0]]['rows'])))
            tables=run_plan({'version':2,'steps':[step],'tickets':[]},tables)['datasets']
            trace.append('sort|output|'+step['name']+'|'+str(len(tables[step['name']]['rows'])))
        elif step['kind']=='proc_means':tables[step['name']]=execute_means(step,tables,plan['version'],trace=trace)
        elif step['kind']=='proc_print':reports.update(execute_print(step,tables,plan['version'],trace=trace))
        else:raise ValueError('procedure evidence trace uses complete SORT/MEANS/PRINT sources')
    traced={'datasets':tables,'log':[]}
    if reports:traced['reports']=reports
    assert_tree(result,traced)
    if emitted:
        namespace={'inputs':deepcopy(catalog)};stream=io.StringIO()
        with contextlib.redirect_stdout(stream):exec(translate(source).code,namespace)
        assert_tree(namespace['result'],result);assert stream.getvalue()==''
    return {'result':result,'trace':trace}


def hand_cases(mode):
    if mode=='means':
        return [('original',ORIGINAL.read_text(),incoming()),
          ('empty',means_source(sort=True,printed=True),incoming(False)),
          ('missing-BY',means_source(),plain([(None,2),(None,4),(1,None)])),
          ('all-missing',means_source(),plain([(1,None),(1,None)])),
          ('singleton',means_source(),plain([(1,9)])),
          ('constant',means_source(),plain([(1,7),(1,7)])),
          ('negative',means_source(printed=True),plain([(-2,-3),(-2,1),(0,-1)])),
          ('DF-and-missing',means_source(),plain([(1,1),(1,None),(1,3),(1,5)])),
          ('alias-order',means_source(stats='var=variance mean=avg nmiss=nmissing n=nobs'),plain([(1,1),(1,3)])),
          ('1000-extremes',means_source(),plain([(0,-1000 if i%2 else 1000) for i in range(1000)]))]
    names=['c'+str(i).zfill(31) for i in range(32)]
    maximum={'raw':{'schema':dict.fromkeys(names,'number'),'rows':[dict.fromkeys(names,-0.123456789) for _ in range(1000)]}}
    generic={'raw':{'schema':{'x':'number'},'rows':[{'x':1},{'x':None}]},'other':{'encoding':'latin-1','label':'untouched','schema':{'tag':'number','fraction':'number','c':{'type':'character','length':1}},'rows':[{'tag':{'missing':'A'},'fraction':0.1,'c':'é'}]}}
    return [('original',ORIGINAL.read_text(),incoming()),
      ('header-only',print_source(),{'raw':{'schema':{'x':'number'},'rows':[]}}),
      ('missing-zero',print_source(),{'raw':{'schema':{'x':'number'},'rows':[{'x':None},{'x':-0.0},{'x':2}]}}),
      ('fraction',print_source(),{'raw':{'schema':{'x':'number'},'rows':[{'x':0.25},{'x':-0.125},{'x':0.0001}]}}),
      ('selected-order',print_source('x g'),plain([(1,2),(3,4)])),
      ('empty-metadata',print_source(),{'raw':{'schema':{'x':{'type':'number','label':'','format':''}},'rows':[{'x':2}]}}),
      ('unrelated-generic-preservation',print_source(),generic),
      ('exact-maximum-report',print_source(' '.join(names)),maximum)]


def generated_cases(mode,count=160):
    rng=random.Random(7841 if mode=='means' else 7842);out=[]
    for i in range(count):
        pairs=[(rng.choice([None,-2,-1,0,1,2]),rng.choice([None,-9,-3,0,1,2,4,9])) for _ in range(rng.randrange(0,33))]
        catalog=plain(pairs)
        source=means_source(sort=True,printed=i%3==0) if mode=='means' else (means_source(sort=True,printed=True) if i%2 else print_source('x g'))
        out.append((f'generated-{i}',source,catalog))
    return out


def refusal_cases(mode):
    valid=means_source() if mode=='means' else print_source('g x');catalog=plain([(0,1),(0,3)]);out=[]
    if mode=='means':
        replacements=[('noprint ','','missing-NOPRINT'),('vardef=df','vardef=n','other-VARDEF'),('by g;','','missing-BY'),('var x;','','missing-VAR'),('/ noinherit','','inheritance'),('n=nobs','n=g','BY-alias'),('n=nobs','n=_type_','TYPE-alias'),('n=nobs','n=_freq_','FREQ-alias'),('nmiss=nmissing','nmiss=nobs','duplicate-alias'),('n=nobs','sum=nobs','unsupported-stat'),('by g','by g x','multiple-BY'),('var x','var x g','multiple-VAR'),('data=raw','data=lib.raw','qualified-input'),('out=summary','out=raw','collision'),('var x','var g','BY-analysis-collision'),('output out=summary','output out=summary(drop=_type_)','output-option'),('proc means','proc summary','other-procedure')]
        for old,new,name in replacements:out.append((name,valid.replace(old,new),deepcopy(catalog)))
        for value,name in [(1.5,'fraction'),(1001,'wide'),({'missing':'A'},'tag'),(True,'boolean'),(float('inf'),'nonfinite')]:
            c=deepcopy(catalog);c['raw']['rows'][-1]['x']=value;out.append((name,valid,c))
        out.append(('unsorted',valid,plain([(1,1),(0,2)])))
        c=deepcopy(catalog);c['raw']['rows'][-1]['g']={'missing':'A'};out.append(('tagged-BY',valid,c))
    else:
        for old,new,name in [(' noobs','','OBS-default'),('var g x','var g g','duplicate-selected'),('var g x','var absent','unknown-selected'),('var g x','var x1-x2','name-range'),('data=raw','data=raw(obs=1)','input-option'),('noobs','noobs label','LABEL-option'),('var g x','var K','Unicode-fold'),('run;','run;orphan=1;','trailing-source')]:out.append((name,valid.replace(old,new),deepcopy(catalog)))
        for value,name in [(True,'boolean'),({'missing':'A'},'tag'),(float('inf'),'nonfinite'),(2147483648,'numeric-bound'),(0.00001,'fractional-text-bound'),(0.12345678905,'decimal-midpoint')]:
            c=deepcopy(catalog);c['raw']['rows'][-1]['x']=value;out.append((name,valid,c))
        names=[f'c{i}' for i in range(33)];out.append(('33columns',print_source(' '.join(names)),{'raw':{'schema':dict.fromkeys(names,'number'),'rows':[]}}))
        out.append(('two-PRINT',valid+valid,deepcopy(catalog)))
    for empty in (False,True):
        for spec,name in [({'type':'character','length':8},'character'),({'type':'number','length':4},'width4'),({'type':'number','format':'8.'},'formatted')]:
            c=deepcopy(catalog);c['raw']['schema']['x']=spec
            if empty:c['raw']['rows']=[]
            elif name=='character':
                for row in c['raw']['rows']:row['x']='text'
            out.append((name+('-empty' if empty else ''),valid,c))
    c=deepcopy(catalog);c['raw']['rows']*=501;out.append(('1001rows',valid,c))
    for index in range(valid.count(';')):
        locations=[i for i,c in enumerate(valid) if c==';'];position=locations[index];out.append((f'missing-terminator-{index}',valid[:position]+valid[position+1:],deepcopy(catalog)))
    out.append(('unknown-on-empty',valid.replace('var x','var absent') if mode=='means' else valid.replace('var g x','var absent'),{'raw':{'schema':catalog['raw']['schema'],'rows':[]}}))
    return out


def cli_check(source,catalog,expected,*,wrong_dataset=None,wrong_reports=None,code=0):
    with tempfile.TemporaryDirectory() as temp:
        folder=Path(temp);path=folder/'source.sas';path.write_text(source);inputs=folder/'inputs.json';inputs.write_text(json.dumps(catalog));out=folder/'job'
        command=[sys.executable,'-B','-m','saschi','run',str(path),'--inputs',str(inputs),'--output',str(out)]
        if expected['datasets']:
            target=wrong_dataset if wrong_dataset is not None else {name:table for name,table in expected['datasets'].items() if name=='summary' or len(expected['datasets'])==1}
            if not target:target=expected['datasets']
            file=folder/'expected.json';file.write_text(json.dumps(target));command+=['--expect',str(file)]
        if 'reports' in expected or wrong_reports is not None:
            file=folder/'reports.json';file.write_text(json.dumps(wrong_reports if wrong_reports is not None else expected['reports']));command+=['--expect-reports',str(file)]
        process=subprocess.run(command,cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT),'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=90)
        assert process.returncode==code,(process.stdout,process.stderr)
        receipt=json.loads((out/'receipt.json').read_text());assert receipt['accepted'] is (code==0)
        assert (out/'result.json').exists() is (code==0)
        if code==0:
            assert_tree(json.loads((out/'result.json').read_text()),expected)
            if 'reports' in expected:assert {p.name:p.read_bytes() for p in (out/'reports').iterdir()}=={k:v.encode() for k,v in expected['reports'].items()}
        else:assert not (out/'reports').exists() and not (out/'exports').exists()
        return receipt


def wrong_comparators(mode):
    source=ORIGINAL.read_text();catalog=incoming();expected=original_expected();controls=0
    if mode=='means':
        for damage in ('value','boolean','missing','multiplicity','order','metadata'):
            wrong={'summary':deepcopy(expected['datasets']['summary'])};t=wrong['summary']
            if damage=='value':t['rows'][1]['variance']=2
            elif damage=='boolean':t['rows'][0]['_type_']=False
            elif damage=='missing':t['rows'][2]['variance']=0
            elif damage=='multiplicity':t['rows'].append(deepcopy(t['rows'][0]))
            elif damage=='order':t['schema']=dict(reversed(list(t['schema'].items())))
            else:t['schema']['avg']['label']='Measurement'
            receipt=cli_check(source,catalog,expected,wrong_dataset=wrong,code=1);assert receipt['comparison']=='failed';controls+=1
    else:
        for damage in ('value','header','newline','name','multiplicity','whitespace'):
            wrong={'print.txt':REPORT}
            if damage=='value':wrong['print.txt']=REPORT.replace('1 0 3 3 0 3 4','1 0 3 3 0 3 2')
            elif damage=='header':wrong['print.txt']=REPORT.replace('g _type_','Group _type_')
            elif damage=='newline':wrong['print.txt']=REPORT.rstrip('\n')
            elif damage=='name':wrong={'wrong.txt':REPORT}
            elif damage=='multiplicity':wrong['print.txt']=REPORT+REPORT.splitlines()[-1]+'\n'
            else:wrong['print.txt']=REPORT.replace(' ','  ',1)
            receipt=cli_check(source,catalog,expected,wrong_reports=wrong,code=1);assert receipt['report_comparison']=='failed';controls+=1
    return controls


def check_original():
    expected=original_expected();trace=original_trace();source=ORIGINAL.read_text()
    assert hashlib.sha256(source.encode()).hexdigest()==SOURCE_PIN
    assert ordered_digest(expected)==RESULT_PIN and hashlib.sha256(REPORT.encode()).hexdigest()==REPORT_PIN
    assert ordered_digest(trace)==TRACE_PIN and len(REPORT)==128 and len(trace)==19
    actual=execute(source,incoming(),True);witness=program_witness()
    assert_tree(actual['result'],expected);assert actual['trace']==trace
    assert_tree(witness['result'],expected);assert witness['trace']==trace
    assert witness['accounting']=={'statements':11,'steps':[{'kind':'sort','input_rows':12,'output_rows':12,'groups':0,'records':0},{'kind':'means','input_rows':12,'output_rows':6,'groups':6,'records':0},{'kind':'print','input_rows':6,'output_rows':0,'groups':0,'records':7}]}
    cli_check(source,incoming(),expected)


def main(mode='means'):
    check_original();hands=hand_cases(mode);generated=generated_cases(mode);cases=hands+generated
    witnesses=batch_witness([(s,c) for _,s,c in cases])
    for (name,source,catalog),witness in zip(cases,witnesses,strict=True):
        assert witness is not None,name
        actual=execute(source,catalog,True);assert_tree(actual['result'],witness['result']);assert actual['trace']==witness['trace'],name
    bad=refusal_cases(mode);witnesses=batch_witness([(s,c) for _,s,c in bad])
    for (name,source,catalog),witness in zip(bad,witnesses,strict=True):
        assert witness is None,name
        try:
            p=compile_plan(source)
            if not p.blocked:run_plan(p.to_dict(),catalog)
        except (ValueError,KeyError,TypeError,OverflowError,RuntimeError):pass
        else:assert p.blocked,name
    controls=wrong_comparators(mode)
    source=ORIGINAL.read_text()+'data bad;zero=0;v=1/zero;run;'
    cli_check(source,incoming(),original_expected(),code=1)
    print(f'VERIFIED: proc-{mode} {len(hands)} hand cases,{len(generated)} generated complete-source/runtime/R schedules,{len(bad)} shared refusals,{controls} actual CLI wrong comparisons;11-statement original,19 events,128 exact report bytes; no live SAS')
    return 0


if __name__=='__main__':raise SystemExit(main())
