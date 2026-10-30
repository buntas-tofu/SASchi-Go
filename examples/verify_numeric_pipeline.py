#!/usr/bin/env python3
"""Independent full-source R evidence for bounded rounded numeric pipelines."""
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
from examples.verify_binary64 import assert_tree
from examples.verify_numeric_rows import catalog_files,decode_program
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.emit_py import translate

ORIGINAL=HERE/'numeric_pipeline_capture.sas'
SOURCE_PIN='f69124cbbc6aecd2738fdb84ddd96d8bdc67c8f264a5e5e8cf314b5cc84f61fa'
RESULT_PIN='2e8308bd71e578c1061505cb8d4829c7afc4d23dbc2b816bac7a22fba691ce67'
STDOUT_PIN='2daff53a82fab95e1a7ab39626f24e95718a3720b92353e90865f3a1f50e91fb'


def rrun(*args):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'numeric_pipeline.R'),*map(str,args)],capture_output=True,text=True,check=True,timeout=60)


def witnesses(cases):
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory)
        with (folder/'cases.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['source','catalog'])
            for i,(source,catalog) in enumerate(cases):
                (folder/f'{i}.sas').write_text(source);catalog_files(folder/f'cat{i}',catalog)
                writer.writerow([f'{i}.sas',f'cat{i}'])
        lines=rrun('batch',folder).stdout.splitlines()
    results=[];current=[]
    for line in lines:
        if line.startswith('CASE:'):current=[]
        elif line.startswith('ANSWER:'):results.append(decode_program(current) if line=='ANSWER:OK' else None)
        elif not line.startswith('REASON:'):current.append(line)
    assert len(results)==len(cases)
    return results


def execute(source,catalog=None,emitted=False):
    plan=compile_plan(source);assert not plan.blocked,plan.tickets
    supplied={} if catalog is None else deepcopy(catalog);before=deepcopy(supplied)
    serialized=plan.to_dict();saved=deepcopy(serialized);observed=run_plan(serialized,supplied)
    assert supplied==before and serialized==saved
    if emitted:
        namespace={'inputs':deepcopy(supplied)};stdout=io.StringIO()
        with contextlib.redirect_stdout(stdout):exec(translate(source).code,namespace)
        assert_tree(namespace['result'],observed)
        assert stdout.getvalue()==''.join(line+'\n' for line in observed['log'])
    return observed


def inline_source(records,body='q=x/3;total+q;output;put q;',prefix='',names='x'):
    return ('data d;'+prefix+'input '+names+';trigger=1**1;'+body+'datalines;\n'+
            ''.join(record+'\n' for record in records)+';\nrun;')


def original_expected():
    schema={n:'number' for n in ('accumulated','total','seq','rolling','early')}
    rows=[];accumulated=0.;log=[]
    for seq,x,initial in ((1,1.,0.),(2,None,None),(3,3.,10.)):
        values=[None if x is None else x/j for j in (1,2,3)]
        rolling=None
        for value in values:
            if value is not None:rolling=value if rolling is None else rolling+value
        accumulated=accumulated+(rolling or 0.)
        total=(initial or 0.)+(rolling or 0.)
        rows.append({'accumulated':accumulated,'total':total,'seq':float(seq),'rolling':rolling,'early':None})
        total=total+1/3;total=total+1/3
        rows.append({'accumulated':accumulated,'total':total,'seq':float(seq),'rolling':rolling,'early':None if rolling is None else rolling/3})
    return {'datasets':{'pipeline':{'schema':schema,'rows':rows},
            'fresh':{'schema':{'answer':'number'},'rows':[{'answer':1.}]}},
            'log':['1 1.8333333333 2.5 ','2 . 0.6666666667 ','3 5.5 16.166666667 ']}


def pins(mode):
    if mode=='input':
        source=inline_source(['1','3 99','2 4','7'],names='x den',body='q=x/den;output;put q;')
        table={'schema':{'x':'number','den':'number','trigger':'number','q':'number'},
               'rows':[{'x':1.,'den':3.,'trigger':1.,'q':1/3},{'x':2.,'den':4.,'trigger':1.,'q':.5}]}
        return [(source,{}, {'datasets':{'d':table},'log':['0.3333333333 ','0.5 ']}),
                (inline_source([],body='if 0 then future=2;output;'),{},
                 {'datasets':{'d':{'schema':{'x':'number','trigger':'number','future':'number'},'rows':[]}},'log':[]})]
    if mode=='arrays':
        source='data d;array a{3} x y z;trigger=1**1;x=1000000000;y=.1;z=-1000000000;s=sum(of a{*});run;'
        expected={'datasets':{'d':{'schema':dict.fromkeys(('x','y','z','trigger','s'),'number'),
            'rows':[{'x':1e9,'y':.1,'z':-1e9,'trigger':1.,'s':.10000002384185791}]}},'log':[]}
        current='data d;array a x y;trigger=1**1;x=1/3;y=2/3;do over a;a=a*1.1;output;end;s=sum(of a{*});put s;run;'
        current_expected={'datasets':{'d':{'schema':dict.fromkeys(('x','y','trigger','s'),'number'),
            'rows':[{'x':(1/3)*1.1,'y':2/3,'trigger':1.,'s':None},
                    {'x':(1/3)*1.1,'y':(2/3)*1.1,'trigger':1.,'s':None}]}},'log':['1.1 ']}
        counted='data d;array a{3} x1-x3;trigger=1**1;do i=1 to 3;a{i}=1/i;end;s=sum(of a{*});run;'
        counted_expected={'datasets':{'d':{'schema':dict.fromkeys(('x1','x2','x3','trigger','i','s'),'number'),
            'rows':[{'x1':1.,'x2':.5,'x3':1/3,'trigger':1.,'i':4.,'s':1.8333333333333333}]}},'log':[]}
        return [(source,{},expected),(current,{},current_expected),(counted,{},counted_expected)]
    if mode=='loops':
        out=[]
        for kind,count in (('while',0),('until',1)):
            test='n<0' if kind=='while' else 'n>=0'
            source=f'data d;trigger=1**1;n=0;q=0;do {kind}({test});n=n+1;q=q+1/3;output;end;run;'
            out.append((source,{}, {'datasets':{'d':{'schema':dict.fromkeys(('trigger','n','q'),'number'),
                'rows':[] if count==0 else [{'trigger':1.,'n':1.,'q':1/3}]}},'log':[]}))
        for kind in ('while','until'):
            for predicate,initial,final in (("x<constant('pi')" if kind=='while' else "x>=constant('pi')",1.,4.),
                ('x**2<2' if kind=='while' else 'x**2>=2',1.,2.),
                ('sin(x)>0' if kind=='while' else 'sin(x)=0',.5,0.)):
                body='x=0;' if initial==.5 else 'x=x+1;'
                source=f'data d;x={initial!r};do {kind}({predicate});'+body+'end;run;'
                out.append((source,{}, {'datasets':{'d':{'schema':{'x':'number'},'rows':[{'x':final}]}},'log':[]}))
        return out
    supplied={'raw':{'encoding':'ascii','label':'source','schema':{'x':'number'},'rows':[{'x':1.},{'x':2.}]}}
    set_source='data d(drop=first second x trigger);array a{2} first second;set raw;trigger=1**1;a{1}=x/3;s=sum(of a{*});run;'
    set_expected={'datasets':{**supplied,'d':{'encoding':'ascii','label':'source','schema':{'s':'number'},'rows':[{'s':1/3},{'s':2/3}]}},'log':[]}
    return [(ORIGINAL.read_text(),{},original_expected()),(set_source,supplied,set_expected)]


def generated(mode):
    rng=random.Random({'input':5401,'arrays':5501,'loops':5601,'composition':5701}[mode]);cases=[]
    for i in range(120):
        if mode=='input':
            records=['.' if rng.randrange(5)==0 else str(rng.randint(1,80)/8) for _ in range(rng.randrange(5))]
            source=inline_source(records,body='q=x/3;total+q;if x>1 then scratch=q;output;put q;')
        elif mode=='arrays':
            size=rng.randint(1,4);assignments=''.join(f'a{{{j}}}='+('.' if rng.randrange(5)==0 else repr(rng.randint(1,80)/8))+'/3;' for j in range(1,size+1))
            source=f'data d;array a{{{size}}} x1-x{size};trigger=1**1;'+assignments+'s=sum(of a{*});output;x1=x1+1/3;output;put s;run;'
        elif mode=='loops':
            start=rng.randint(-2,4);stop=rng.randint(-2,8);kind=rng.choice(('while','until'));relation='<' if kind=='while' else '>='
            source=f'data d;trigger=1**1;n={start};q=0;do {kind}(n{relation}{stop});n=n+1;q=q+1/3;output;end;put q;run;'
        else:
            records=[' '.join(('.' if rng.randrange(6)==0 else str(rng.randint(1,24)/4),str(rng.randrange(5)))) for _ in range(rng.randrange(5))]
            source=ORIGINAL.read_text().replace('1 0\n. .\n3 10\n',''.join(r+'\n' for r in records))
        cases.append((source,{}))
    return cases


def refusals(mode):
    if mode=='input':return [(inline_source(['0.1']),{}),(inline_source(['.A']),{}),(inline_source(['1;']),{}),
        (inline_source(['1'],body='if 0 then bad=sin(4);'),{})]
    if mode=='arrays':return [('data d;array a{2} x y;trigger=1**1;if 0 then a{0}=1/3;run;',{}),
        ('data d;array a{2} x y;trigger=1**1;i=0;a{i}=1/3;run;',{}),
        ('data d;array a{2} x y;trigger=1**1;x=2147483647;y=1;s=sum(of a{*});run;',{}),
        ('data d;array a{1} x;trigger=1**1;a{1/1}=2;run;',{}),
        ('data d;array a x y;trigger=1**1;a{1}=1/3;run;',{}),
        ('data d;array sin{1} x;trigger=1**1;run;',{}),
        ('data d;array a{1} x;trigger=1**1;_error_=1/3;run;',{}),
        ('data d;array a{1} x;trigger=1**1;retain total 1+2;run;',{}),
        ('data d;array a{1} x;trigger=1**1;if 0 then z=sqrt(x);run;',{})]
    if mode=='loops':return [('data d;trigger=1**1;n=0;do while(n<10001);n=n+1;end;run;',{}),
        ('data d;trigger=1**1;do until(0);n=1/3;end;run;',{}),
        ('data d;trigger=1**1;do while(0);bad=sin(4);end;run;',{}),
        ('data d;trigger=1**1;do i=1 to 3;if i<2;output;end;do while(0);end;run;',{}),
        ('data d;trigger=1**1;i=0;do while(i<3);i=i+1;if i<2;output;end;run;',{})]
    return [(ORIGINAL.read_text().replace('1 0\n. .\n3 10\n','0.1 0\n'),{}),
            (ORIGINAL.read_text().replace('bucket{j}=x/j','bucket{0}=x/j'),{}),
            (ORIGINAL.read_text().replace('j=j+1;','j=j;',1),{}),
            ('data d;array a{1} first;set raw;trigger=1**1;a{1}=1/3;run;',
             {'raw':{'schema':{'unused':'number'},'rows':[{'unused':2147483648.}]}})]


def cli_check(source,expected):
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);path=folder/'program.sas';path.write_text(source);out=folder/'job'
        expect=folder/'expected.json';expect.write_text(json.dumps(expected['datasets']))
        process=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--expect',str(expect),'--output',str(out)],
            cwd=ROOT,capture_output=True,text=True,timeout=45)
        receipt=json.loads((out/'receipt.json').read_text())
        assert process.returncode==0 and receipt['accepted'] and receipt['comparison']=='passed',(process.stdout,process.stderr)
        assert_tree(json.loads((out/'result.json').read_text()),expected)
        assert receipt['source_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()


def naive_controls():
    expected=original_expected()
    for damage in ('all_missing','retained_reset','input_missing','scratch','snapshots','order','metadata','text'):
        wrong=deepcopy(expected);rows=wrong['datasets']['pipeline']['rows']
        if damage=='all_missing':rows[2]['rolling']=0.
        elif damage=='retained_reset':rows[4]['accumulated']=5.5
        elif damage=='input_missing':rows[2]['total']=rows[1]['total']
        elif damage=='scratch':rows[2]['early']=rows[1]['early']
        elif damage=='snapshots':rows.pop()
        elif damage=='order':wrong['datasets']['pipeline']['schema']=dict(reversed(list(wrong['datasets']['pipeline']['schema'].items())))
        elif damage=='metadata':wrong['datasets']['pipeline']['label']='wrong'
        else:wrong['log'][0]=wrong['log'][0].rstrip()
        try:assert_tree(wrong,expected)
        except AssertionError:pass
        else:raise AssertionError(('naive comparator blind',damage))
    try:assert_tree({'ordered':.1},{'ordered':.10000002384185791})
    except AssertionError:pass
    else:raise AssertionError('vectorized aggregation comparator blind')
    return 9


def cli_wrong_controls():
    """Eight actual table-comparison failures, with rejected observed artifacts.

    The existing --expect contract compares datasets only. Logical text has its
    separate exact result/emitted comparisons and is not passed off as --expect.
    """
    expected=original_expected();cases=[]
    for damage in ('all_missing','retained_reset','input_missing','scratch','snapshots','order','metadata'):
        wrong=deepcopy(expected['datasets']);rows=wrong['pipeline']['rows']
        if damage=='all_missing':rows[2]['rolling']=0.
        elif damage=='retained_reset':rows[4]['accumulated']=5.5
        elif damage=='input_missing':rows[2]['total']=rows[1]['total']
        elif damage=='scratch':rows[2]['early']=rows[1]['early']
        elif damage=='snapshots':rows.pop()
        elif damage=='order':wrong['pipeline']['schema']=dict(reversed(list(wrong['pipeline']['schema'].items())))
        else:wrong['pipeline']['label']='wrong'
        cases.append((ORIGINAL.read_text(),wrong,expected))
    source,_,observed=pins('arrays')[0];wrong=deepcopy(observed['datasets']);wrong['d']['rows'][0]['s']=.1
    cases.append((source,wrong,observed))
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory)
        for i,(source,wrong,observed) in enumerate(cases):
            path=folder/f'{i}.sas';path.write_text(source);expect=folder/f'{i}.json';expect.write_text(json.dumps(wrong));out=folder/f'out{i}'
            process=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--expect',str(expect),'--output',str(out)],
                cwd=ROOT,capture_output=True,text=True,timeout=45)
            receipt=json.loads((out/'receipt.json').read_text())
            assert process.returncode==1 and not receipt['accepted'] and receipt['comparison']=='failed'
            assert receipt['expected_sha256']==hashlib.sha256(expect.read_bytes()).hexdigest()
            assert not (out/'result.json').exists() and (out/'observed.json').is_file()
            assert_tree(json.loads((out/'observed.json').read_text()),observed)
    return len(cases)


def main(mode='composition'):
    assert mode in ('input','arrays','loops','composition')
    hand=pins(mode);cases=[(s,c) for s,c,_ in hand]+generated(mode);seen=witnesses(cases)
    for i,((source,catalog),independent) in enumerate(zip(cases,seen)):
        assert independent is not None,(mode,i,source)
        expected,accounting=independent;observed=execute(source,catalog,i<len(hand) or i%30==0)
        assert_tree(observed,expected)
        if i<len(hand):assert_tree(observed,hand[i][2])
        if mode=='composition' and i==0:
            assert accounting=={'statements':32,'steps':[{'name':'pipeline','iterations':3,'trips':15},{'name':'fresh','iterations':1,'trips':0}]},accounting
    bad=refusals(mode);seen=witnesses(bad)
    for (source,catalog),independent in zip(bad,seen):
        try:execute(source,catalog)
        except (ValueError,RuntimeError,AssertionError):pass
        else:raise AssertionError(('missing refusal',source))
        assert independent is None,('R missing refusal',source)
    cli_check(hand[0][0],hand[0][2])
    if mode=='composition':
        source=ORIGINAL.read_text()
        assert witnesses([(source+'proc print;run;',{}),(source.rsplit('run;',1)[0],{})])==[None,None]
        assert cli_wrong_controls()==8
        assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==SOURCE_PIN
        assert hashlib.sha256(json.dumps(original_expected(),separators=(',',':')).encode()).hexdigest()==RESULT_PIN
        assert hashlib.sha256(''.join(line+'\n' for line in original_expected()['log']).encode()).hexdigest()==STDOUT_PIN
    print(f'VERIFIED: numeric-pipeline-{mode} {len(hand)} hand pins,120 generated full-source/runtime/R cases,'
          f'{len(bad)} shared refusals,{naive_controls()} naive controls; exact structure/logical text,32-epsilon numeric budget; emitted/CLI, no live SAS')


if __name__=='__main__':main()
