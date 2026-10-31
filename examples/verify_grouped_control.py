#!/usr/bin/env python3
"""Independent grouped-control source, state, event and CLI evidence."""
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
from examples.verify_numeric_rows import catalog_files as prior_catalog_files,decode_program
from saschi.compare import equal

def assert_tree(actual,expected):
    assert equal(actual,expected,ordered_maps=True),(actual,expected)

def assert_trace(actual,expected):
    assert isinstance(actual,list) and isinstance(expected,list) and actual==expected,(actual,expected)
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.emit_py import translate
from saschi.grouped_control import execute_step,PROFILE
from saschi.values import normalize_catalog

ORIGINAL=HERE/'grouped_control_capture.sas'
SOURCE_PIN='a4355e2c445c3626d1b4c00dae698bfe6c896f54ccd47cc70aea58c48c2b08eb'
RESULT_PIN='7f456b0d33b1a0866fb112b1e5c13a5b6b923fd8c2a66817465f4f4c1a3745ba'
STDOUT_PIN='3ff580a2f4bc01b60f96a822e39b8c0a4095d11c64d9a699411988da119e28e4'
TRACE_PIN='5a7240539b5a57cbb3ca3615b94b9d378d17accf8069c6df24ac99db9a5da971'


def catalog_files(folder,catalog):
    """Transport raw catalog types/order to base R without runtime normalization."""
    folder.mkdir(parents=True,exist_ok=True)
    def kind(value):
        return ('missing' if value is None else 'boolean' if isinstance(value,bool) else
                'integer' if type(value) is int else 'number' if type(value) is float else
                'string' if isinstance(value,str) else 'object' if isinstance(value,dict) else 'other')
    table_fields=['table','table_kind','row_count','table_keys','encoding','encoding_kind','dataset_label','dataset_label_kind']
    descriptor_fields=['table','name','name_kind','type','type_kind','keys','length','length_kind','label','label_kind','format','format_kind']
    value_fields=['table','row','name','name_kind','kind','value']
    tables=[];descriptors=[];values=[];invalid=False
    if not isinstance(catalog,dict):invalid=True
    else:
        for table_name,table in catalog.items():
            if not isinstance(table,dict) or not isinstance(table.get('schema'),dict) or not isinstance(table.get('rows'),list):invalid=True;continue
            label=table.get('label');encoding=table.get('encoding')
            tables.append([table_name,kind(table_name),len(table['rows']),'|'.join(map(str,table)),encoding if 'encoding' in table else '-',kind(encoding) if 'encoding' in table else '-',label.encode().hex() if isinstance(label,str) else '-',kind(label) if 'label' in table else '-'])
            for name,spec in table['schema'].items():
                typed=isinstance(spec,dict);typ=spec.get('type') if typed else spec
                fields=[table_name,name,kind(name),'typed-number' if typed and typ=='number' else typ,kind(typ),'|'.join(map(str,spec)) if typed else '-']
                for field in ('length','label','format'):
                    present=typed and field in spec;value=spec.get(field) if typed else None
                    fields.extend([value.encode().hex() if field!='length' and isinstance(value,str) else value if present else '-',kind(value) if present else '-'])
                descriptors.append(fields)
            for index,row in enumerate(table['rows'],1):
                if not isinstance(row,dict):invalid=True;continue
                for name,value in row.items():
                    tag=isinstance(value,dict) and set(value)=={'missing'} and isinstance(value['missing'],str)
                    typ=('tagged' if tag else 'missing' if value is None else 'boolean' if isinstance(value,bool) else 'number' if type(value) in (int,float) else 'character' if isinstance(value,str) else 'other')
                    values.append([table_name,index,name,kind(name),typ,value['missing'] if tag else value])
    for filename,header,rows in [('tables.csv',table_fields,tables),('descriptors.csv',descriptor_fields,descriptors),('values.csv',value_fields,values)]:
        with (folder/filename).open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(header);writer.writerows(rows)
    if invalid:(folder/'invalid.flag').write_text('unsupported transport shape')


def batch_witness(cases):
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory)
        with (folder/'cases.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['source','catalog'])
            for i,case in enumerate(cases):
                source,catalog=(case['source'],case.get('catalog',{})) if isinstance(case,dict) else case
                (folder/f'{i}.sas').write_text(source);catalog_files(folder/f'cat{i}',catalog);writer.writerow([f'{i}.sas',f'cat{i}'])
        r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        process=subprocess.run([r,str(HERE/'grouped_control.R'),'batch',str(folder)],capture_output=True,text=True,check=True,timeout=120)
    results=[];current=[];trace=[];reason=''
    for line in process.stdout.splitlines():
        if line.startswith('CASE:'):current=[];trace=[];reason=''
        elif line.startswith('TRACE:'):trace.append(bytes.fromhex(line[6:]).decode())
        elif line.startswith('REASON:'):reason=line[7:]
        elif line.startswith('ANSWER:'):
            if line=='ANSWER:REFUSE':results.append(None)
            else:
                clean=[];rows={};table=None;table_keys={};column_keys={};row_keys=None
                for record in current:
                    if record.startswith('TABLE:'):table=record[6:];rows[table]=[];column_keys[table]={};row_keys=None
                    if record.startswith('TABLEKEYS:'):table_keys[table]=record[10:].split('|')
                    elif record.startswith('COLUMNKEYS:'):
                        key,*fields=record[11:].split('|');column_keys[table][key]=fields
                    elif record.startswith('ROWKEYS:'):row_keys=record[8:].split('|') if record[8:] else []
                    elif record.startswith('ROW:'):
                        cells=record[4:].split(',') if record[4:] else []
                        values=[None if cell=='M' else bytes.fromhex(cell[1:]).decode() if cell.startswith('C') else
                                {'missing':cell[1:]} if cell.startswith('T') else float(cell[1:]) for cell in cells]
                        rows[table].append((row_keys,values))
                    else:clean.append(record)
                result,accounting=decode_program(clean)
                for name,values in rows.items():
                    table=result['datasets'][name]
                    table['rows']=[dict(zip(keys if keys is not None else table['schema'],row)) for keys,row in values]
                    for column,keys in column_keys[name].items():table['schema'][column]={key:table['schema'][column][key] for key in keys}
                    if name in table_keys:result['datasets'][name]={key:table[key] for key in table_keys[name]}
                results.append({'result':result,'accounting':accounting,'trace':trace})
        else:current.append(line)
    assert len(results)==len(cases),(process.stdout,process.stderr)
    return results


def execute(source,catalog=None,emitted=False):
    parsed=compile_plan(source);assert not parsed.blocked,parsed.tickets
    supplied={} if catalog is None else deepcopy(catalog);saved=deepcopy(supplied);plan=parsed.to_dict();before=deepcopy(plan)
    result=run_plan(plan,supplied);assert_tree(plan,before);assert_tree(supplied,saved)
    trace=[];tables=normalize_catalog(supplied);logs=[]
    for step in plan['steps']:
        if step['kind']!='control_data':raise ValueError('trace witness expects new control steps only')
        table,records=execute_step(step,tables,plan['version'],trace)
        if table is not None:tables[step['name']]=table
        logs.extend(records)
    assert_tree({'datasets':tables,'log':logs},result)
    if emitted:
        namespace={'inputs':deepcopy(supplied)};stream=io.StringIO()
        with contextlib.redirect_stdout(stream):exec(translate(source).code,namespace)
        assert_tree(namespace['result'],result);assert stream.getvalue()==logical_stdout(result)
    return {'result':result,'trace':trace}


def logical_stdout(result):return ''.join(line+'\n' for line in result['log'])


def original_expected():
    seed={'schema':dict.fromkeys(('key','x','total'),'number'),'rows':[{'key':1.,'x':2.,'total':10.},{'key':2.,'x':None,'total':None},{'key':3.,'x':4.,'total':20.}]}
    schema=dict.fromkeys(('accumulated','key','total','phase','i','scratch','j'),'number')
    values=[(0,1,12,0,1,12,None),(15,1,15,1,4,12,2),(16,2,1,1,1,None,2),(16,3,24,0,1,24,None),(45,3,29,1,4,24,2)]
    measured={'schema':schema,'rows':[dict(zip(schema,[None if v is None else float(v) for v in row])) for row in values]}
    fresh={'schema':{'answer':'number','idx':'number'},'rows':[{'answer':4.,'idx':0.}]}
    return {'datasets':{'seed':seed,'measured':measured,'fresh':fresh},'log':['1 15 15 4 2 ','2 1 16 1 2 ','3 29 45 4 2 ','4 0 ']}


def original_trace():
    """Hand-authored event schedule, independent of either parser/runtime."""
    out=['row|1','group|enter']
    for key,x,total in ((1,'2','10'),(2,'.','.'),(3,'4','20')):
        out.extend([f'assign|key|{key}',f'assign|x|{x}',f'assign|total|{total}',f'output|key={key};x={x};total={total}'])
    out.append('group|exit')
    for row,key,initial_acc,early_total,late_total,final_acc in ((1,1,0,12,15,15),(2,2,15,None,1,16),(3,3,16,24,29,45)):
        out.extend([f'row|{row}','assign|phase|0','capture|i|1|3|1|3'])
        for i in (1,) if key==2 else (1,2,3):
            out.extend([f'iteration|counted|i|{i}','group|enter',f'if|{int(i==2)}'])
            if i==2:out.extend(['transfer|continue','group|exit',f'increment|i|{i+1}']);continue
            total=0 if key==2 else early_total if i==1 else late_total-1
            out.extend([f'sum|total|{total}',f'if|{int(key==2)}'])
            if key==2:out.extend(['transfer|leave','group|exit']);break
            out.append(f'if|{int(i==1)}')
            if i==1:out.extend(['group|enter',f'assign|scratch|{early_total}',f'output|accumulated={initial_acc};key={key};total={early_total};phase=0;i=1;scratch={early_total};j=.','group|exit'])
            out.extend(['group|exit',f'increment|i|{i+1}'])
        out.extend(['loop|exit|counted','assign|phase|1','assign|j|0','iteration|until|1','group|enter','assign|j|1','if|1','transfer|continue','group|exit','test|until|0','iteration|until|2','group|enter','assign|j|2','if|0',f'sum|total|{late_total}','group|exit','test|until|1','loop|exit|until',f'sum|accumulated|{final_acc}'])
        final_i=1 if key==2 else 4;scratch='.' if key==2 else str(early_total)
        out.append(f'output|accumulated={final_acc};key={key};total={late_total};phase=1;i={final_i};scratch={scratch};j=2')
        out.append('put|'+f'{key} {late_total} {final_acc} {final_i} 2 '.encode().hex())
    out.extend(['row|1','assign|answer|0','capture|idx|3|1|-1|3'])
    for idx,total in ((3,3),(2,None),(1,4)):
        out.extend([f'iteration|counted|idx|{idx}','group|enter',f'if|{int(idx==2)}'])
        out.append('transfer|continue' if idx==2 else f'sum|answer|{total}')
        out.extend(['group|exit',f'increment|idx|{idx-1}'])
    out.extend(['loop|exit|counted','group|enter','output|answer=4;idx=0','group|exit','put|34203020'])
    return out


def case(name,source,expected=None,catalog=None,trace=None):
    return {'name':name,'source':source,'catalog':{} if catalog is None else catalog,'expected':expected,'trace':trace}


def simple(names,rows,logs=()):
    return {'datasets':{'d':{'schema':dict.fromkeys(names.split(),'number'),'rows':[dict(zip(names.split(),values)) for values in rows]}},'log':list(logs)}


def supplied(rows=True):
    return {'raw':{'encoding':'ascii','label':'source',
        'schema':{'key':{'type':'number','length':8,'label':'id','format':''},'x':'number','total':'number','other':{'type':'character','length':4}},
        'rows':[{'key':1.,'x':2.,'total':10.,'other':'AB  '},{'key':2.,'x':None,'total':None,'other':'CD  '}] if rows else []}}


def hand_cases(mode='group'):
    if mode=='group':
        meta=supplied();selected={'saved':'number','key':deepcopy(meta['raw']['schema']['key']),'total':'number'}
        source='data d(keep=key total saved);retain saved 0;set raw(drop=other);do;if key=1 then scratch=x;total+x;saved+total;output;put key total saved;end;run;'
        expected={'datasets':{**deepcopy(meta),'d':{'encoding':'ascii','label':'source','schema':selected,'rows':[{'saved':12.,'key':1.,'total':12.},{'saved':12.,'key':2.,'total':0.}]}},'log':['1 12 12 ','2 0 12 ']}
        empty=supplied(False);empty_expected={'datasets':{**deepcopy(empty),'d':{'encoding':'ascii','label':'source','schema':selected,'rows':[]}},'log':[]}
        return [
          case('group_once','data d;x=1;do;x=x+1;do;x=x*2;end;end;run;',simple('x',[(4.,)])),
          case('nearest_else','data d;x=0;if 1 then do;if 0 then do;x=1;end;else do;x=2;end;end;else do;x=3;end;run;',simple('x',[(2.,)])),
          case('dead_OUTPUT','data d;x=1;if 0 then do;future=2;output;end;run;',simple('x future',[])),
          case('snapshots','data d;x=1;do;if 0 then future=9;output;x=2;output;end;put x;run;',simple('x future',[(1.,None),(2.,None)],['2 '])),
          case('subset','data d;x=1;do;if 0;x=2;end;run;',simple('x',[])),
          case('null_named','data _null_;x=1;if 0 then do;x=2;end;put x=;run;',{'datasets':{},'log':['x=1']}),
          case('selected_input',source,expected,meta),
          case('empty_input',source,empty_expected,empty),
          case('literal_words','data d;x=1;do;put "do; leave; continue;" " A  B ";end;run;',simple('x',[(1.,)],['do; leave; continue; A  B '])),
          case('loop_in_group','data d;x=0;if 1 then do;do i=1 to 2;x+i;end;end;run;',simple('x i',[(3.,3.)])),
          case('missing_truth','data d;x=.;if x then do;y=1;end;else do;y=2;end;run;',simple('x y',[(None,2.)]))]
    return [
      case('original',ORIGINAL.read_text(),original_expected(),trace=original_trace()),
      case('counted_leave','data d;x=0;do i=3 to 1 by -1;do;if i=2 then leave;x+i;end;end;run;',simple('x i',[(3.,2.)])),
      case('counted_continue','data d;x=0;do i=3 to 1 by -1;if i=2 then continue;x+i;end;run;',simple('x i',[(4.,0.)])),
      case('nearest_inner_leave','data d;x=0;do i=1 to 2;do j=1 to 3;if j=2 then do;leave;end;end;x+1;end;run;',simple('x i j',[(2.,3.,2.)])),
      case('nearest_inner_continue','data d;x=0;y=0;do i=1 to 2;do j=1 to 3;if j=2 then continue;x+1;end;y+10;end;run;',simple('x y i j',[(4.,20.,3.,4.)])),
      case('while_continue','data d;n=0;x=0;do while(n<3);do;n=n+1;if n<3 then continue;x=x+10;end;end;run;',simple('n x',[(3.,10.)])),
      case('until_continue_bottom','data d;n=0;do until(n>=1);do;n=n+1;if n=1 then continue;n=99;end;end;run;',simple('n',[(1.,)])),
      case('leave_bypasses_test','data d;n=2147483647;do until(n+1>0);leave;end;run;',simple('n',[(2147483647.,)])),
      case('leave_bypasses_increment','data d;do i=2147483647 to 2147483647 by 2147483647;leave;end;run;',simple('i',[(2147483647.,)])),
      case('dead_dynamic_overflow','data d;x=2147483647;do i=1 to 1;continue;x=x+1;end;run;',simple('x i',[(2147483647.,2.)])),
      case('unreachable_OUTPUT','data d;x=1;do i=1 to 1;leave;output;end;run;',simple('x i',[])),
      case('zero_trip_owned','data d;x=1;do while(0);continue;end;run;',simple('x',[(1.,)]))]


def generated_cases(mode='group',count=160):
    rng=random.Random(6001 if mode=='group' else 6101);out=[]
    for index in range(count):
        value=rng.randint(-12,12);other=rng.randint(-8,8)
        if mode=='group':
            source=f'data d;x={value};do;if x<0 then do;y={other};end;else do;y=2;end;output;x=x+y;output;end;put x y;run;'
        else:
            stop=rng.randint(1,7);skip=rng.randint(1,stop);leave=rng.randint(1,stop+1)
            if index%3==0:source=f'data d;x={value};do i=1 to {stop};do;if i={skip} then continue;if i={leave} then leave;x=x+i;end;end;put x i;run;'
            else:
                kind='while' if index%3==1 else 'until';test=f'n<{stop}' if kind=='while' else f'n>={stop}'
                source=f'data d;n=0;x={value};do {kind}({test});do;n=n+1;if n={skip} then continue;x=x+{other};end;end;put n x;run;'
        out.append(case(f'generated_{index}',source))
    return out


def refusal_cases(mode='group'):
    base='data d;x=1;do;';end='end;run;'
    common=[
      case('zero_PDV','data d;do;end;run;'),
      case('null_zero_PDV','data _null_;do;put "A";end;run;'),
      case('fraction',base+'x=.5;'+end),
      case('division',base+'x=1/3;'+end),
      case('power',base+'x=1**1;'+end),
      case('static_bad_skipped',base+'if 0 then bad=2147483647+1;'+end),
      case('dynamic_overflow','data d;x=2147483647;do;x=x+1;end;run;'),
      case('Unicode_name','data d;K=1;do;x=K;end;run;'),
      case('reserved_target',base+'_error_=1;'+end),
      case('foreign_OUTPUT',base+'output other;'+end),
      case('array',base+'array a{1} x;'+end),
      case('input','data d;input x;do;y=x;end;datalines;\n1\n;\nrun;'),
      case('unknown_call',base+'if 0 then y=sin(0);'+end),
      case('late_SET','data d;do;x=1;end;set raw;run;',catalog=supplied()),
      case('unresolved_selector','data d(keep=absent);x=1;do;x=2;end;run;')]
    if mode=='group':
        for value in (2147483648.,.5,True,{'missing':'A'}):
            incoming={'raw':{'schema':{'x':'number','unused':'number'},'rows':[{'x':1.,'unused':value}]}}
            common.append(case('selected_'+repr(value),'data d;set raw;do;x=0;if 0 then output;end;run;',catalog=incoming))
        incoming={'raw':{'schema':{'x':{'type':'character','length':4}},'rows':[]}}
        common.append(case('empty_character','data d;set raw;do;x=1;end;run;',catalog=incoming))
        incoming={'raw':{'schema':{'x':{'type':'number','length':4}},'rows':[]}}
        common.append(case('empty_numeric_width','data d;set raw;do;x=1;end;run;',catalog=incoming))
        incoming={'raw':{'schema':{'x':{'type':'number','format':'8.'}},'rows':[]}}
        common.append(case('empty_formatted_PUT','data d;set raw;do;x=1;put x;end;run;',catalog=incoming))
        return common
    return common+[
      case('group_not_owner',base+'if 0 then continue;'+end),
      case('leave_arguments','data d;x=1;do i=1 to 2;leave i;end;run;'),
      case('continue_arguments','data d;x=1;do i=1 to 2;continue i;end;run;'),
      case('active_index','data d;do i=1 to 2;do;if 0 then i=1;end;end;run;'),
      case('self_start','data d;i=1;do;do i=i to 3;x=i;end;end;run;'),
      case('control_literal_0','data d;x=0;do;do i=1.0 to 2;leave;end;end;run;'),
      case('control_literal_1','data d;x=0;do;do i=1 to 2e0;leave;end;end;run;'),
      case('control_literal_2','data d;x=0;do;do i=1 to 2 by 1e0;leave;end;end;run;'),
      case('control_literal_3','data d;x=0;do;do i=(1.0) to 2;leave;end;end;run;'),
      case('self_stop','data d;i=1;if 0 then do;do i=1 to i;x=i;end;end;run;'),
      case('self_by','data d;i=1;do;do i=1 to 3 by i;x=i;end;end;run;'),
      case('conditional_loop','data d;x=0;do;if 1 then do i=1 to 2;end;end;run;'),
      case('nested_while','data d;x=0;do i=1 to 2;do;do while(0);leave;end;end;end;run;'),
      case('count_10001','data d;do i=1 to 10001;leave;end;run;'),
      case('shared_budget','data d;x=0;do i=1 to 2;do j=1 to 6000;if j=1 then continue;x+1;end;end;run;'),
      case('until_10001','data d;x=1;do until(0);continue;end;run;'),
      case('while_10001','data d;x=1;do while(1);continue;end;run;'),
      case('increment_overflow','data d;do i=2147483647 to 2147483647 by 2147483647;continue;end;run;'),
      case('bad_after_leave','data d;x=1;do i=1 to 1;leave;x=.5;end;run;'),
      case('bad_zero_trip','data d;x=1;do while(0);leave;y=2147483647+1;end;run;')]


def promotion_cases():
    data=[
      ('data d; x=1; if 0 then do; x=2; end; put x=; run;',simple('x',[(1.,)],['x=1'])),
      ('data _null_; x=1; if 0 then do; x=2; end; put x=; run;',{'datasets':{},'log':['x=1']}),
      ('data d; if 1 then do; x=2; end; run;',simple('x',[(2.,)])),
      ('data d; do i=1 to 2; if 1 then do; x=7; end; end; run;',simple('i x',[(3.,7.)])),
      ('data d; do i=1 to 2; if 1 then leave; end; run;',simple('i',[(1.,)])),
      ('data d; do i=1 to 2; if 1 then continue; end; run;',simple('i',[(3.,)])),
      ('data d; if 1 then x=7; else do; x=9; end; run;',simple('x',[(7.,)])),
      ('data d; do i=1 to 2; leave; end; run;',simple('i',[(1.,)])),
      ('data d; n=2; do i=1 to n; leave; end; run;',simple('n i',[(2.,1.)])),
      ('data d; do i=1 to 2; continue; end; run;',simple('i',[(3.,)])),
      ('data d; n=2; do i=1 to n; continue; end; run;',simple('n i',[(2.,3.)]))]
    return [case(f'old_source_{i}',s,e) for i,(s,e) in enumerate(data)]


def cli_check(source,catalog=None,expected=None):
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);program=folder/'program.sas';program.write_text(source);inputs=folder/'inputs.json';inputs.write_text(json.dumps({} if catalog is None else catalog));out=folder/'job';args=[sys.executable,'-m','saschi','run',str(program),'--inputs',str(inputs),'--output',str(out)]
        if expected is not None and expected['datasets']:
            path=folder/'expected.json';path.write_text(json.dumps(expected['datasets']));args.extend(['--expect',str(path)])
        process=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=45);receipt=json.loads((out/'receipt.json').read_text())
        assert receipt['source_sha256']==hashlib.sha256(program.read_bytes()).hexdigest()
        if expected is None:
            assert process.returncode!=0 and not receipt['accepted'];assert not (out/'result.json').exists();assert not (out/'stdout.txt').exists()
        else:
            assert process.returncode==0 and receipt['accepted'] and receipt['comparison']==('passed' if expected['datasets'] else 'not requested'),(process.stdout,process.stderr,receipt)
            observed=json.loads((out/'result.json').read_text());assert_tree(observed,expected);assert receipt['result_sha256']==hashlib.sha256((out/'result.json').read_bytes()).hexdigest()
        return receipt


def wrong_cases(mode='group'):
    valid=hand_cases('group')[3] if mode=='group' else hand_cases('transfer')[0];correct=valid['expected'];target='d' if mode=='group' else 'measured';out=[]
    for damage in ('schema_order','snapshot','missing','multiplicity','metadata','value'):
        wrong=deepcopy(correct);table=wrong['datasets'][target]
        if damage=='schema_order':table['schema']=dict(reversed(list(table['schema'].items())))
        elif damage=='snapshot':table['rows'][0][next(iter(table['rows'][0]))]=99.
        elif damage=='missing':table['rows'][0][next(reversed(table['schema']))]=99.
        elif damage=='multiplicity':table['rows'].pop()
        elif damage=='metadata':table['label']='invented'
        else:table['rows'][0][next(iter(table['rows'][0]))]=-99.
        out.append({**valid,'name':damage,'wrong':wrong})
    return out


def wrong_comparators(mode='group',actual_cli=True):
    controls=wrong_cases(mode)
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory)
        for index,c in enumerate(controls):
            try:assert_tree(c['wrong'],c['expected'])
            except AssertionError:pass
            else:raise AssertionError('structural comparator missed '+c['name'])
            if not actual_cli:continue
            source=folder/f'{index}.sas';source.write_text(c['source']);expect=folder/f'{index}.json';expect.write_text(json.dumps(c['wrong']['datasets']));out=folder/f'out{index}'
            p=subprocess.run([sys.executable,'-m','saschi','run',str(source),'--expect',str(expect),'--output',str(out)],cwd=ROOT,capture_output=True,text=True,timeout=45);r=json.loads((out/'receipt.json').read_text());observed=out/'observed.json'
            assert p.returncode==1 and not r['accepted'] and r['comparison']=='failed';assert not (out/'result.json').exists() and observed.is_file();assert_tree(json.loads(observed.read_text()),c['expected']);assert r['result_sha256']==hashlib.sha256(observed.read_bytes()).hexdigest();assert r['expected_sha256']==hashlib.sha256(expect.read_bytes()).hexdigest()
    valid=controls[0];wrong=deepcopy(valid['expected']);wrong['log'][0]=wrong['log'][0].rstrip()
    try:assert_tree(wrong,valid['expected'])
    except AssertionError:pass
    else:raise AssertionError('logical text comparator missed trailing blank')
    observed=execute(valid['source'])['trace'];wrong_trace=observed.copy();wrong_trace.remove(next(event for event in wrong_trace if event=='group|enter'))
    try:assert_trace(wrong_trace,observed)
    except AssertionError:pass
    else:raise AssertionError('event comparator missed omitted group entry')
    return len(controls)+2


def main(mode='group'):
    assert mode in ('group','transfer');hand=hand_cases(mode);generated=generated_cases(mode);valid=hand+generated;seen=batch_witness(valid)
    for i,(c,witness) in enumerate(zip(valid,seen)):
        assert witness is not None,(c['name'],c['source']);observed=execute(c['source'],c['catalog'],i<len(hand) or i%40==0);assert_tree(observed['result'],witness['result']);assert_trace(observed['trace'],witness['trace'])
        if c['expected'] is not None:assert_tree(observed['result'],c['expected'])
        if c['trace'] is not None:assert_trace(observed['trace'],c['trace'])
    bad=refusal_cases(mode);seen=batch_witness(bad)
    for c,witness in zip(bad,seen):
        try:execute(c['source'],c['catalog'])
        except (ValueError,RuntimeError,AssertionError):pass
        else:raise AssertionError('missing refusal '+c['name'])
        assert witness is None,('R missing refusal',c['name'])
    cli_check(hand[0]['source'],hand[0]['catalog'],hand[0]['expected'])
    if mode=='transfer':
        promoted=promotion_cases();seen=batch_witness(promoted)
        from examples.verify_numeric_pipeline import witnesses as old_profile_witnesses
        assert old_profile_witnesses([(c['source'],c['catalog']) for c in promoted])==[None]*len(promoted)
        for c,witness in zip(promoted,seen):
            assert witness is not None;cooked=execute(c['source'],emitted=True);assert_tree(cooked['result'],c['expected']);assert_tree(witness['result'],c['expected']);p=compile_plan(c['source']).to_dict();p['steps'][0]['kind']='data';p['steps'][0]['operations'].pop(0)
            try:run_plan(p)
            except ValueError:pass
            else:raise AssertionError('old DATA profile admitted new control')
        accounting=batch_witness([hand[0]])[0]['accounting'];assert accounting=={'statements':57,'steps':[{'name':'seed','iterations':1,'trips':0},{'name':'measured','iterations':3,'trips':13},{'name':'fresh','iterations':1,'trips':3}]}
    atomic='data earlier;x=1;do;put x;output;end;run;data late;x=2147483647;do;x=x+1;end;run;'
    cli_check(atomic);assert batch_witness([case('late_failure',atomic)])==[None]
    emitted=translate(atomic);stream=io.StringIO()
    with contextlib.redirect_stdout(stream):
        try:exec(emitted.code,{})
        except ValueError:pass
        else:raise AssertionError('late failure accepted')
    assert stream.getvalue()==''
    if mode=='transfer':
        assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==SOURCE_PIN
        assert hashlib.sha256(json.dumps(original_expected(),separators=(',',':')).encode()).hexdigest()==RESULT_PIN
        assert hashlib.sha256(logical_stdout(original_expected()).encode()).hexdigest()==STDOUT_PIN
        assert hashlib.sha256(json.dumps(original_trace(),separators=(',',':')).encode()).hexdigest()==TRACE_PIN
        source=ORIGINAL.read_text()
        frontier=[case('appended',source+'proc print;run;'),case('truncated',source.rsplit('run;',1)[0])]
        assert batch_witness(frontier)==[None,None]
        for c in frontier:
            assert compile_plan(c['source']).blocked
    controls=wrong_comparators(mode)
    print(f'VERIFIED: grouped-control-{mode} {len(hand)} hand pins,{len(generated)} generated full-source/runtime/R event schedules,{len(bad)} shared source refusals,{controls} wrong comparators (6 actual CLI dataset,1 exact logical text,1 exact trace); emitted/CLI/atomic; no live SAS')


if __name__=='__main__':main()
