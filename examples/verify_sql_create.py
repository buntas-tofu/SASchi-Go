#!/usr/bin/env python3
"""Descriptor-only SQL evidence; separate from general SQL and live SAS."""
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
from saschi.sql_create import parse_create,validate_step,materialize,RESERVED
from saschi.compare import equal,table_equal

ORIGINAL=HERE/'sql_create_capture.sas'
ROKU=Path(os.environ.get('SASCHI_ROKU_CORPUS',ROOT.parent/'saschi-roku'/'corpus'))
if not ROKU.is_absolute():raise ValueError('SQL witness requires an absolute corpus path')
CORPUS=ROKU/'table_creation_postal_addresses.sas'
SOURCE_PINS={'sql_create_capture.sas':'f7fb2e69dd4d2a3c8b22b3f43df495e2c9f7d22e399e39ff36c468454f1234e7',
             'table_creation_postal_addresses.sas':'7dca236b35f04e87491eb9cda52d3ae192b3ee6cb05fc96f674cc59074007349'}
RESULT_PINS={'sql_create_capture.sas':'7e3961a1917ccdc40603565b91ad8f1fe9add5b91ca2098f4ccb450999070b9c',
             'table_creation_postal_addresses.sas':'8b70a7a8fdbaf0580bfb0aa98ea18fd14c7785b92502f71b7ed8fceaf38ab335'}
STDOUT_PIN='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'


def columns(*pairs):return [{'name':name,'type':'character','length':width} for name,width in pairs]


PINS=[('CREATE TABLE One (value CHAR(1))',('one',columns(('value',1)))),
      ('create table limits (wide char(32767))',('limits',columns(('wide',32767)))),
      ('create table ordered (z char(2),a char(3))',('ordered',columns(('z',2),('a',3)))),
      ('cReAtE TaBlE MiXeD (Id CHAR ( 8 ), Zip char(20))',('mixed',columns(('id',8),('zip',20)))),
      ('create table _private (_first char(17))',('_private',columns(('_first',17)))),
      ('create table '+('t'*32)+' ('+('c'*32)+' char(32))',('t'*32,columns(('c'*32,32)))),
      ('create\ntable multiline\n(a\tchar(8),\nb char(50))',('multiline',columns(('a',8),('b',50)))),
      ('create table many ('+','.join('c'+str(i)+' char(1)' for i in range(64))+')',
       ('many',columns(*[('c'+str(i),1) for i in range(64)])))]
REFUSALS=['create table t ()','create table t (a char(0))','create table t (a char(32768))',
 'create table t (a char(-1))','create table t (a char(+1))','create table t (a char(01))',
 'create table t (a char(1.0))','create table t (a char(1e1))','create table t (a char(999999))',
 'create table t (a char)','create table t (a character(8))','create table t (a varchar(8))',
 'create table t (a numeric)','create table t (a numeric(8))','create table t (a int)',
 'create table t (a char(8),A char(9))','create table t (a char(8),)',
 'create table t (,a char(8))','create table t (a char(8),,b char(2))',
 'create table t (a char(8) b char(2))','create table t (achar(8))',
 'create table t (a char(8) not null)','create table t (a char(8) primary key)',
 'create table t (a char(8) unique)','create table t (a char(8) default x)',
 'create table t (a char(8) label="x")','create table t (a char(8) format=$8.)',
 'create table t (a char(8) length=4)','create table t (constraint uq unique(a))',
 'create table lib.t (a char(8))','create table t(keep=a) (a char(8))',
 'create table "t" (a char(8))',"create table 't'n (a char(8))",
 'create table t ("a" char(8))','create table t (a.b char(8))','create table &t (a char(8))',
 'create table t as select * from other','create table t like other',
 'create view t (a char(8))','create table t (a char(8)) extra',
 'create table t (a char(8)); delete from other','create table t (a char(8)) as select a from raw',
 'create table K (a char(8))','create table t (K char(8))',
 'create table '+('t'*33)+' (a char(8))','create table t ('+('c'*33)+' char(8))',
 'create table t ('+','.join('c'+str(i)+' char(1)' for i in range(65))+')']
REFUSALS += ['create table '+name+' (a char(8))' for name in sorted(RESERVED)]
REFUSALS += ['create table t ('+name+' char(8))' for name in sorted(RESERVED)]
HELPER_RESOURCE_REFUSAL='create'+' '*16385+'table t (a char(8))'
BOUNDARY_REFUSALS=['proc sql noexec;create table t (a char(8));quit;',
 'proc sql;quit;','proc sql;create table t (a char(8));run;',
 'proc sql;create table t (a char(8));','proc sql;create table t (a char(8));quit',
 'create table t (a char(8));',
 'proc sql;create table t (a char(8));create table u (a char(8));quit;',
 'proc sql;create table t (a char(8));insert into t values (1);quit;',
 'proc sql;create table t (a char(8));quit;proc print;run;',
 'proc sql;create table t (a char(8));quit;orphan=1;']


def step_for(name,cols,line=1,create_line=2):
    return {'kind':'sql_create','name':name,'line':line,'inputs':[],'by':[],
            'operations':[{'kind':'sql_create','line':create_line,'args':{'columns':deepcopy(cols)}}],
            'nodupkey':False,'where':None,'retained':{},'lengths':{},'display_names':{}}


def table_for(cols):return {'schema':{c['name']:{'type':'character','length':c['length']} for c in cols},'rows':[]}


def program(text):return 'proc sql;'+text+';quit;'


def rrun(*args,check=True):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'sql_create.R'),*map(str,args)],capture_output=True,text=True,check=check,timeout=90)


def decode(lines):
    result={'datasets':{},'log':[]};accounting={'statements':None,'tables':[],'rows':0};table=None
    for line in lines:
        tag,value=line.split(':',1)
        if tag=='STATEMENTS':accounting['statements']=int(value)
        elif tag=='TABLE':
            table={'schema':{},'rows':[]};result['datasets'][value]=table;accounting['tables'].append(value)
        elif tag=='COLUMN':
            name,width=value.split(',');table['schema'][name]={'type':'character','length':int(width)}
        elif tag=='ROWS':assert value=='0'
        else:raise AssertionError(line)
    return result,accounting


def batch_witness(cases):
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory)
        with (folder/'cases.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['path','existing'])
            for index,(source,existing) in enumerate(cases):
                path=folder/f'{index}.sas';path.write_text(source);writer.writerow([path,','.join(existing)])
        lines=rrun('batch',folder/'cases.csv').stdout.splitlines()
    results=[];current=[]
    for line in lines:
        if line.startswith('CASE:'):current=[]
        elif line.startswith('ANSWER:'):results.append(decode(current) if line=='ANSWER:OK' else None)
        else:current.append(line)
    assert len(results)==len(cases)
    return results


def program_witness(path=ORIGINAL):return decode(rrun('program',path).stdout.splitlines())


def original_expected():
    return {'datasets':{'contacts':table_for(columns(('record_id',8),('display_name',40),('region',2))),
                        'widths':table_for(columns(('_first',1),('boundary',32767),('final_2',17)))},'log':[]}


def corpus_expected():
    return {'datasets':{'address':table_for(columns(('addrid',8),('street',50),('city',25),('state',2),('zip',20)))},'log':[]}


def digest(value):return hashlib.sha256(json.dumps(value,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def generated_cases():
    rng=random.Random(5401);cases=[]
    for index in range(400):
        count=rng.randint(1,64);pairs=[(f'c{i}',rng.choice((1,2,8,50,256,32767,rng.randint(1,32767)))) for i in range(count)]
        rng.shuffle(pairs);name=f'table_{index}'
        text='create table '+name+' ('+',\n'.join(n+f' CHAR ( {w} )' for n,w in pairs)+')'
        if index%2:text=text.upper()
        cases.append((text,(name,columns(*pairs))))
    return cases


def check_helpers():
    good=PINS+generated_cases();witnesses=batch_witness([(program(text),[]) for text,_ in good]+[(program(text),[]) for text in REFUSALS])
    for index,((text,(name,cols)),witness) in enumerate(zip(good,witnesses)):
        assert equal(parse_create(text),(name,cols),ordered_maps=True),(index,text)
        step=step_for(name,cols);before=deepcopy(step);catalog={};table=materialize(step,catalog)
        assert equal(table,table_for(cols),ordered_maps=True) and equal(step,before,ordered_maps=True) and catalog=={}
        assert equal(witness,({'datasets':{name:table},'log':[]},{'statements':3,'tables':[name],'rows':0}),ordered_maps=True)
        table['schema'][cols[0]['name']]['length']=1
        assert equal(step,before,ordered_maps=True)
    for text,witness in zip(REFUSALS,witnesses[len(good):]):
        try:parse_create(text)
        except ValueError:pass
        else:raise AssertionError(('source refusal missing',text))
        assert witness is None,('R refusal missing',text)
    assert batch_witness([(source,[]) for source in BOUNDARY_REFUSALS])==[None]*len(BOUNDARY_REFUSALS)
    assert batch_witness([(program('create table t (a char(8))'),['T'])])==[None]
    try:parse_create(HELPER_RESOURCE_REFUSAL)
    except ValueError:pass
    else:raise AssertionError('standalone helper text cap')
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'padded.txt';path.write_text(HELPER_RESOURCE_REFUSAL)
        assert rrun('declaration',path).stdout.strip()=='REFUSE'
    # The shared scanner canonicalizes whitespace before helper admission.
    assert equal(batch_witness([(program(HELPER_RESOURCE_REFUSAL),[])]),[
        ({'datasets':{'t':table_for(columns(('a',8)))},'log':[]},{'statements':3,'tables':['t'],'rows':0})],ordered_maps=True)
    return good


def execute(source,catalog=None):
    from saschi.emit_py import translate
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    plan=compile_plan(source);assert not plan.blocked,plan.tickets
    supplied={} if catalog is None else deepcopy(catalog);before=deepcopy(supplied)
    serialized=plan.to_dict();saved=deepcopy(serialized);result=run_plan(serialized,supplied)
    assert equal(supplied,before,ordered_maps=True) and equal(serialized,saved,ordered_maps=True)
    translation=translate(source);assert not translation.blocked
    namespace={'inputs':deepcopy(supplied)};stdout=io.StringIO()
    with contextlib.redirect_stdout(stdout):exec(translation.code,namespace)
    assert equal(namespace['result'],result,ordered_maps=True)
    assert stdout.getvalue()==''.join(line+'\n' for line in result['log'])
    return result,stdout.getvalue()


def cli_check(path,expected,catalog=None):
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);output=folder/'job';command=[sys.executable,'-m','saschi','run',str(path),'--output',str(output)]
        if catalog is not None:
            inputs=folder/'inputs.json';inputs.write_text(json.dumps(catalog));command+=['--inputs',str(inputs)]
        if expected is not None:
            expected_path=folder/'expected.json';expected_path.write_text(json.dumps(expected['datasets']))
            command+=['--expect',str(expected_path)]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=40)
        receipt=json.loads((output/'receipt.json').read_text())
        if expected is None:
            assert result.returncode!=0 and not receipt['accepted'] and not (output/'result.json').exists()
            assert 'EARLIER' not in result.stdout
        else:
            assert result.returncode==0 and receipt['accepted'] and receipt['comparison']=='passed',(result.stdout,result.stderr)
            assert equal(json.loads((output/'result.json').read_text()),expected,ordered_maps=True)
            assert receipt['source_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()


def check_program(path,expected,count):
    assert hashlib.sha256(path.read_bytes()).hexdigest()==SOURCE_PINS[path.name]
    independent,accounting=program_witness(path)
    assert equal(independent,expected,ordered_maps=True) and accounting=={'statements':count,'tables':list(expected['datasets']),'rows':0}
    observed,stdout=execute(path.read_text());assert equal(observed,expected,ordered_maps=True) and stdout==''
    assert digest(observed)==RESULT_PINS[path.name]
    assert hashlib.sha256(stdout.encode()).hexdigest()==STDOUT_PIN
    cli_check(path,expected)


def cli_compare_failure(path,expected,observed):
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);output=folder/'job';expected_path=folder/'expected.json'
        expected_path.write_text(json.dumps(expected['datasets']))
        process=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--expect',str(expected_path),
            '--output',str(output)],cwd=ROOT,capture_output=True,text=True,timeout=40)
        receipt=json.loads((output/'receipt.json').read_text())
        assert process.returncode==1 and not receipt['accepted'] and receipt['comparison']=='failed'
        assert not (output/'result.json').exists() and (output/'observed.json').is_file()
        assert equal(json.loads((output/'observed.json').read_text()),observed,ordered_maps=True)
        assert receipt['result_sha256']==hashlib.sha256((output/'observed.json').read_bytes()).hexdigest()
        assert receipt['expected_sha256']==hashlib.sha256(expected_path.read_bytes()).hexdigest()


def naive_controls(actual_jobs=False):
    expected=corpus_expected()
    for damage in ('order','width','rows','metadata','type'):
        wrong=deepcopy(expected);table=wrong['datasets']['address']
        if damage=='order':table['schema']=dict(reversed(list(table['schema'].items())))
        elif damage=='width':table['schema']['street']['length']=8
        elif damage=='rows':table['rows']=[dict.fromkeys(table['schema'],'')]
        elif damage=='metadata':table['label']='invented'
        else:table['schema']['zip']='number'
        assert not equal(wrong,expected,ordered_maps=True)
        assert not table_equal(table,expected['datasets']['address'])
        if actual_jobs:cli_compare_failure(CORPUS,wrong,expected)
    return 5


def main():
    from saschi.plan import compile_plan
    good=check_helpers()
    for index,(text,(name,cols)) in enumerate(good):
        source=program(text);plan=compile_plan(source);assert not plan.blocked,plan.tickets
        from saschi.runtime import run_plan
        assert equal(run_plan(plan.to_dict()),{'datasets':{name:table_for(cols)},'log':[]},ordered_maps=True)
        if index<len(PINS) or index%40==0:assert equal(execute(source)[0],{'datasets':{name:table_for(cols)},'log':[]},ordered_maps=True)
    for text in REFUSALS:assert compile_plan(program(text)).blocked,text
    for source in BOUNDARY_REFUSALS:assert compile_plan(source).blocked,source
    assert equal(execute(program(HELPER_RESOURCE_REFUSAL))[0],{'datasets':{'t':table_for(columns(('a',8)))},'log':[]},ordered_maps=True)
    check_program(ORIGINAL,original_expected(),6)
    check_program(CORPUS,corpus_expected(),3)
    # Existing destinations refuse, even empty, without partial accepted output.
    source='data earlier;put "EARLIER";run;'+program('create table t (a char(8))')
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'collision.sas';path.write_text(source)
        cli_check(path,None,{'t':{'schema':{'a':'number'},'rows':[]}})
    assert naive_controls(actual_jobs=True)==5
    print(f'VERIFIED: SQL CREATE {len(PINS)} hand pins,400 independent R/source/runtime descriptor cases,'
          f'{len(REFUSALS)} shared declaration refusals,{len(BOUNDARY_REFUSALS)} procedure-boundary refusals,'
          'one helper-only resource refusal,one normalized-whitespace source control,'
          'one R existing-name refusal,5 naive controls; original6-statement/two-table witness; '
          'complete unchanged postal-address3-statement/zero-row program; source/emitted/CLI/R; no live SAS or physical log claim')
    print('VERIFIED corpus: table_creation_postal_addresses.sas; complete source/descriptor/empty-result/stdout pins, independent R and CLI; no live SAS')


if __name__=='__main__':main()
