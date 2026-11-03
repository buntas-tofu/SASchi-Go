#!/usr/bin/env python3
"""Independent original PROC SORT DROP/composition qualification for maintainer review.

Hand/base-R qualification runs before new translator comparisons. No live SAS.
"""
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
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('SASCHI_REPOSITORY_ROOT', str(HERE.parent))).resolve()
sys.path.insert(0, str(ROOT))
ORIGINAL = HERE / 'sort_composition_capture.sas'
SOURCE_PIN = '2bc4863d9ec58f857e1fdaea8b9ac77607e4b9d8d8380113f79acbac7b4ee467'
RESULT_PIN = '126cd829a39de99935cddb91a90ea62fe1c77f6a21409f038a87764893cbdec3'
TRACE_PIN = 'ff83d8627449de93e4f73aee3bc97ff178f89b6457e8db9b02ffd1c234c261a3'
ACCOUNT_KEYS = ('statements', 'physical_records', 'observations', 'attempts', 'outputs')


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()


def exact(actual, expected):
    if type(expected) is dict:
        assert type(actual) is dict and list(actual) == list(expected), (actual, expected)
        for name in expected: exact(actual[name], expected[name])
    elif type(expected) is list:
        assert type(actual) is list and len(actual) == len(expected), (actual, expected)
        for a, b in zip(actual, expected, strict=True): exact(a, b)
    elif type(expected) in (int, float):
        assert type(actual) in (int, float) and actual == expected, (actual, expected)
    else: assert type(actual) is type(expected) and actual == expected, (actual, expected)


def table(columns, values):
    schema = {name: {'type': 'character' if width else 'number', 'length': width or 8} for name, width in columns}
    return {'schema': schema, 'rows': [{name: str(value).ljust(width) if width else None if value is None else float(value)
                                      for (name, width), value in zip(columns, row, strict=True)} for row in values]}


def view(raw, ordinals):
    return {'schema': deepcopy(raw['schema']), 'rows': [deepcopy(raw['rows'][i-1]) for i in ordinals]}


def logical_report(dataset, title):
    lines = [] if title is None else ['TITLE: ' + title]
    lines.append('obs ' + ' '.join(dataset['schema']))
    for i, row in enumerate(dataset['rows'], 1):
        fields = []
        for name, spec in dataset['schema'].items():
            value = row[name]
            if spec['type'] == 'character': fields.append(json.dumps(value.rstrip(' '), ensure_ascii=True))
            else:
                assert value is None or value == int(value)
                fields.append('.' if value is None else str(int(value)))
        lines.append(str(i) + ' ' + ' '.join(fields))
    return '\n'.join(lines) + '\n'


def report_events(title, dataset, name, content, rows):
    records = content.splitlines(); first = 0 if title is None else 1
    events = ['mixed-print|input|' + dataset + '|' + str(rows)]
    if title is not None: events.append('mixed-print|title|' + records[0].encode().hex())
    events.append('mixed-print|header|' + records[first].encode().hex())
    events.extend('mixed-print|row|' + line.encode().hex() for line in records[first+1:])
    events.append('mixed-print|output|' + name + '|' + str(len(content.encode())))
    return events


def input_trace(line, count):
    events = []
    for attempt in range(1, count+2):
        events.append({'kind': 'character_input', 'line': line, 'attempt': attempt, 'complete': attempt <= count})
        if attempt <= count: events.append({'kind': 'character_output', 'line': line, 'observation': attempt})
    return events


COLUMNS=[('zebra',3),('alpha',0),('payload',0),('scrap',2),('echo',2)]
VALUES=[('B',2,10,'X','p'),('A',None,20,'Y','q'),('A',-2,30,'Z','r'),('A',2,40,'U','s'),
        ('A',2,50,'V','t'),('a',-1,60,'W','u'),('',9,70,'M','v'),('B',None,80,'N','w'),
        ('A',2,40,'U','s'),('B',2,90,'P','x'),('',None,100,'Q','y'),('a',-1,110,'R','z')]


def selected(raw,names,ordinals):
    return {'schema':{name:deepcopy(raw['schema'][name]) for name in names},
            'rows':[{name:deepcopy(raw['rows'][i-1][name]) for name in names} for i in ordinals]}


def original_expected():
    raw=table(COLUMNS,VALUES)
    dropped=selected(raw,['zebra','alpha','payload'],[11,7,2,3,4,8,1,6])
    directed=selected(raw,['zebra','alpha','payload','scrap'],[7,11,4,3,2,1,8,6])
    two=selected(raw,['zebra','alpha','payload'],[6,1,8,4,3,2,7,11])
    late=selected(raw,['zebra','alpha','payload'],[11,8,7,6,4,3,2,1])
    legacy_keep=selected(raw,['zebra','payload'],[1,2,3,4,6,7,8,11])
    legacy_plain=selected(raw,['zebra','payload'],[7,11,2,3,4,1,8,6])
    legacy_directed=view(raw,[12,11,10,8,7,6,5,4,9,3,2,1])
    return {'datasets':{'raw':raw,'dropped':dropped,'directed':directed,'two_directions':two,'late':late,
                        'legacy_keep':legacy_keep,'legacy_plain':legacy_plain,'legacy_directed':legacy_directed},'log':[],
            'reports':{'print_01.txt':logical_report(dropped,'Ascending DROP snapshot'),
                       'print_02.txt':logical_report(directed,'Directed KEEP snapshot')}}


def key_specs(names,directions):
    return [{'name':name,'descending':direction} for name,direction in zip(names,directions,strict=True)]


def sort_event(line,src,dest,order,kept,mode=None,names=None,keys=None):
    event={'event':'sort_composition' if mode is not None else 'sort','line':line,'source':src,'destination':dest}
    if mode is not None:event.update(selection={'mode':mode,'names':list(names)},keys=deepcopy(keys))
    event.update(source_ordinals=list(order),kept_ordinals=list(kept));return event


def original_trace():
    events=input_trace(4,12)
    asc=key_specs(['zebra','alpha'],[False,False]);mixed=key_specs(['zebra','alpha'],[False,True])
    desc=key_specs(['zebra','alpha'],[True,True]);late=key_specs(['payload','zebra'],[True,False])
    events.append(sort_event(20,'raw','dropped',[11,7,2,3,4,5,9,8,1,10,6,12],[11,7,2,3,4,8,1,6],
                             'drop',['echo','scrap'],asc))
    reports=original_expected()['reports']
    def report(title,dataset,name):
        events.append('title|set|'+title.encode().hex())
        events.extend(report_events(title,dataset,name,reports[name],8))
    report('Ascending DROP snapshot','dropped','print_01.txt')
    events.append(sort_event(26,'raw','directed',[7,11,4,5,9,3,2,1,10,8,6,12],[7,11,4,3,2,1,8,6],
                             'keep',['payload','alpha','zebra','scrap'],mixed))
    events.append(sort_event(29,'raw','two_directions',[6,12,1,10,8,4,5,9,3,2,7,11],[6,1,8,4,3,2,7,11],
                             'drop',['echo','scrap'],desc))
    report('Directed KEEP snapshot','directed','print_02.txt')
    events.append(sort_event(35,'directed','late',[2,7,1,8,3,4,5,6],[2,7,1,8,3,4,5,6],
                             'drop',['scrap'],late))
    events.append(sort_event(38,'dropped','legacy_keep',[7,3,4,5,8,2,6,1],[7,3,4,5,8,2,6,1]))
    events.append(sort_event(41,'legacy_keep','legacy_plain',[6,8,2,3,4,1,7,5],[6,8,2,3,4,1,7,5]))
    events.append(sort_event(44,'raw','legacy_directed',[12,11,10,8,7,6,5,4,9,3,2,1],[12,11,10,8,7,6,5,4,9,3,2,1]))
    events.append('title|reset');return events


def source(cards,columns='z :$3. n payload q :$2. tail :$2.',mode='drop',names='tail q',keys='z n',nodupkey=True,reports=0):
    text=('data raw;\ninfile datalines dsd;\ninput '+columns+';\ndatalines4;\n'+''.join(card+'\n' for card in cards)+';;;;\nrun;\n'
          +'proc sort data=raw('+mode+'='+names+') out=ordered'+(' nodupkey' if nodupkey else '')+';\nby '+keys+';\nrun;\n')
    for i in range(reports):text+='title "Snapshot '+str(i+1)+'";\nproc print data='+('raw' if i==0 else 'ordered')+';\nrun;\n'
    return text


def hand_case(values,mode,names,keys,nodupkey,reports=0):
    raw=table([('z',3),('n',0),('payload',0),('q',2),('tail',2)],values)
    selected_names=[name for name in raw['schema'] if (name in names)==(mode=='keep')]
    def value_key(row):
        result=[]
        for spec in keys:
            name=spec['name'];descending=spec['descending'];value=row[name]
            if raw['schema'][name]['type']=='character':
                result.append(tuple(-ord(c) if descending else ord(c) for c in value))
            elif descending:result.append((1,0) if value is None else (0,-value))
            else:result.append((0,0) if value is None else (1,value))
        return tuple(result)
    order=sorted(range(1,len(values)+1),key=lambda i:value_key(raw['rows'][i-1]));kept=[];previous=None
    for ordinal in order:
        current=value_key(raw['rows'][ordinal-1])
        if not nodupkey or current!=previous:kept.append(ordinal)
        previous=current
    ordered=selected(raw,selected_names,kept);truth={'datasets':{'raw':raw,'ordered':ordered},'log':[]}
    trace=input_trace(3,len(values));trace.append(sort_event(len(values)+7,'raw','ordered',order,kept,mode,names,keys))
    if reports:
        truth['reports']={}
        for i in range(reports):
            title='Snapshot '+str(i+1);dataset='raw' if i==0 else 'ordered';name='print_%02d.txt'%(i+1);table_value=truth['datasets'][dataset]
            content=logical_report(table_value,title);truth['reports'][name]=content;trace.append('title|set|'+title.encode().hex())
            trace.extend(report_events(title,dataset,name,content,len(table_value['rows'])))
    return {'result':truth,'trace':trace,'accounting':dict(zip(ACCOUNT_KEYS,[8+3*reports,len(values),len(values),len(values)+1,len(values)],strict=True))}


def generated_cases(count=64):
    rng=random.Random(7801);cases=[]
    for i in range(count):
        fractional=i%4==0
        values=[(rng.choice(['','A','B','a','Aa']),rng.choice([None,-2,-.5,0,.5,2] if fractional else [None,-2,0,2]),rng.randrange(5),rng.choice(['X','Y','']),rng.choice(['M','N',''])) for _ in range(rng.randrange(25))]
        names=['tail','q'] if i%2 else ['q','tail'];keys=key_specs(['z','n'] if i%3 else ['n','z'],[False,False]);nodup=i%3!=0;reports=0 if fractional else i%3
        cards=[','.join('.' if value is None else str(value) for value in row) for row in values]
        cases.append((source(cards,names=' '.join(names),keys=' '.join(k['name'] for k in keys),nodupkey=nodup,reports=reports),hand_case(values,'drop',names,keys,nodup,reports)))
    return cases


def boundary_cases():
    full=source([])
    for i in range(62):full+=f'proc sort data=raw(drop=q tail) out=s{i};by z;run;\n'
    return [source([]),source(['A,1,2,X,M']*1000),source(['A,-2147483647,1,X,M','B,2147483647,2,Y,N',',.,3,Z,P']),
            source(['A,.5,1,X,M',',.,2,Y,N','a,-.5,3,Z,P']),
            source(['Z'*64+',1,X'],columns='z :$64. n q :$1.',names='q',keys='z',nodupkey=False),
            source([],columns='z :$1. '+' '.join('n'+str(i) for i in range(31)),names='n30',keys='z'),
            source([],columns='z :$1. '+' '.join('n'+str(i) for i in range(8)),names='n7',keys='z '+' '.join('n'+str(i) for i in range(7))),
            full,source([])+'title "A";\n'*32,source([],reports=2),source(['A,1,2,X,M']).replace('\n','\r\n')]


def refusal_cases():
    base=source([]);result=[]
    for label,names,keys in [('removed-by','n','n'),('unknown-drop','absent','z'),('duplicate-drop','q q','z'),('empty-drop','','z'),
                            ('drop-all','z n payload q tail','z'),('numeric-only','z q tail','n'),('unknown-by','q tail','absent'),
                            ('duplicate-by','q tail','z z'),('special-by','q tail','_all_'),('range-drop','q1-q2','z'),('special-drop','_numeric_','z')]:
        result.append((label,source([],names=names,keys=keys)))
    for label,before,after in [('in-place',' out=ordered',''),('explicit-in-place','out=ordered','out=raw'),
                              ('both-options','drop=tail q','drop=tail keep=z n'),('output-option','out=ordered','out=ordered(keep=z)'),
                              ('dupout',' nodupkey',' dupout=removed nodupkey'),('unknown-option','out=ordered','out=ordered force')]:
        result.append((label,base.replace(before,after)))
    result+=[('excluded-inexact',source(['A,1,0.1,X,M'],names='payload q tail',keys='z')),
             ('excluded-nonascii',source(['A,1,2,é,M'])),('excluded-tagged',source(['A,1,.A,X,M'],names='payload',keys='z')),
             ('empty-invalid-descriptor',source([],columns='z :$3. n payload q :$65. tail :$2.')),
             ('no-run',base.rsplit('run;',1)[0]),('extra-statement',base.replace('by z n;','by z n;where n=1;')),
             ('third-report',source([],reports=2)+'proc print data=raw;run;\n'),('fractional-print',source(['A,.5,2,X,M'],reports=1)),
             ('rows1001',source(['A,1,2,X,M']*1001)),('step65',boundary_cases()[7]+'proc sort data=raw(drop=q) out=excess;by z;run;\n'),
             ('columns33',source([],columns='z :$1. '+' '.join('n'+str(i) for i in range(32)),names='n31',keys='z')),
             ('by9',source([],columns='z :$1. '+' '.join('n'+str(i) for i in range(9)),names='n8',keys='z '+' '.join('n'+str(i) for i in range(8)))),
             ('title33',boundary_cases()[8]+'title "B";\n'),('unsupported-all-join',base+'proc sort data=raw out=allkeys nodupkey;by _all_;run;\n')]
    return result


def family_selection_controls():
    return [('ascending-keep',source([],mode='keep',names='payload n z',keys='z n')),
            ('plain-sort',source([]).replace('(drop=tail q)','')),
            ('comment-decoy','/* proc sort data=raw(drop=n) out=decoy;by z;run; */\n'+source([]).replace('(drop=tail q)','')),
            ('title-decoy',source([],reports=1).replace('(drop=tail q)','').replace('Snapshot 1','DROP=inactive'))]


def batch_witness(sources,r_name='sort_input_drop.R'):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory); paths = []
        for i, text in enumerate(sources):
            path = folder / f'{i}.sas'; path.write_text(text); paths.append(path)
        listing = folder / 'sources.txt'; listing.write_text(''.join(str(path) + '\n' for path in paths))
        rscript = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        run = subprocess.run([rscript, str(HERE / r_name), str(listing)], cwd=ROOT,
                             env={**os.environ, 'SASCHI_EXAMPLES_ROOT': str(ROOT / 'examples')},
                             text=True, capture_output=True, check=True, timeout=120)
    answers = []; active = None; current = None
    for line in run.stdout.splitlines():
        if line.startswith('BEGIN '):
            assert active is None; active = int(line[6:]); refused = False
            result = {'datasets': {}, 'log': []}; trace = []; accounting = None; reports = {}
        elif line == 'REFUSED': refused = True
        elif line == 'OK': pass
        elif line.startswith('TABLE '): current = {'schema': {}, 'rows': []}; result['datasets'][line[6:]] = current
        elif line.startswith('COL '):
            _, name, kind, width = line.split(); current['schema'][name] = {'type': kind, 'length': int(width)}
        elif line.startswith('ROW '):
            fields = [None if item == 'M' else bytes.fromhex(item[2:]).decode('ascii') if item.startswith('C:') else float(item[2:]) for item in line[4:].split('|')]
            current['rows'].append(dict(zip(current['schema'], fields, strict=True)))
        elif line == 'ENDTABLE': current = None
        elif line.startswith('ACCOUNT '): accounting = dict(zip(ACCOUNT_KEYS, map(int, line[8:].split()), strict=True))
        elif line.startswith('REPORT '):
            _, name, body = line.split(); reports[name] = bytes.fromhex(body).decode('ascii')
        elif line.startswith('EVENT '): trace.append(json.loads(line[6:]))
        elif line == 'END':
            assert active == len(answers) + 1
            if reports: result['reports'] = reports
            answers.append(None if refused else {'result': result, 'trace': trace, 'accounting': accounting}); active = None
        else: raise AssertionError((line, run.stderr))
    assert active is None and len(answers) == len(sources)
    return answers


def qualify_anchor(witness=batch_witness):
    text=ORIGINAL.read_text();truth=original_expected();trace=original_trace()
    if SOURCE_PIN:assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==SOURCE_PIN
    if RESULT_PIN:assert digest(truth)==RESULT_PIN
    if TRACE_PIN:assert digest(trace)==TRACE_PIN
    assert not any(name=='saschi' or name.startswith('saschi.') or name=='sas_semantics' for name in sys.modules)
    answer=witness([text])[0];exact(answer['result'],truth);exact(answer['trace'],trace)
    exact(answer['accounting'],dict(zip(ACCOUNT_KEYS,[33,12,12,13,12],strict=True)))
    assert len(trace)==59
    return {'original':text,'truth':truth,'trace':trace,'anchor':answer}


def qualify():
    q=qualify_anchor();generated=generated_cases();boundaries=boundary_cases();refused=refusal_cases();selection=family_selection_controls()
    answers=batch_witness([text for text,_ in generated]+boundaries+[text for _,text in refused]+[text for _,text in selection])
    for (_,expected),answer in zip(generated,answers[:len(generated)],strict=True):exact(answer,expected)
    assert all(answer is not None for answer in answers[len(generated):len(generated)+len(boundaries)])
    start=len(generated)+len(boundaries)
    for (label,_),answer in zip(refused,answers[start:start+len(refused)],strict=True):assert answer is None,label
    for (label,_),answer in zip(selection,answers[start+len(refused):],strict=True):assert answer is None,label
    return {**q,'generated':generated,'boundaries':boundaries,'refused':refused,'selection':selection,'independent':answers}


def qualification_record(q):
    return {'status':'Independent original complete-source hand/base-R expectation qualification for maintainer review. No new runtime or translator imports/comparisons, release acceptance or native SAS claim.',
            'passed':True,'construct':'DS-078 literal input DROP','original_language_statements':33,'original_opaque_payloads':1,'original_physical_rows':12,'original_input_attempts':13,
            'original_outputs':12,'original_steps':13,'original_full_runtime_trace_events':59,'generated_programs':len(q['generated']),
            'positive_boundaries':len(q['boundaries']),'source_refusals':len(q['refused']),'outside_new_family_controls':len(q['selection']),
            'complete_original_result_trace_accounting_equal':True,'complete_generated_result_trace_accounting_equal':True,
            'new_translator_imports':0,'new_translator_comparisons':0,'result_policy_sha256':digest(q['truth']),'trace_policy_sha256':digest(q['trace']),
            'reports':[{'name':name,'bytes':len(body.encode()),'sha256':hashlib.sha256(body.encode()).hexdigest()} for name,body in q['truth']['reports'].items()]}


def execute(text):
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    from saschi.emit_py import translate
    from saschi.sort_composition import run_program
    plan = compile_plan(text);assert not plan.blocked, plan.tickets
    portable=plan.to_dict();before=deepcopy(portable);trace=[]
    result=run_plan(portable);exact(portable,before)
    exact(run_program(portable,trace=trace),result);exact(portable,before)
    namespace={};output=io.StringIO()
    with contextlib.redirect_stdout(output):exec(translate(text).code,namespace)
    exact(namespace['result'],result);assert output.getvalue()==''
    return result,trace


def check_refused(label,text):
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    plan=compile_plan(text)
    if not plan.blocked:
        try:run_plan(plan.to_dict())
        except (ValueError,TypeError,KeyError,RecursionError):pass
        else:raise AssertionError(label)


def check_old_selection(label,text):
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    plan=compile_plan(text);assert not plan.blocked,(label,plan.tickets)
    assert not any(step.kind in ('composed_sort',) for step in plan.steps),label
    assert run_plan(plan.to_dict()) is not None


def cli_check(text,truth,wrong=False):
    from saschi.cli import main
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);src=folder/'input.sas';src.write_text(text)
        expected=folder/'expected.json';expected.write_text(json.dumps(truth['datasets']))
        reports=folder/'reports.json';reports.write_text(json.dumps(truth.get('reports',{})))
        output=folder/'job';console=io.StringIO()
        argv=['run',str(src),'--expect',str(expected),'--output',str(output)]
        if 'reports' in truth:argv+=['--expect-reports',str(reports)]
        with contextlib.redirect_stdout(console):code=main(argv)
        receipt=json.loads((output/'receipt.json').read_text())
        assert code==(1 if wrong else 0),(code,receipt.get('error'))
        assert receipt['accepted'] is (not wrong)
        assert receipt['source_sha256']==hashlib.sha256(src.read_bytes()).hexdigest()
        assert not (output/'exports').exists()
        if wrong:
            assert not (output/'result.json').exists() and (output/'observed.json').is_file()
            assert not (output/'reports').exists()
        else:
            exact(json.loads((output/'result.json').read_text()),truth)
            if 'reports' in truth:
                assert receipt['report_contract']=='ascii-titled-mixed-integer-v1'
                assert sorted(path.name for path in (output/'reports').iterdir())==sorted(truth['reports'])
                for name,body in truth['reports'].items():assert (output/'reports'/name).read_bytes()==body.encode()
        assert not list(folder.glob('.job.*'))
    return receipt


def cli_source_refusal(text):
    from saschi.cli import main
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);src=folder/'refused.sas';src.write_text(text);output=folder/'job'
        with contextlib.redirect_stdout(io.StringIO()):code=main(['run',str(src),'--output',str(output)])
        receipt=json.loads((output/'receipt.json').read_text())
        assert code in (1,2) and receipt['accepted'] is False
        assert not any((output/name).exists() for name in ('result.json','observed.json','reports','exports'))
        assert not list(folder.glob('.job.*'))
    return 1


# Post-freeze adapters only. Every qualified oracle function above is unchanged.
def wrong_drop_cases(truth):
    answers=[]
    for mode in ('ignored-drop','last-survivor','descriptor-order','padding','changed-value','raw-mutated','lost-multiplicity'):
        wrong=deepcopy(truth);tables=wrong['datasets'];dropped=tables['dropped']
        if mode=='ignored-drop':
            for name in ('scrap','echo'):
                dropped['schema'][name]=deepcopy(tables['raw']['schema'][name])
                for row in dropped['rows']:row[name]='X '
        elif mode=='last-survivor':dropped['rows'][4]['payload']=50.
        elif mode=='descriptor-order':dropped['schema']=dict(reversed(list(dropped['schema'].items())))
        elif mode=='padding':dropped['rows'][0]['zebra']=''
        elif mode=='changed-value':dropped['rows'][0]['payload']=-999.
        elif mode=='raw-mutated':tables['raw']['rows'].pop()
        else:tables['legacy_directed']['rows'].pop(8)
        answers.append((mode,wrong))
    return answers


def comparator_refuses(actual,wrong):
    try:exact(actual,wrong)
    except AssertionError:return
    raise AssertionError('known-wrong complete comparator admitted')


def trace_controls(trace,directed=False):
    answers=[]
    modes=('selection-order','selection-mode','key-direction','sorted-identity','equal-row-survivor','missing-event','legacy-event')
    for mode in modes:
        wrong=deepcopy(trace)
        target=next(event for event in wrong if type(event) is dict and event.get('event')=='sort_composition'
                    and (not directed or event['destination']=='directed'))
        if mode=='selection-order':target['selection']['names'].reverse()
        elif mode=='selection-mode':target['selection']['mode']='keep' if target['selection']['mode']=='drop' else 'drop'
        elif mode=='key-direction':target['keys'][-1]['descending']=not target['keys'][-1]['descending']
        elif mode=='sorted-identity':target['source_ordinals'][0]=999
        elif mode=='equal-row-survivor':target['kept_ordinals']=[9 if value==4 else value for value in target['kept_ordinals']]
        elif mode=='missing-event':wrong.remove(target)
        else:next(event for event in wrong if type(event) is dict and event.get('event')=='sort')['destination']='wrong'
        comparator_refuses(trace,wrong);answers.append(wrong)
    return len(answers)


def portable_refusals():
    from saschi.plan import compile_plan
    from saschi.sort_composition import execute_sort,run_program,validate_step
    plan=compile_plan(source([])).to_dict();step=next(item for item in plan['steps'] if item['kind']=='composed_sort')
    empty=table([('z',3),('n',0),('payload',0),('q',2),('tail',2)],[]);count=0
    def rejected(changed=step,table_value=empty,version=2):
        nonlocal count
        before=json.dumps(table_value,separators=(',',':'))
        try:execute_sort(changed,{'raw':table_value},version=version)
        except (ValueError,TypeError,KeyError,RecursionError):pass
        else:raise AssertionError('malformed composed_sort admitted')
        assert json.dumps(table_value,separators=(',',':'))==before;count+=1
    for name,value in [('by',['z']),('nodupkey',True),('line',True),('inputs',[]),('name','raw'),('extra',1),('where',True)]:
        changed=deepcopy(step);changed[name]=value;rejected(changed)
    for name,value in [('selection',{'mode':'drop','names':[]}),('selection',{'mode':'drop','names':['q','q']}),
                       ('selection',{'mode':'drop','names':['absent']}),('selection',{'mode':'drop','names':['z','q','tail']}),
                       ('selection',{'mode':'drop','names':['z','n','payload','q','tail']}),
                       ('selection',{'mode':'keep','names':['z','n']}),('selection',{'mode':'DROP','names':['q']}),
                       ('selection',{'mode':'drop','names':('q',)}),('selection',{'mode':'drop','names':['q'],'extra':1}),
                       ('keys',[]),('keys',[{'name':'z','descending':0}]),('keys',[{'name':'z','descending':False,'extra':1}]),
                       ('keys',[{'name':'q','descending':False}]),('keys',[{'name':'z','descending':False}]*2),
                       ('nodupkey',1),('source_lines',[]),('source_lines',[True,3]),('profile','sort-input-keep-v1'),('extra',1)]:
        changed=deepcopy(step);changed['operations'][0]['args'][name]=value;rejected(changed)
    for name in ('profile','selection','keys','nodupkey','source_lines'):
        changed=deepcopy(step);del changed['operations'][0]['args'][name];rejected(changed)
    rejected(version=True)
    for value in (True,float('nan'),'.A',2147483648,.1):
        changed=deepcopy(empty);changed['rows']=[{'z':'A  ','n':1.,'payload':value,'q':'X ','tail':'M '}]
        modified=deepcopy(step);modified['operations'][0]['args']['selection']['names']=['payload','q','tail'];modified['operations'][0]['args']['keys']=[{'name':'z','descending':False}]
        rejected(modified,changed)
    changed=deepcopy(empty);changed['schema']['q']['length']=True;rejected(table_value=changed)
    changed=deepcopy(empty);changed['rows']=[{'z':'A  ','n':1.,'payload':2.,'q':'é ','tail':'M '}];rejected(table_value=changed)
    changed=deepcopy(step);changed['operations'][0]['args']['selection']['names'].append(changed);rejected(changed)
    for location in ('matched','producer','catalog'):
        changed=deepcopy(plan);catalog=None
        if location=='matched':changed['matched'].append({'profile':'sort-projection-composition-v1'})
        elif location=='producer':changed['steps'][0]['operations'][0]['args']['hidden']={'kind':'composed_sort'}
        else:catalog={'external':empty}
        try:run_program(changed,catalog)
        except (ValueError,TypeError,KeyError,RecursionError):count+=1
        else:raise AssertionError('hidden marker or supplied catalog admitted')
    # Returned args, table and trace data are independent copies.
    before=deepcopy(step);args=validate_step(step);args['selection']['names'].append('absent');exact(step,before)
    input_table=table([('z',3),('n',0),('payload',0),('q',2),('tail',2)],[('A',1,2,'X','M')]);prior=deepcopy(input_table);events=[]
    answer=execute_sort(step,{'raw':input_table},trace=events);answer['rows'][0]['z']='changed';events[0]['selection']['names'].append('absent')
    exact(input_table,prior);exact(step,before)
    return count


def preflight_and_once(text):
    from collections import Counter
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    from saschi import sort_composition,sort_options,sort_projection
    plan=compile_plan(text).to_dict();calls=[];real=sort_composition.execute_sort
    def forbidden(*args,**kwargs):raise AssertionError('preflight executed SORT')
    with patch.object(sort_composition,'execute_sort',forbidden),patch.object(sort_options,'execute_sort',forbidden),patch.object(sort_projection,'execute_sort',forbidden):
        sort_composition.validate_program(plan)
    def counted(*args,**kwargs):
        result=real(*args,**kwargs);calls.append((args[0]['kind'],args[0]['name']));return result
    with patch.object(sort_composition,'execute_sort',counted):run_plan(plan)
    assert [name for _,name in calls]==['dropped','directed','two_directions','late','legacy_keep','legacy_plain','legacy_directed'],calls
    assert Counter(kind for kind,_ in calls)=={'composed_sort':4,'projected_sort':1,'sort':1,'bounded_sort':1},calls
    return {'composed':4,'ascending_KEEP':1,'plain':1,'directed':1}


def atomic_check(text,target):
    from saschi import sort_composition,mixed_reports
    from saschi.cli import main
    real=sort_composition.execute_sort;renderer=mixed_reports.execute_print;calls=[];reports=[]
    def later(*args,**kwargs):
        answer=real(*args,**kwargs);calls.append(args[0]['name'])
        if args[0]['name']==target:raise ValueError('composition late SORT fault at '+target)
        return answer
    def printed(*args,**kwargs):
        answer=renderer(*args,**kwargs);reports.append(deepcopy(answer));return answer
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);path=folder/'original.sas';path.write_text(text);output=folder/'job'
        with patch.object(sort_composition,'execute_sort',later),patch.object(mixed_reports,'execute_print',printed),contextlib.redirect_stdout(io.StringIO()):
            code=main(['run',str(path),'--output',str(output)])
        receipt=json.loads((output/'receipt.json').read_text())
        assert code==1 and receipt['accepted'] is False and receipt['error']=='composition late SORT fault at '+target,receipt
        assert len(reports)==2 and all(reports) and calls[-1]==target
        assert len(calls)==(4 if target=='late' else 7)
        assert not any((output/name).exists() for name in ('result.json','observed.json','reports','exports'))
        assert not list(folder.glob('.job.*'))
    return 1





# Complete post-freeze adapters. Frozen hand/R qualification functions stay exact.
def runtime_accounting(text,events):
    from saschi.parser import split_statements,Kind
    from saschi.plan import compile_plan
    statements=split_statements(text)
    producers=[step for step in compile_plan(text).to_dict()['steps'] if step['kind']=='character_data']
    attempts=[event for event in events if type(event) is dict and event.get('kind')=='character_input']
    outputs=[event for event in events if type(event) is dict and event.get('kind')=='character_output']
    return dict(zip(ACCOUNT_KEYS,[sum(not any(token.kind is Kind.DATA for token in item.tokens) for item in statements),
        sum(len(step['operations'][0]['args']['records']) for step in producers),len(outputs),len(attempts),len(outputs)],strict=True))


def runtime_case(text,witness):
    result,events=execute(text)
    exact(result,witness['result']);exact(events,witness['trace'])
    exact(runtime_accounting(text,events),witness['accounting'])
    return result,events


def wrong_reports(truth,directed=False):
    target='print_02.txt' if directed else 'print_01.txt';cases=[]
    for label,transform in [('missing-final-LF',lambda text:text.rstrip('\n')),
                            ('missing-TITLE',lambda text:text.split('\n',1)[1]),
                            ('wrong-observation',lambda text:text.replace('\n1 ','\n99 ',1)),
                            ('wrong-header',lambda text:text.replace('obs zebra alpha payload','obs payload alpha zebra',1))]:
        wrong=deepcopy(truth);wrong['reports'][target]=transform(wrong['reports'][target]);cases.append((label,wrong))
    wrong=deepcopy(truth);wrong['reports']['print_01.txt']=wrong['reports']['print_02.txt'];cases.append(('earlier-snapshot-replaced',wrong))
    wrong=deepcopy(truth);wrong['reports'].pop('print_02.txt');cases.append(('missing-report',wrong))
    return cases


def genuine_late_renderer_atomic():
    from saschi import sort_composition,mixed_reports
    from saschi.plan import compile_plan
    from saschi.cli import main
    text=('data raw;infile datalines dsd;input z :$3. n payload q :$2. tail :$2.;datalines4;\n'
          'A,.5,1,X,M\nB,1,2,Y,N\n;;;;\nrun;\n'
          'proc sort data=raw(keep=payload z) out=first;by descending payload;run;\n'
          'proc print data=first;run;\n'
          'proc sort data=raw(drop=q tail) out=second;by descending n;run;\n'
          'proc print data=second;run;\n')
    assert not compile_plan(text).blocked
    execute_sort=sort_composition.execute_sort;execute_print=mixed_reports.execute_print;sorts=[];reports=[]
    def sorted_once(*args,**kwargs):
        value=execute_sort(*args,**kwargs);sorts.append(args[0]['name']);return value
    def printed(*args,**kwargs):
        value=execute_print(*args,**kwargs);reports.append(list(value));return value
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);path=folder/'late.sas';path.write_text(text);output=folder/'job'
        with patch.object(sort_composition,'execute_sort',sorted_once),patch.object(mixed_reports,'execute_print',printed),contextlib.redirect_stdout(io.StringIO()):
            code=main(['run',str(path),'--output',str(output)])
        receipt=json.loads((output/'receipt.json').read_text())
        assert code==1 and receipt['accepted'] is False
        assert sorts==['first','second'] and reports==[['print_01.txt']],(sorts,reports)
        assert not any((output/name).exists() for name in ('result.json','observed.json','reports','exports'))
        assert not list(folder.glob('.job.*'))
    return 1


def finish_runtime_gate(qualified,construct,wrong_builder,*,directed=False):
    # qualify() runs first, while no translator/semantics module is imported.
    # Its R and hand source/results/accounting/trace are immutable expectations.
    q=qualified();actual,events=runtime_case(q['original'],q['anchor'])
    exact(actual,q['truth']);exact(events,q['trace'])
    generated=0
    for text,expected in q['generated']:
        runtime_case(text,expected);generated+=1
    boundaries=0;start=len(q['generated'])
    for text,witness in zip(q['boundaries'],q['independent'][start:start+len(q['boundaries'])],strict=True):
        runtime_case(text,witness);boundaries+=1
    refused=0
    for label,text in q['refused']:check_refused(label,text);refused+=1
    selections=0
    for label,text in q['selection']:check_old_selection(label,text);selections+=1
    accepted_cli=cli_check(q['original'],q['truth'])
    # Original source has33 code statements and1opaque card block. The one
    # historical plain SORT keeps its header-only route; its BY/RUN remain
    # unrouted, alongside the opaque block, under the unchanged census policy.
    complete=accepted_cli['completeness']
    assert [complete[name] for name in ('n_statements','n_routed','n_unrouted','n_functions','n_tickets')]==[34,31,3,0,0],complete
    wrong_data=wrong_builder(q['truth']);dataset_controls=0
    for _,incorrect in wrong_data:
        comparator_refuses(actual,incorrect);receipt=cli_check(q['original'],incorrect,True)
        assert receipt['comparison']=='failed';dataset_controls+=1
    report_controls=0
    for _,incorrect in wrong_reports(q['truth'],directed):
        comparator_refuses(actual,incorrect);receipt=cli_check(q['original'],incorrect,True)
        assert receipt['report_comparison']=='failed';report_controls+=1
    summary={'construct':construct,'original_statements':q['anchor']['accounting']['statements'],
        'original_rows':q['anchor']['accounting']['physical_records'],'INPUT_attempts':q['anchor']['accounting']['attempts'],
        'full_runtime_events':len(events),'generated':generated,'positive_boundaries':boundaries,
        'source_refusals':refused,'old_family_controls':selections,'portable_refusals':portable_refusals(),
        'wrong_actual_cli_datasets':dataset_controls,'wrong_actual_cli_reports':report_controls,
        'wrong_full_trace_controls':trace_controls(events,directed),
        'actual_source_negative_cli':cli_source_refusal(next(text for label,text in q['refused'] if 'removed-by' in label)),
        'actual_SORT_executions':preflight_and_once(q['original']),
        'late_actual_cli_faults':{'post_sort_after_two_reports':atomic_check(q['original'],'legacy_directed' if directed else 'late'),
                                 'genuine_second_renderer':genuine_late_renderer_atomic()},
        'actual_source_completeness':{key:complete[key] for key in ('n_statements','n_routed','n_unrouted','n_functions','n_tickets')},
        'runtime_accounting_comparisons':1+generated+boundaries,
        'qualification':'Repository hand/base-R policy; strict full trace comparisons are separate from CLI dataset/report comparisons. No native SAS or physical-layout claim.'}
    print(construct+': '+json.dumps(summary,sort_keys=True));return summary


if __name__=='__main__':finish_runtime_gate(qualify,'sort-input-drop',wrong_drop_cases)
