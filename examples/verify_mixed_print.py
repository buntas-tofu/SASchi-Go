#!/usr/bin/env python3
"""Original complete-source mixed PRINT/TITLE evidence with independent base R."""
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
from sas_semantics import sas_proc_sort
from saschi.character_input import execute_step as execute_character
from saschi.compare import equal
from saschi.emit_py import translate
from saschi.mixed_reports import execute_title,execute_print,validate_program
from saschi.plan import compile_plan
from saschi.runtime import run_plan

ORIGINAL=HERE/'mixed_reports_capture.sas'
VALUES=[('beta','B',9),('alpha','A',2),('beta','A',7),('','',None),
        ('two words','C',-3),('alpha','A',4),('path\\leaf','D',0),('Zebra','%',None)]
ORDER=[4,8,2,6,3,1,7,5]
FIRST='TITLE:   Intake  \nobs word code n\n1 "beta" "B" 9\n2 "alpha" "A" 2\n3 "beta" "A" 7\n4 "" "" .\n5 "two words" "C" -3\n6 "alpha" "A" 4\n7 "path\\\\leaf" "D" 0\n8 "Zebra" "%" .\n'
SECOND='TITLE: After ordering\nobs word code n\n1 "" "" .\n2 "Zebra" "%" .\n3 "alpha" "A" 2\n4 "alpha" "A" 4\n5 "beta" "A" 7\n6 "beta" "B" 9\n7 "path\\\\leaf" "D" 0\n8 "two words" "C" -3\n'
ACCOUNT_NAMES=['statements','opaque_payloads','steps','physical_records','input_attempts','observations',
               'outputs','sort_steps','title_sets','title_resets','print_steps','printed_rows']
ORIGINAL_ACCOUNT=dict(zip(ACCOUNT_NAMES,[16,1,8,8,9,8,8,1,2,2,2,16]))
SOURCE_PIN='a04c9418df8578dcc0cf30d48d8e0addda1aa1189d4a460ab17aca1d66e12c85'
RESULT_PIN='e0369bdaf46e57c90d0572863bba9486f782e5ff94a3c6bd3d6fd85d975831a3'
TRACE_PIN='379e30e8beb413247fa0fdb7ec90697129f6a909e305370ea7014d2a9d7e6daa'
REPORT_PINS=['65b2f3381cc7629345dab0b3fe53b93b252bc86088c409224a24eb0c3b7513ba','2df243400dca97d2fe79db09a9bcd164095a2191219eb87a03df682e2e137ef8']


def digest(value):
    return hashlib.sha256(json.dumps(value,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def assert_tree(actual,expected):
    assert equal(actual,expected,ordered_maps=True),(actual,expected)


def original_expected():
    raw={'schema':{'word':{'type':'character','length':12},'code':{'type':'character','length':4},'n':{'type':'number','length':8}},
         'rows':[{'word':word.ljust(12),'code':code.ljust(4),'n':None if n is None else float(n)} for word,code,n in VALUES]}
    ordered=deepcopy(raw);ordered['rows']=[deepcopy(raw['rows'][i-1]) for i in ORDER]
    return {'datasets':{'raw':raw,'ordered':ordered},'log':[],'reports':{'print_01.txt':FIRST,'print_02.txt':SECOND}}


def original_trace():
    trace=[]
    for i in range(1,10):
        trace.append({'kind':'character_input','line':3,'attempt':i,'complete':i<=8})
        if i<=8:trace.append({'kind':'character_output','line':3,'observation':i})
    for name,table,title,report,lines in [('raw','raw','  Intake  ',FIRST,None),('ordered','ordered','After ordering',SECOND,None)]:
        if name=='ordered':trace.extend(['sort|input|raw|8','sort|output|ordered|8'])
        trace.append('title|set|'+title.encode().hex())
        trace.append('mixed-print|input|'+table+'|8')
        records=report.splitlines();trace.append('mixed-print|title|'+records[0].encode().hex())
        trace.append('mixed-print|header|'+records[1].encode().hex())
        trace.extend('mixed-print|row|'+record.encode().hex() for record in records[2:])
        file='print_01.txt' if name=='raw' else 'print_02.txt'
        trace.append('mixed-print|output|'+file+'|'+str(len(report)))
        trace.append('title|reset')
    return trace


def decode(lines):
    result={'datasets':{},'log':[]};trace=[];account=None;table=None
    for line in lines:
        tag,_,value=line.partition(' ')
        if tag=='TABLE':table={'schema':{},'rows':[]};result['datasets'][value]=table
        elif tag=='COL':
            name,kind,width=value.split();table['schema'][name]={'type':kind,'length':int(width)}
        elif tag=='ROW':
            fields=value.split('|');cells=[]
            for field in fields:
                if field=='M':cells.append(None)
                elif field.startswith('C:'):cells.append(bytes.fromhex(field[2:]).decode('ascii'))
                elif field.startswith('N:'):cells.append(float(field[2:]))
                else:raise AssertionError(field)
            table['rows'].append(dict(zip(table['schema'],cells,strict=True)))
        elif tag=='ENDTABLE':pass
        elif tag=='REPORT':
            name,encoded=value.split();result.setdefault('reports',{})[name]=bytes.fromhex(encoded).decode('ascii')
        elif tag=='TRACE_STRING':trace.append(bytes.fromhex(value).decode('ascii'))
        elif tag=='TRACE_INPUT':
            source_line,attempt,complete=map(int,value.split());trace.append({'kind':'character_input','line':source_line,'attempt':attempt,'complete':bool(complete)})
        elif tag=='TRACE_OUTPUT':
            source_line,observation=map(int,value.split());trace.append({'kind':'character_output','line':source_line,'observation':observation})
        elif tag=='ACCOUNT':account=dict(zip(ACCOUNT_NAMES,map(int,value.split()),strict=True))
        else:raise AssertionError(line)
    return {'result':result,'trace':trace,'accounting':account}


def batch_witness(sources,mode='print'):
    with tempfile.TemporaryDirectory(prefix='mixed-report-R-') as temporary:
        directory=Path(temporary);paths=[]
        for i,source in enumerate(sources):
            p=directory/(str(i)+'.sas');p.write_text(source);paths.append(str(p))
        manifest=directory/'paths.txt';manifest.write_text('\n'.join(paths)+'\n')
        r=shutil.which('Rscript');assert r is not None
        twin='mixed_reports.R' if mode=='print' else 'logical_title.R'
        process=subprocess.run([r,str(HERE/twin),str(manifest)],cwd=ROOT,text=True,capture_output=True,timeout=120)
        assert process.returncode==0,(process.stdout,process.stderr)
        blocks=[];current=None
        for line in process.stdout.splitlines():
            if line.startswith('BEGIN '):current=[]
            elif line=='END':blocks.append(None if current==['REFUSED'] else decode(current[1:]));current=None
            else:
                assert current is not None;current.append(line)
        assert len(blocks)==len(sources);return blocks


def program_witness(path=ORIGINAL,mode='print'):
    return batch_witness([Path(path).read_text()],mode)[0]


def execute(source,emitted=False):
    parsed=compile_plan(source)
    if parsed.blocked:raise ValueError(str(parsed.tickets))
    plan=parsed.to_dict();before=deepcopy(plan);actual=run_plan(plan);assert plan==before
    tables={};trace=[];reports={};title=None;ordinal=0
    validate_program(plan)
    for step in plan['steps']:
        kind=step['kind']
        if kind=='character_data':tables[step['name']],logs=execute_character(step,tables,trace=trace);assert logs==[]
        elif kind=='report_title':title=execute_title(step,trace=trace)
        elif kind=='mixed_print':
            ordinal+=1;reports.update(execute_print(step,tables,title,ordinal,trace=trace))
        elif kind=='sort':
            source_table=tables[step['inputs'][0]];trace.append('sort|input|'+step['inputs'][0]+'|'+str(len(source_table['rows'])))
            table=deepcopy(source_table);table['rows']=deepcopy(sas_proc_sort(source_table['rows'],step['by'],step['nodupkey']))
            tables[step['name']]=table;trace.append('sort|output|'+step['name']+'|'+str(len(table['rows'])))
        else:raise AssertionError(kind)
    traced={'datasets':tables,'log':[]}
    if reports:traced['reports']=reports
    assert_tree(actual,traced)
    if emitted:
        namespace={'__name__':'__mixed_report_fixture__'};stream=io.StringIO()
        with contextlib.redirect_stdout(stream):exec(translate(source).code,namespace)
        assert stream.getvalue()=='';assert_tree(namespace['result'],actual)
    return {'result':actual,'trace':trace,'final_title':title}


def data_source(records=None,columns='word :$12. code :$4. n',name='raw'):
    if records is None:records=['beta,B,2','alpha,A,1']
    return f'data {name};infile datalines dsd;input {columns};datalines4;\n'+'\n'.join(records)+('\n' if records else '')+';;;;\nrun;\n'


def title_source(text):
    return 'title;' if text is None else "title '"+text.replace("'","''")+"';"


def hand_cases(mode):
    base=data_source();printed='proc print data=raw;run;'
    if mode=='title':
        return [('set',base+title_source('hello')+printed),('reset',base+title_source('hello')+'title;'+printed),
                ('outer-spaces',base+title_source('  hello  ')+printed),('semicolon',base+title_source('one;two')+printed),
                ('escaped-apostrophe',base+title_source("reader's view")+printed),('quoted-double',base+title_source('say "hello"')+printed),
                ('max-title',base+title_source('x'*128)+printed),('empty-data',data_source([])+title_source('empty')+printed),
                ('persist-sort',base+title_source('same')+printed+'proc sort data=raw out=s;by word;run;proc print data=s;run;'),
                ('original',ORIGINAL.read_text())]
    return [('default-order',base+printed),('empty',data_source([])+printed),
            ('blank-fields',data_source([',,'])+printed),('internal-space',data_source(['two words,A,1'])+printed),
            ('backslash',data_source(['path\\leaf,A,-1'])+printed),('raw-keywords',data_source(['title run,B,2'])+printed),
            ('opaque-semicolon',data_source(['a;b,A,3'])+printed),('integer-bound',data_source(['x,A,-2147483647','y,B,2147483647'])+printed),
            ('missing-and-zero',data_source(['x,A,.','y,B,-0'])+printed),
            ('all-character',data_source(['b,B','a,A'],columns='word :$12. code :$4.')+printed),
            ('stable-sort',base+'proc sort data=raw out=s;by word code;run;proc print data=s;run;'),
            ('original',ORIGINAL.read_text())]


def generated_cases(mode,count=160):
    rng=random.Random(70619 if mode=='print' else 70620);cases=[]
    words=['','alpha','beta','two words','a;b','a\\b','x&y','x%y']
    for i in range(count):
        records=[]
        for _ in range(rng.randrange(0,9)):
            value=rng.choice([None,0,-1,rng.randrange(-99,100)]);records.append(','.join([rng.choice(words),rng.choice(['','A','B']),'.' if value is None else str(value)]))
        source=data_source(records);title=rng.choice([None,'first','  padded  ',"reader's view",'one;two'])
        source+=title_source(title)+'proc print data=raw;run;'
        if rng.randrange(2):
            source+='proc sort data=raw out=s'+(' nodupkey' if rng.randrange(2) else '')+';by word code;run;'
            source+=title_source(rng.choice([None,'second']))+'proc print data=s;run;'
        source+='title;';cases.append((f'generated-{i}',source))
    return cases


def refusal_cases(mode):
    base=data_source();printed='proc print data=raw;run;'
    common=[('no-character-trigger','data d;x=1;run;title "x";proc print data=d;run;'),
            ('numeric-only-DSD',data_source(['1'],columns='n')+printed),('legacy-mix',base+'data d;x=1;run;'+printed),
            ('third-print',base+printed*3),('too-many-title',base+'title;'*33+printed),
            ('undefined-input',base+'proc print data=absent;run;'),('MEANS-mix',base+'proc means data=raw;run;'+printed),
            ('late-fraction',data_source(['x,A,1','y,B,1.5'])+printed),('obs-column',data_source([],columns='obs :$1. n')+printed),
            ('nonascii-record',data_source(['é,A,1'])+printed),('quoted-record',data_source(['"x",A,1'])+printed),
            ('late-wide',data_source(['x,A,1','x'*13+',B,2'])+printed),('64-step-cap',base+'title;'*31+printed*2+'proc sort data=raw;by word;run;'*31)]
    if mode=='title':
        more=[('empty-title',"title '';"),('blank-title',"title ' ';"),('macro-amp',"title '&x';"),('macro-percent',"title '%x';"),
              ('TITLE2',"title2 'x';"),('two-literals',"title 'a' 'b';"),('variable-title','title word;'),
              ('wide-title',title_source('x'*129)),('nonascii-title',title_source('é')),('missing-title-semicolon',"title 'x' ")]
        return common+[(name,base+bad+printed) for name,bad in more]
    more=[('NOOBS','proc print data=raw noobs;run;'),('VAR','proc print data=raw;var word;run;'),
          ('LABEL','proc print data=raw label;run;'),('OBS-option','proc print data=raw(obs=1);run;'),
          ('FORMAT','proc print data=raw;format n 8.;run;'),('BY','proc print data=raw;by word;run;'),
          ('implicit-input','proc print;run;'),('qualified-input','proc print data=work.raw;run;'),
          ('missing-RUN-semicolon','proc print data=raw;run'),('QUIT','proc print data=raw;quit;')]
    return common+[(name,base+bad) for name,bad in more]


def cli_check(source,expected,reports,expected_exit=0):
    with tempfile.TemporaryDirectory(prefix='mixed-report-cli-') as temporary:
        directory=Path(temporary);sp=directory/'source.sas';ep=directory/'expected.json';rp=directory/'reports.json';out=directory/'job'
        sp.write_text(source);ep.write_text(json.dumps(expected['datasets']));rp.write_text(json.dumps(reports))
        process=subprocess.run([sys.executable,'-B','-m','saschi','run',str(sp),'--expect',str(ep),'--expect-reports',str(rp),'--output',str(out)],
                               cwd=ROOT,env=dict(os.environ,PYTHONPATH=str(ROOT)),text=True,capture_output=True,timeout=90)
        assert process.returncode==expected_exit,(process.stdout,process.stderr)
        receipt=json.loads((out/'receipt.json').read_text());assert receipt['accepted'] is (expected_exit==0)
        if expected_exit==0:
            assert_tree(json.loads((out/'result.json').read_text()),expected)
            assert {p.name:p.read_text() for p in (out/'reports').iterdir()}==reports
            assert receipt['report_comparison']=='passed'
        else:
            assert not (out/'result.json').exists() and not (out/'reports').exists() and not (out/'exports').exists()
            if (out/'observed.json').exists():assert_tree(json.loads((out/'observed.json').read_text()),original_expected())
        return receipt


def wrong_comparators(mode):
    truth=original_expected();source=ORIGINAL.read_text();controls=[]
    if mode=='title':
        damages=[('title-value',FIRST.replace('Intake','Intakes',1)),('leading-space',FIRST.replace('TITLE:   ','TITLE:  ',1)),
                 ('trailing-space',FIRST.replace('Intake  \n','Intake \n',1)),('title-omitted','\n'.join(FIRST.splitlines()[1:])+'\n'),
                 ('header-case',FIRST.replace('obs word','Obs word',1)),('newline',FIRST[:-1])]
        for name,bad in damages:
            reports=deepcopy(truth['reports']);reports['print_01.txt']=bad;cli_check(source,truth,reports,1);controls.append(name)
    else:
        for damage in ('number','character-padding','obs','schema-header','basename','missing-report'):
            reports=deepcopy(truth['reports'])
            if damage=='number':reports['print_01.txt']=FIRST.replace('"B" 9','"B" 8')
            elif damage=='character-padding':reports['print_01.txt']=FIRST.replace('"beta"','"beta "',1)
            elif damage=='obs':reports['print_02.txt']=SECOND.replace('\n1 ','\n9 ',1)
            elif damage=='schema-header':reports['print_01.txt']=FIRST.replace('word code n','code word n')
            elif damage=='basename':reports={'wrong.txt':FIRST,'print_02.txt':SECOND}
            else:del reports['print_02.txt']
            cli_check(source,truth,reports,1);controls.append(damage)
    return controls


def check_original(mode='print'):
    source=ORIGINAL.read_text();truth=original_expected();trace=original_trace()
    assert hashlib.sha256(source.encode()).hexdigest()==SOURCE_PIN
    assert digest(truth)==RESULT_PIN and digest(trace)==TRACE_PIN
    assert [hashlib.sha256(report.encode()).hexdigest() for report in (FIRST,SECOND)]==REPORT_PINS
    witness=program_witness(mode=mode);assert witness is not None
    assert_tree(witness['result'],truth);assert witness['trace']==trace and witness['accounting']==ORIGINAL_ACCOUNT
    actual=execute(source,True);assert_tree(actual['result'],truth);assert actual['trace']==trace and actual['final_title'] is None
    cli_check(source,truth,truth['reports'])
    return witness


def main(mode='print'):
    check_original(mode);hand=hand_cases(mode);generated=generated_cases(mode);cases=hand+generated
    witnesses=batch_witness([source for _,source in cases],mode)
    for (name,source),witness in zip(cases,witnesses,strict=True):
        assert witness is not None,name;actual=execute(source,True);assert_tree(actual['result'],witness['result']);assert actual['trace']==witness['trace'],name
    refused=refusal_cases(mode);witnesses=batch_witness([source for _,source in refused],mode)
    for (name,source),witness in zip(refused,witnesses,strict=True):
        assert witness is None,('R accepted refusal',name)
        try:execute(source)
        except (ValueError,RuntimeError):pass
        else:raise AssertionError(('runtime accepted refusal',name))
    controls=wrong_comparators(mode)
    # A later PRINT cell fails after the first report was buffered.
    late=data_source()+'proc print data=raw;run;'+data_source(['x,A,1.5'],name='late')+'proc print data=late;run;'
    cli_check(late,original_expected(),original_expected()['reports'],1)
    construct='mixed-print' if mode=='print' else 'logical-title'
    print(f'VERIFIED: {construct} {len(hand)} hand cases,{len(generated)} generated source/runtime/emitted/R cases,{len(refused)} shared refusals,{len(controls)} actual CLI wrong-report controls; original16 statements/8rows/47events,164+168 exact report bytes; no live SAS')


if __name__=='__main__':main()
