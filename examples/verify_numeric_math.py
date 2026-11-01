#!/usr/bin/env python3
"""Finite complete-source base-R and high-precision numeric math evidence."""
from copy import deepcopy
from decimal import Decimal, localcontext
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
from examples.verify_numeric_rows import catalog_files,decode_program
from saschi import numeric_math
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.emit_py import translate

ORIGINAL=HERE/'numeric_math_capture.sas'
SOURCE_PIN='4f3f07e57504565b078f3ce6b47826a374a4559cb6d1c9c19002b9bf0a9c3592'
RESULT_PIN='0b19a5b653116ff0e73330a31e9057649311e460bf9000d38b2887f2c148f661'
STDOUT_PIN='395e101ecbaffe56ef28bfe8a8e73f1ab333aa68154ea7f4f42533a1b5544157'


def witnesses(cases,mode='sqrt'):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    entry={'sqrt':'numeric_sqrt.R','log':'numeric_log.R','sum':'rounded_sum.R'}[mode]
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory)
        with (folder/'cases.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['source','catalog'])
            for i,(source,catalog) in enumerate(cases):
                (folder/f'{i}.sas').write_text(source);catalog_files(folder/f'cat{i}',catalog)
                writer.writerow([f'{i}.sas',f'cat{i}'])
        output=subprocess.run([r,str(HERE/entry),'batch',str(folder)],capture_output=True,text=True,check=True,timeout=90)
    seen=[];current=[]
    for line in output.stdout.splitlines():
        if line.startswith('CASE:'):current=[]
        elif line.startswith('ANSWER:'):seen.append(decode_program(current) if line=='ANSWER:OK' else None)
        elif not line.startswith('REASON:'):current.append(line)
    assert len(seen)==len(cases),(output.stdout,output.stderr)
    return seen


def execute(source,catalog=None,emitted=False):
    p=compile_plan(source);assert not p.blocked,p.tickets
    plan=p.to_dict();saved=deepcopy(plan);supplied=deepcopy(catalog or {});before=deepcopy(supplied)
    observed=run_plan(plan,supplied);assert plan==saved and supplied==before
    if emitted:
        namespace={'inputs':deepcopy(supplied)};stdout=io.StringIO()
        with contextlib.redirect_stdout(stdout):exec(translate(source).code,namespace)
        assert_tree(namespace['result'],observed)
        assert stdout.getvalue()==''.join(line+'\n' for line in observed['log'])
    return observed


def original_expected():
    schema=dict.fromkeys(('running','root','logged','seq','combined','array_total','stage'),'number')
    rows=[]
    # Literal targets independently checked with Decimal90 and the base-R twin.
    total=3.1183451686887675
    for seq,root,logged,combined,running in [(1.,0.,0.,0.,0.),
            (2.,1.7320508075688772,1.3862943611198906,total,total),
            (3.,None,None,None,total)]:
        for stage in (1.,2.):rows.append({'running':running,'root':root,'logged':logged,'seq':seq,
            'combined':combined,'array_total':combined,'stage':stage})
    return {'datasets':{'transformed':{'schema':schema,'rows':rows},
            'fresh':{'schema':dict.fromkeys(('root','logged','combined','running'),'number'),
                'rows':[{'root':2.,'logged':0.,'combined':2.,'running':2.}]}},
            'log':['1 0 0 ','2 3.1183451687 3.1183451687 ','3 . 3.1183451687 ']}


def scalar(body,names,values,log=None):
    return ('data d;'+body+'run;',{}, {'datasets':{'d':{'schema':dict.fromkeys(names,'number'),
        'rows':[dict(zip(names,values))]}},'log':log or []})


def hand_cases(mode):
    if mode=='sqrt':
        return [scalar('x=sqrt(0);y=sqrt(4);z=sqrt(.);',('x','y','z'),(0.,2.,None)),
            scalar('x=sqrt(2);',('x',),(1.4142135623730951,)),
            scalar('x=sqrt(sum(1,3));',('x',),(2.,)),
            ('data d;array a x y;x=4;y=9;do over a;a=sqrt(a);output;end;run;',{},
                {'datasets':{'d':{'schema':dict.fromkeys(('x','y'),'number'),
                 'rows':[{'x':2.,'y':9.},{'x':2.,'y':3.}]}},'log':[]})]
    if mode=='log':
        return [scalar('x=log(1);y=log(2);z=log(.);',('x','y','z'),(0.,.6931471805599453,None)),
            scalar('x=log(.5);',('x',),(-.6931471805599453,)),
            scalar('x=log(1+0.00000000000000001);',('x',),(0.,)),
            scalar('x=log(1.0000000000000002);',('x',),(2.2204460492503128e-16,))]
    return [scalar('t=1**1;s=sum(.,.);z=sum(.,0);',('t','s','z'),(1.,None,0.)),
        scalar('t=1**1;s=sum(1000000000,.1,-1000000000);',('t','s'),(1.,.10000002384185791)),
        scalar('x=log(1);s=sum(.1,.2,.);',('x','s'),(0.,.30000000000000004)),
        scalar('x=sqrt(4);s=sum(.5,.25);',('x','s'),(2.,.75)),
        (ORIGINAL.read_text(),{},original_expected())]


def generated_cases(mode):
    rng=random.Random({'sqrt':6601,'log':6701,'sum':6801}[mode]);out=[]
    for i in range(120):
        values=['.' if rng.randrange(5)==0 else repr(rng.randint(0,128)/8) for _ in range(rng.randrange(5))]
        if mode=='sqrt':
            body='root=sqrt(x);if x>1 then scratch=root;total+root;output;'
        elif mode=='log':
            body='logged=log(1+x);if x>1 then scratch=logged;total+logged;output;'
        else:
            body='root=sqrt(x);combined=sum(root,.,x/3);total+combined;output;'
        source='data d;retain total 0;input x;'+body+'datalines;\n'+''.join(x+'\n' for x in values)+';\nrun;'
        if i%3==0:
            expr='sqrt(x)' if mode=='sqrt' else 'log(1+x)' if mode=='log' else 'sum(sqrt(x),.,x/3)'
            source=f'data d;array a{{2}} x y;x={rng.randrange(1,16)};y=.;z={expr};a{{1}}=z;s=sum(of a{{*}});output;x=x+1;output;run;'
        if i%7==0:
            expr='sqrt(n)' if mode=='sqrt' else 'log(1+n)' if mode=='log' else 'sum(sqrt(n),.,n/3)'
            source=f'data d;n=0;total=0;do while(n<3);n=n+1;q={expr};total=total+q;output;end;run;'
        if i%11==0:
            expr='sqrt(i)' if mode=='sqrt' else 'log(1+i)' if mode=='log' else 'sum(sqrt(i),.,i/3)'
            source=f'data d;do i=1 to 3;q={expr};output;end;run;'
        out.append((source,{}))
    return out


def refusal_cases(mode):
    common=[('data d;input x;y=sqrt(4);datalines;\n0.1\n;\nrun;',{}),
        ('data d;array a{1} x;y=sqrt(4);if 0 then a{0}=1;run;',{}),
        ('data d;y=sqrt(4);do i=1 to sqrt(4);x=i;end;run;',{}),
        ('data d;y=log(1);x=1;do while(x);x=x+1;end;run;',{}),
        ('data d;x=sqrt(1e-200*1e-200);run;',{})]
    if mode=='sqrt':return common+[('data d;if 0 then y=sqrt(-1);run;',{}),
        ('data d;input x;y=sqrt(-1);datalines;\n;\nrun;',{}),
        ('data d;x=-1;y=sqrt(x);run;',{}),('data d;y=sqrt(1,2);run;',{}),
        ('data d;array sqrt{1} x;y=sqrt(4);run;',{})]
    if mode=='log':return common+[('data d;if 0 then y=log(0);run;',{}),
        ('data d;y=log(-1);run;',{}),('data d;x=0;y=log(x);run;',{}),
        ('data d;y=log(1.0000000000000002);put y;run;',{}),('data d;y=log();run;',{})]
    return common+[('data d;t=1**1;s=sum(.,2147483648);run;',{}),
        ('data d;t=1**1;s=sum(2147483647,1,-1);run;',{}),
        ('data d;t=1**1;s=sum();run;',{}),('data d;t=1**1;s=sum(1,"bad");run;',{})]


def high_precision(mode):
    names=('sqrt','log') if mode=='sum' else (mode,);count=0
    for name in names:
        values=[0.,1.,2.,4.,2147483647.,sys.float_info.min] if name=='sqrt' else [1.,2.,.5,2147483647.,sys.float_info.min,math.nextafter(1.,2.),math.nextafter(1.,0.)]
        for x in values:
            with localcontext() as c:
                c.prec=90;d=Decimal.from_float(x);truth=float(d.sqrt() if name=='sqrt' else d.ln())
            actual=numeric_math.apply(name,[x])
            assert abs(actual-truth)<=32*sys.float_info.epsilon*max(1.,abs(truth));count+=1
    return count


def cli_check(source,expected,wrong=False):
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);path=folder/'program.sas';path.write_text(source);out=folder/'job'
        expect=folder/'expected.json';expect.write_text(json.dumps(expected['datasets']))
        p=subprocess.run([sys.executable,'-B','-m','saschi','run',str(path),'--expect',str(expect),'--output',str(out)],cwd=ROOT,capture_output=True,text=True,timeout=45)
        receipt=json.loads((out/'receipt.json').read_text())
        assert p.returncode==(1 if wrong else 0),(p.stdout,p.stderr,receipt)
        assert receipt['accepted'] is (not wrong) and receipt['comparison']==('failed' if wrong else 'passed')
        assert receipt['source_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
        assert (out/'observed.json' if wrong else out/'result.json').is_file()
        if wrong:assert not (out/'result.json').exists()
        else:assert_tree(json.loads((out/'result.json').read_text()),expected)


def wrong_comparators():
    expected=original_expected();count=0
    for damage in ('root','logarithm','all_missing','retained_reset','snapshot','order','fresh_reset'):
        wrong=deepcopy(expected);rows=wrong['datasets']['transformed']['rows']
        if damage=='root':rows[2]['root']=1.7
        elif damage=='logarithm':rows[2]['logged']=2.
        elif damage=='all_missing':rows[4]['combined']=0.
        elif damage=='retained_reset':rows[4]['running']=0.
        elif damage=='snapshot':rows.pop()
        elif damage=='order':wrong['datasets']['transformed']['schema']=dict(reversed(list(wrong['datasets']['transformed']['schema'].items())))
        else:wrong['datasets']['fresh']['rows'][0]['running']=5.1183451686887675
        cli_check(ORIGINAL.read_text(),wrong,True);count+=1
    source,_,truth=hand_cases('sum')[1];wrong=deepcopy(truth);wrong['datasets']['d']['rows'][0]['s']=.1
    cli_check(source,wrong,True);count+=1
    wrong=deepcopy(expected);wrong['log'][0]=wrong['log'][0].rstrip()
    try:assert_tree(wrong,expected)
    except AssertionError:count+=1
    else:raise AssertionError('exact logical text comparison did not reject trailing-blank damage')
    return count


def atomic_cli():
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory)
        for i,source in enumerate(['data earlier;x=1;put x;run;data d;x=0;y=log(x);run;',
                'data d;input x;y=sqrt(-1);datalines;\n;\nrun;']):
            path=folder/f'{i}.sas';path.write_text(source);out=folder/f'job{i}'
            p=subprocess.run([sys.executable,'-B','-m','saschi','run',str(path),'--output',str(out)],cwd=ROOT,capture_output=True,text=True,timeout=45)
            receipt=json.loads((out/'receipt.json').read_text());assert p.returncode in (1,2) and not receipt['accepted']
            assert not (out/'result.json').exists() and not (out/'observed.json').exists()
            assert '\n1 \n' not in p.stdout
    return 2



def promotion_control(source,expected=None):
    """Preserve each literal older-source frontier and explicit older markers."""
    from examples.verify_numeric_pipeline import witnesses as old_witnesses
    from saschi import binary64, numeric_pipeline
    assert old_witnesses([(source,{})])==[None]
    parsed=compile_plan(source);assert not parsed.blocked,parsed.tickets
    serialized=parsed.to_dict()
    assert serialized['steps'][0]['operations'][0]['args']=={'name':numeric_math.PROFILE}
    observed=execute(source,emitted=True);independent=witnesses([(source,{})])[0]
    assert independent is not None;assert_tree(observed,independent[0])
    if expected is not None:assert_tree(observed,expected)
    for marker in (binary64.PROFILE,binary64.ROWS_PROFILE,numeric_pipeline.PROFILE,None):
        forged=deepcopy(serialized)
        if marker is None:forged['steps'][0]['operations'].pop(0)
        else:forged['steps'][0]['operations'][0]['args']['name']=marker
        try:run_plan(forged)
        except ValueError:pass
        else:raise AssertionError(('older profile admitted new mathematics',marker))
    return observed


def main(mode='sum'):
    hand=hand_cases(mode);cases=[(s,c) for s,c,_ in hand]+generated_cases(mode)
    seen=witnesses(cases,mode)
    for i,((source,catalog),independent) in enumerate(zip(cases,seen)):
        assert independent is not None,(mode,i,source)
        expected,accounting=independent;observed=execute(source,catalog,i<len(hand) or i%30==0)
        assert_tree(observed,expected)
        if i<len(hand):assert_tree(observed,hand[i][2])
        if mode=='sum' and i==len(hand)-1:
            assert accounting=={'statements':29,'steps':[{'name':'transformed','iterations':3,'trips':6},{'name':'fresh','iterations':1,'trips':0}]},accounting
    bad=refusal_cases(mode)
    for (source,catalog),independent in zip(bad,witnesses(bad,mode)):
        try:execute(source,catalog)
        except (ValueError,RuntimeError,AssertionError):pass
        else:raise AssertionError(('missing Python refusal',source))
        assert independent is None,('missing R refusal',source)
    cli_check(hand[0][0],hand[0][2])
    controls=0
    if mode in ('sqrt','log'):
        for index,value in ((1,4. if mode=='sqrt' else .3010299956639812),(2,0.)):
            wrong=deepcopy(hand[0][2]);wrong['datasets']['d']['rows'][0][('y' if index==1 else 'z')]=value
            cli_check(hand[0][0],wrong,True);controls+=1
    if mode=='sum':
        assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==SOURCE_PIN
        assert hashlib.sha256(json.dumps(original_expected(),separators=(',',':')).encode()).hexdigest()==RESULT_PIN
        assert hashlib.sha256(''.join(x+'\n' for x in original_expected()['log']).encode()).hexdigest()==STDOUT_PIN
        assert witnesses([(ORIGINAL.read_text()+'proc print;run;',{}),(ORIGINAL.read_text().rsplit('run;',1)[0],{})],mode)==[None,None]
        cli_check(ORIGINAL.read_text(),original_expected());controls=wrong_comparators();assert controls==9;assert atomic_cli()==2
    print(f'VERIFIED: numeric-math-{mode} {len(hand)} hand pins,120 generated source/runtime/R cases,{len(bad)} shared refusals,{high_precision(mode)} Decimal90 targets,{controls} comparator controls; emitted/actual CLI;32-epsilon numeric, exact structure/logical text; no live SAS')


if __name__=='__main__':main()
