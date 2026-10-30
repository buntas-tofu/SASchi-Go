#!/usr/bin/env python3
"""DS-052/053 independent numeric-row and projection evidence, no live SAS."""
from copy import deepcopy
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
from examples.verify_binary64 import assert_tree
from saschi.emit_py import translate
from saschi.plan import compile_plan
from saschi.runtime import run_plan

ORIGINAL=HERE/'numeric_rows_capture.sas'
SOURCE_PIN='f662ecd018d7da511da0ec786d008ebac1bddc52a0dc10b4429b82a5985a3ce6'
RESULT_PIN='bd55e027f5c3edec7ab592051ec71c4bd81b790fbfea4cc775cedafce1436792'
STDOUT_PIN='2a7648ae08bdc6254170ff46d4618aeb9071bf03a25e86946021d0914c638460'


def incoming(rows=True):
    return {'incoming':{'encoding':'latin-1','label':'numeric source',
        'schema':{'key':{'type':'number','length':8,'label':'identifier'},'x':'number',
                  'carry':{'type':'number','length':8,'label':'input carry'},'excluded':'number'},
        'rows':[{'key':1.,'x':1.,'carry':10.,'excluded':100.},
                {'key':2.,'x':2.,'carry':None,'excluded':200.},
                {'key':3.,'x':3.,'carry':30.,'excluded':300.}] if rows else []}}


def catalog_files(folder,catalog):
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'descriptors.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['table','name','type','length','label','format','encoding','dataset_label'])
        for table_name,table in catalog.items():
            for name,spec in table['schema'].items():
                typed=isinstance(spec,dict);kind=spec['type'] if typed else spec
                writer.writerow([table_name,name,'typed-number' if typed and kind=='number' else kind,
                    spec.get('length','-') if typed else '-',spec.get('label','').encode().hex() if typed and 'label' in spec else '-',
                    spec.get('format','').encode().hex() if typed and 'format' in spec else '-',
                    table.get('encoding','-'),table['label'].encode().hex() if 'label' in table else '-'])
    with (folder/'values.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['table','row','name','kind','value'])
        for table_name,table in catalog.items():
            for index,row in enumerate(table['rows'],1):
                for name,value in row.items():
                    kind=('missing' if value is None else 'boolean' if isinstance(value,bool) else
                          'number' if isinstance(value,(int,float)) else 'character' if isinstance(value,str) else 'other')
                    writer.writerow([table_name,index,name,kind,value])


def rrun(*args,check=True):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'numeric_rows.R'),*map(str,args)],capture_output=True,text=True,check=check,timeout=120)


def decode_program(lines):
    result={'datasets':{},'log':[]};accounting={'statements':None,'steps':[]}
    table=None
    for line in lines:
        tag,value=line.split(':',1)
        if tag=='STATEMENTS':accounting['statements']=int(value)
        elif tag=='TABLE':table={'schema':{},'rows':[]};result['datasets'][value]=table
        elif tag=='META':
            encoding,label=value.split('|')
            schema,rows=table['schema'],table['rows'];table.clear()
            if encoding!='-':table['encoding']=encoding
            if label!='-':table['label']=bytes.fromhex(label).decode()
            table.update(schema=schema,rows=rows)
        elif tag=='COLUMN':
            name,kind,length,label,fmt=value.split('|')
            if kind=='number':spec='number'
            else:
                spec={'type':'number' if kind=='typed-number' else kind}
                if length!='-':spec['length']=int(length)
                if label!='-':spec['label']=bytes.fromhex(label).decode()
                if fmt!='-':spec['format']=bytes.fromhex(fmt).decode()
            table['schema'][name]=spec
        elif tag=='ROW':
            cells=value.split(',');values=[None if x=='M' else bytes.fromhex(x[1:]).decode() if x[0]=='C' else float(x[1:]) for x in cells]
            table['rows'].append(dict(zip(table['schema'],values)))
        elif tag=='ACCOUNT':
            name,iterations,trips=value.split(',');accounting['steps'].append({'name':name,'iterations':int(iterations),'trips':int(trips)})
        elif tag=='LOG':result['log'].append(bytes.fromhex(value).decode())
        else:raise AssertionError(line)
    return result,accounting


def batch_witness(cases):
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory)
        with (folder/'cases.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['source','catalog'])
            for index,(source,catalog) in enumerate(cases):
                (folder/f'{index}.sas').write_text(source)
                catalog_files(folder/f'catalog{index}',catalog)
                writer.writerow([f'{index}.sas',f'catalog{index}'])
        lines=rrun('batch',folder).stdout.splitlines()
    records=[];current=[]
    for line in lines:
        if line.startswith('CASE:'):current=[]
        elif line.startswith('ANSWER:'):
            records.append(decode_program(current) if line=='ANSWER:OK' else None)
        else:current.append(line)
    assert len(records)==len(cases)
    return records


def program_witness(path=ORIGINAL,catalog=None):
    return batch_witness([(path.read_text(),incoming() if catalog is None else catalog)])[0]


def execute(source,catalog=None,emitted=False):
    plan=compile_plan(source);assert not plan.blocked,plan.tickets
    supplied={} if catalog is None else deepcopy(catalog);before=deepcopy(supplied)
    serialized=plan.to_dict();saved=deepcopy(serialized)
    observed=run_plan(serialized,supplied)
    assert supplied==before and serialized==saved
    if emitted:
        generated=translate(source);assert not generated.blocked,generated.tickets
        stdout=io.StringIO();namespace={'inputs':deepcopy(supplied)}
        with contextlib.redirect_stdout(stdout):exec(generated.code,namespace)
        assert_tree(namespace['result'],observed)
        assert stdout.getvalue()==''.join(line+'\n' for line in observed['log'])
    return observed


def c1_source(value=1.,mode=0):
    header=('data d;' if mode==0 else 'data d(keep=future total ratio);' if mode==1 else 'data d(drop=trigger a);')
    tail='keep future total ratio;' if mode==0 else ''
    return (header+f'trigger=1**1;a={value!r};ratio=a/3;total=ratio*1.1;output;'
            'ratio=ratio+1/3;if 0 then future=2;output;put ratio;'+tail+'run;')


def c1_expected(value):
    ratio=1/3 if value==1 else 2/3;total=.3666666666666667 if value==1 else .7333333333333334
    return {'datasets':{'d':{'schema':{'ratio':'number','total':'number','future':'number'},
        'rows':[{'ratio':ratio,'total':total,'future':None},
                {'ratio':ratio+1/3,'total':total,'future':None}]}},'log':['0.6666666667 ' if value==1 else '1 ']}


def c1_pins():
    pins=[(c1_source(value,style),{},c1_expected(value)) for value in (1.,2.) for style in range(3)]
    pins[-1]=('data d(drop=i trigger hidden);trigger=1**1;ratio=0;do i=1 to 3;ratio=ratio+1/3;end;'
        'hidden=ratio*1.1;output;ratio=ratio+1/3;output;put ratio;run;',{},
        {'datasets':{'d':{'schema':{'ratio':'number'},'rows':[{'ratio':1.},{'ratio':4/3}]}},'log':['1.3333333333 ']})
    return pins


def original_expected():
    result={'datasets':incoming(),'log':['1 0.3333333333 . 7 ','2 0.6666666667 . . ','3 1 . . ',
        '2 0.4444444444 . ','3 1 31 ','0.5 ']}
    key=incoming()['incoming']['schema']['key'];meta={'encoding':'latin-1','label':'numeric source'}
    result['datasets']['shaped']={**meta,'schema':{'total':'number','key':key,'before':'number','carried':'number','ratio':'number','scratch':'number'},
        'rows':[{'total':1.,'key':2.,'before':None,'carried':None,'ratio':2/3,'scratch':None},
                {'total':2.,'key':3.,'before':None,'carried':31.,'ratio':1.,'scratch':None}]}
    result['datasets']['follow']={**meta,'schema':{'total':'number','key':key,'carried':'number','again':'number'},
        'rows':[{'total':1.,'key':2.,'carried':None,'again':4/9},
                {'total':2.,'key':3.,'carried':31.,'again':1.}]}
    result['datasets']['fresh']={'schema':{'answer':'number'},'rows':[{'answer':math.pi/6},{'answer':math.pi/3}]}
    return result


def original_accounting():
    return {'statements':28,'steps':[{'name':'shaped','iterations':3,'trips':0},
        {'name':'follow','iterations':2,'trips':0},{'name':'fresh','iterations':1,'trips':0}]}


def c2_pins():
    supplied=incoming();meta={'encoding':'latin-1','label':'numeric source'}
    def expected(name,values,initial=supplied):
        return {'datasets':{**deepcopy(initial),'d':{**meta,'schema':{name:'number'},'rows':[{name:v} for v in values]}},'log':[]}
    pins=[(ORIGINAL.read_text(),supplied,original_expected()),
      ('data d(keep=q);set incoming(keep=x);q=x/3;trigger=1**1;run;',supplied,expected('q',[1/3,2/3,1.])),
      ('data d(keep=q i total);retain total 0;set incoming(keep=key x);trigger=1**1;q=0;do i=1 to 2;'
       'q=q+x/3;total+x/3;end;put key q;run;',supplied,
       {'datasets':{**deepcopy(supplied),'d':{**meta,'schema':{'total':'number','q':'number','i':'number'},
         'rows':[{'total':2/3,'q':2/3,'i':3.},{'total':2.,'q':4/3,'i':3.},{'total':4.,'q':2.,'i':3.}]}},
        'log':['1 0.6666666667 ','2 1.3333333333 ','3 2 ']}),
      ('data d(keep=future);set incoming;trigger=1**1;if 0 then future=2;run;',incoming(False),expected('future',[],incoming(False))),
      ('data d(keep=before);set incoming(drop=excluded);before=excluded;trigger=1**1;run;',supplied,expected('before',[None]*3)),
      ('data d(keep=copy);set incoming;trigger=1**1;carry=carry+1;copy=carry;run;',supplied,expected('copy',[11.,None,31.])),
      ('data d(keep=s);set incoming;trigger=1**1;if key=1 then s=5;run;',supplied,expected('s',[5.,None,None]))]
    collision={'incoming':{**meta,'schema':{'total':'number','x':'number'},'rows':[{'total':2.,'x':1.},{'total':None,'x':2.}]}}
    pins.append(('data d(keep=total);set incoming;trigger=1**1;total+x;run;',collision,expected('total',[3.,2.],collision)))
    return pins


def generated(mode):
    rng=random.Random(5201 if mode=='projection' else 5301);cases=[]
    if mode=='projection':
        for _ in range(240):cases.append((c1_source(rng.randint(1,1000)/8,rng.randrange(3)),{}))
    else:
        for index in range(360):
            supplied=incoming(False);rows=[]
            for key in range(1,1+(0 if index%20==0 else rng.randrange(1,6))):
                rows.append({'key':float(key),'x':None if rng.randrange(8)==0 else rng.randint(1,1000)/8,
                    'carry':None if rng.randrange(5)==0 else float(rng.randrange(-10,20)),'excluded':float(rng.randrange(20))})
            supplied['incoming']['rows']=rows;style=rng.randrange(3);cut=rng.randrange(len(rows)+1)
            header='data d;' if style==0 else 'data d(keep=scratch ratio carried before key total);' if style==1 else 'data d(drop=x carry trigger excluded);'
            selection='drop=excluded' if index%2 else 'keep=carry x key'
            source=(header+'retain total 0;set incoming('+selection+');trigger=1**1;before=excluded;'
                'if key=1 then excluded=5;carry=carry+1;carried=carry;ratio=x/7;total+ratio;'
                f'if key=1 then scratch=ratio;if key>{cut} then output;put key ratio before;'+
                ('keep scratch ratio carried before key total;' if style==0 else '')+'run;')
            cases.append((source,supplied))
    return cases


def refusal_cases(mode):
    base='data d(keep=a);trigger=1**1;a=1;'
    cases=[(base+'if 0 then hidden=sin(4);run;',{}),
        ('data d(keep=absent);trigger=1**1;a=1;run;',{}),
        (base+'z=0;hidden=1/z;put a;run;',{}),
        (base+'a=0.00001;put a;run;',{}),
        (base+'drop a;run;',{}),
        ('data d(keep=a);trigger=1**1;array v{1} a;run;',{}),
        ('data d(keep=a);trigger=1**1;a=1;do while(a<2);a=a+1;end;run;',{})]
    if mode=='set':
        for value in (2147483648.,2.**-1074,{'missing':'A'},True):
            supplied=incoming();supplied['incoming']['rows'][-1]['carry']=value
            cases.append(('data d(keep=q);set incoming;q=1**1;carry=0;if 0 then output;run;',supplied))
        supplied=incoming(False);supplied['incoming']['schema']['carry']={'type':'character','length':4}
        cases.append(('data d(keep=q);set incoming;q=1**1;run;',supplied))
        for rows in (False,True):
            supplied=incoming(rows);supplied['incoming']['schema']['key']['format']='8.'
            cases.append(('data d(keep=q);set incoming;trigger=1**1;q=x/3;put key;run;',supplied))
        cases.append(('data d(keep=q);set incoming;trigger=1**1;q=x/3;put absent;run;',incoming()))
        cases += [('data d;set incoming;where x>0;q=1**1;run;',incoming()),
                  ('data d;set incoming;by key;q=1**1;run;',incoming()),
                  ('data d;set incoming(keep=absent);q=1**1;run;',incoming())]
        supplied=incoming(False);supplied['incoming']['schema']['carry']={'type':'number','length':4}
        cases.append(('data d(keep=q);set incoming;q=1**1;run;',supplied))
        cases.append(('data d(keep=q);q=1**1;set incoming;run;',incoming()))
        supplied=incoming(False);supplied['incoming']['schema']['_all_']='number'
        cases.append(('data d(keep=q);set incoming;q=1**1;run;',supplied))
    return cases


def cli_check(source,catalog,expected=None):
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);path=folder/'program.sas';path.write_text(source)
        inputs=folder/'inputs.json';inputs.write_text(json.dumps(catalog,allow_nan=False))
        output=folder/'job'
        process=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--inputs',str(inputs),'--output',str(output)],
            cwd=ROOT,capture_output=True,text=True,timeout=45)
        receipt=json.loads((output/'receipt.json').read_text())
        if expected is None:
            assert process.returncode!=0 and not receipt['accepted']
            assert not (output/'result.json').exists()
            assert 'EARLIER' not in process.stdout
        else:
            assert process.returncode==0 and receipt['accepted'],(process.stdout,process.stderr)
            assert_tree(json.loads((output/'result.json').read_text()),expected)
            assert receipt['source_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()


def naive_controls(mode='set'):
    if mode=='projection':
        expected=c1_expected(1.)
        for damage in ('early_value','order','missing','schema','rows','logs'):
            wrong=deepcopy(expected);table=wrong['datasets']['d']
            if damage=='early_value':table['rows'][0]['ratio']=2/3
            elif damage=='order':table['schema']=dict(reversed(list(table['schema'].items())))
            elif damage=='missing':table['rows'][0]['future']=0.
            elif damage=='schema':table['schema']['a']='number'
            elif damage=='rows':table['rows'].append(deepcopy(table['rows'][-1]))
            else:wrong['log'][0]=wrong['log'][0].rstrip()
            try:assert_tree(wrong,expected)
            except AssertionError:pass
            else:raise AssertionError(('C1 comparator control blind',damage))
        return 6
    expected=original_expected();wrong=deepcopy(expected)
    wrong['datasets']['shaped']['rows'][0]['before']=200.
    try:assert_tree(wrong,expected)
    except AssertionError:pass
    else:raise AssertionError('input timing control blind')
    for damage in ('order','missing','scratch','rows','logs'):
        wrong=deepcopy(expected);table=wrong['datasets']['shaped']
        if damage=='order':table['schema']=dict(reversed(list(table['schema'].items())))
        elif damage=='missing':table['rows'][0]['carried']=11.
        elif damage=='scratch':table['rows'][0]['scratch']=1/3
        elif damage=='rows':table['rows'].append(deepcopy(table['rows'][-1]))
        else:wrong['log'][0]=wrong['log'][0].rstrip()
        try:assert_tree(wrong,expected)
        except AssertionError:pass
        else:raise AssertionError(('comparator control blind',damage))
    return 6


def main(mode='projection'):
    assert mode in ('projection','set')
    pins=(c1_pins()
          if mode=='projection' else c2_pins())
    cases=[(source,catalog) for source,catalog,_ in pins]+generated(mode)
    witnesses=batch_witness(cases)
    for index,((source,catalog),witness) in enumerate(zip(cases,witnesses)):
        assert witness is not None,(index,source)
        independent,accounting=witness
        observed=execute(source,catalog,emitted=index<len(pins) or index%40==0)
        assert_tree(observed,independent)
        if index<len(pins):assert_tree(observed,pins[index][2])
        if mode=='set' and index==0:assert accounting==original_accounting(),accounting
    refusals=refusal_cases(mode);refused=batch_witness(refusals)
    for (source,catalog),witness in zip(refusals,refused):
        try:execute(source,catalog)
        except (ValueError,AssertionError,RuntimeError):pass
        else:raise AssertionError(('missing refusal',source,catalog))
        assert witness is None,('R missing refusal',source)
    source,catalog,expected=pins[0];cli_check(source,catalog,expected)
    if mode=='set':
        assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==SOURCE_PIN
        assert hashlib.sha256(json.dumps(expected,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==RESULT_PIN
        assert hashlib.sha256(''.join(line+'\n' for line in expected['log']).encode()).hexdigest()==STDOUT_PIN
        # The independent interpreter must account for all executable source.
        assert batch_witness([(source+'proc print;run;',catalog),(source.rsplit('run;',1)[0],catalog)])==[None,None]
        bad=incoming();bad['incoming']['rows'][-1]['carry']=2147483648.
        cli_check('data earlier;put "EARLIER";run;'+source,bad)
    else:cli_check('data earlier;put "EARLIER";run;'+refusals[2][0],{})
    controls=naive_controls(mode)
    print(f'VERIFIED: numeric-{mode} {len(pins)} hand source pins,{len(cases)-len(pins)} generated source/runtime/R schedules,'
          f'{len(refusals)} shared refusals,{controls} comparator controls; exact schema/missing/order/logical text,'
          '32-epsilon numeric budget; emitted and actual CLI evidence; no live SAS or exact BEST12 claim')


if __name__=='__main__':main()
