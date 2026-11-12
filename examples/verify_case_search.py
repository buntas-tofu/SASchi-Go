#!/usr/bin/env python3
"""Original case/search pins and independent base-R evidence, no live SAS."""
import contextlib
from copy import deepcopy
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
ROOT=next(p for p in HERE.parents if (p/'sas_semantics.py').is_file())
sys.path.insert(0,str(ROOT))
from examples.wave_gate_common import assert_result
ORIGINAL=HERE/'case_search_capture.sas'
INPUTS=HERE/'case_search_inputs.json'
EXPECTED=HERE/'case_search_expected.json'
PINS=json.loads((HERE/'case_search_pins.json').read_text())
SOURCE_SHA='8de49f78d4704cfc2ffdf62c4640a5da80d66f8f72abe396fcb1e69a2e2bd3fe'


def encode(value):
    if type(value) is str:return 'c:'+value.encode('utf-8').hex()
    if value is None:return 'm:'
    if type(value) is bool:return 'b:1'
    if type(value) is dict:return 't:'+value['missing']
    return 'n:'+str(value)


def decode(value):
    if value=='REFUSE':return value
    if value.startswith('c:'):return bytes.fromhex(value[2:]).decode('ascii')
    if value=='m:':return None
    if value.startswith('n:'):return float(value[2:])
    raise AssertionError('oracle transport')


def rrun(mode,*paths):
    command=[os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript',str(HERE/'case_search.R'),mode,*map(str,paths)]
    return subprocess.run(command,capture_output=True,text=True,check=True,timeout=60).stdout.splitlines()


def r_cases(cases):
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'cases.csv'
        with path.open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['name','args'])
            writer.writerows((name,'|'.join(map(encode,args))) for name,args in cases)
        return list(map(decode,rrun('cases',path)))


def program_witness():
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==SOURCE_SHA
    expected=json.loads(EXPECTED.read_text());actual=deepcopy(expected)
    for table in actual['datasets'].values():table['rows']=[]
    actual['log']=[]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'input.csv'
        with path.open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['key','needle'])
            writer.writerows((row['key'],row['needle']) for row in json.loads(INPUTS.read_text())['raw']['rows'])
        records=rrun('program',ORIGINAL,path)
    assert records[0]=='STATEMENTS|20'
    for record in records[1:]:
        parts=record.split('|')
        if parts[0]=='ROW':
            schema=actual['datasets'][parts[1]]['schema']
            assert len(parts[2:])==len(schema)
            actual['datasets'][parts[1]]['rows'].append(dict(zip(schema,map(decode,parts[2:]))))
        elif parts[0]=='LOG':actual['log'].append(bytes.fromhex(parts[1]).decode('ascii'))
        else:raise AssertionError(record)
    assert actual==expected
    return expected


def qualify():
    observed=r_cases([(name,args) for name,args,_ in PINS])
    assert observed==[expected for _,_,expected in PINS]
    refusals=[('upcase',[value]) for value in ('',None,True,{'missing':'A'},'é','a\tb','x'*32768)]
    refusals += [('find',['ab',' ','T']),('find',['ab','a',-1]),('find',['ab','a',1.5]),('find',['ab','a','Q'])]
    assert r_cases(refusals)==['REFUSE']*len(refusals)
    assert 'ABC'.find('A')!=1
    assert 'ab'.find('b ')+1!=2
    assert ' aB '.upper().strip()!=' AB '
    program_witness()
    return refusals


def main():
    refusals=qualify()
    if '--qualify-only' in sys.argv:
        print('QUALIFIED: 14 hand pins,11 independent refusals,20-statement original and complete independent hand/R agreement; qualification timing recorded separately')
        return
    from sas_semantics import sas_upcase,sas_lowcase,sas_index,sas_find
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    from saschi.emit_py import translate
    from saschi.job import build_job
    functions={'upcase':sas_upcase,'lowcase':sas_lowcase,'index':sas_index,'find':sas_find}
    rng=random.Random(9611)
    cases=[(name,args) for name,args,_ in PINS]
    for _ in range(120):
        value=''.join(rng.choice(' AbCYz09!?') for _ in range(rng.randint(1,24)))
        needle=rng.choice(['A','b','?','z ','09'])
        cases.extend([('upcase',[value]),('lowcase',[value]),('index',[value,needle]),('find',[value,needle,'IT',rng.randrange(0,30)])])
    cases += [('upcase',['x'*32767]),('lowcase',['Z'*32767])]
    expected=r_cases(cases+refusals)
    for (name,args),wanted in zip(cases+refusals,expected):
        if wanted=='REFUSE':
            try:functions[name](*args)
            except ValueError:pass
            else:raise AssertionError(('missing refusal',name,args))
            continue
        assert functions[name](*args)==wanted
        literals=["'"+value.replace("'","''")+"'" if type(value) is str else str(value) for value in args]
        source='data d;x='+name+'('+','.join(literals)+');run;'
        plan=compile_plan(source);assert not plan.blocked,plan.tickets
        result=run_plan(plan.to_dict())['datasets']['d']
        assert result['rows']==[{'x':wanted}]
        if type(wanted) is str:assert result['schema']['x']=={'type':'character','length':len(args[0])}
    source=ORIGINAL.read_text();inputs=json.loads(INPUTS.read_text());wanted=program_witness()
    plan=compile_plan(source);assert not plan.blocked,plan.tickets
    assert_result(run_plan(plan.to_dict(),inputs),wanted)
    stream=io.StringIO();namespace={'inputs':inputs}
    with contextlib.redirect_stdout(stream):exec(translate(source).code,namespace)
    assert_result(namespace['result'],wanted)
    assert stream.getvalue()==''.join(line+'\n' for line in wanted['log'])
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);expect=root/'expected.json';expect.write_text(json.dumps(wanted['datasets']))
        log=root/'log.json';log.write_text(json.dumps(wanted['log']))
        job=build_job(source,inputs=INPUTS,expect=expect,expect_log=log)
        assert job.code==0 and job.receipt['accepted']
        command=[sys.executable,'-m','saschi','run',str(ORIGINAL),'--inputs',str(INPUTS),'--expect',str(expect),'--expect-log',str(log),'--output',str(root/'cli')]
        good=subprocess.run(command,capture_output=True,text=True,cwd=ROOT,timeout=60)
        assert good.returncode==0,good.stderr+good.stdout
        assert_result(json.loads((root/'cli/result.json').read_text()),wanted)
        receipt=json.loads((root/'cli/receipt.json').read_text())
        assert receipt['accepted'] and receipt['comparison']=='passed' and receipt['log_comparison']=='passed'
        for mutation in ('value','type','order','metadata','column-order'):
            bad=deepcopy(wanted['datasets'])
            if mutation=='value':bad['clean']['rows'][0]['first']=9
            elif mutation=='type':bad['reset']['rows'][0]['first']=False
            elif mutation=='order':bad['clean']['rows'].reverse()
            elif mutation=='column-order':bad['clean']['schema']=dict(reversed(list(bad['clean']['schema'].items())))
            else:del bad['clean']['schema']['key']['label']
            expect.write_text(json.dumps(bad))
            output=root/('wrong-'+mutation)
            wrong=subprocess.run(command[:-1]+[str(output)],capture_output=True,text=True,cwd=ROOT,timeout=60)
            assert wrong.returncode==1,(mutation,wrong.stdout,wrong.stderr)
            receipt=json.loads((output/'receipt.json').read_text())
            assert not receipt['accepted'] and receipt['comparison']=='failed' and receipt['error'].startswith('expected dataset differs:'),receipt
            assert receipt['log_comparison']=='passed' and (output/'observed.json').is_file() and not (output/'result.json').exists()
        expect.write_text(json.dumps(wanted['datasets']));log.write_text(json.dumps(wanted['log']+['wrong record']))
        output=root/'wrong-log'
        wrong=subprocess.run(command[:-1]+[str(output)],capture_output=True,text=True,cwd=ROOT,timeout=60)
        assert wrong.returncode==1,(wrong.stdout,wrong.stderr)
        receipt=json.loads((output/'receipt.json').read_text())
        assert not receipt['accepted'] and receipt['log_comparison']=='failed' and receipt['error']=='expected ordered log record bytes differ',receipt
        assert (output/'observed.json').is_file() and not (output/'result.json').exists()
    print('VERIFIED: case/search14hand pins,480generated source/runtime/R cases,max widths,11shared refusals,original20statements/six snapshots/six logical records,emitted/actual CLI,six receipt-verified wrong CLI controls; no live SAS')


if __name__=='__main__':main()
