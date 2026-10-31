#!/usr/bin/env python3
"""Independent scalar-flow source, caller, state, event and CLI evidence."""
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
from saschi.flow_control import execute_step,PROFILE,LINK_PROFILE
from saschi.values import normalize_catalog

ORIGINAL=HERE/'flow_control_capture.sas'
SOURCE_PIN='2d81903456ba8305b09ccdd61cf747e3c2f1e0c65130aa7ca8ca7d85c044d94b'
RESULT_PIN='0edeb7c89551d798bbc7be25b26e170b742c9db8fc7357fa629eae0005418b54'
STDOUT_PIN='88c340a8177282ecf27890701f64be735395bc1dd8d683525bcb8527e4343ccf'
TRACE_PIN='05e578889601605443ea4fc88771d8f707206ac8a1a4982321e3e5fc44fdfb62'
CORPUS_SOURCE_PIN='8131b1289000bbb02418d19f4fbd9df9f66df30ea7141fd26f87ba3c28dd42a9'
CORPUS_RESULT_PIN='9a4289d298d831f1f892e263d9bd3376a7cd83ff8417b6e88218692a6f69d26a'
CORPUS_STDOUT_PIN='b9550d1174ff5ffcd7fb23a0c323a60f8d7a12ba8f06565632074fc75a19df25'
CORPUS_TRACE_PIN='62686291d7a778a71a3bb19e4671cfbfc2b024946de4de7b32db794ff72de226'


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
        process=subprocess.run([r,str(HERE/'flow_control.R'),'batch',str(folder)],capture_output=True,text=True,check=True,timeout=120)
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
        if step['kind']!='flow_data':raise ValueError('trace witness expects new control steps only')
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
    return {'datasets':{
        'counted':{'schema':{'n':'number'},'rows':[{'n':3.}]},
        'saved':{'schema':dict.fromkeys(('total','x','scratch'),'number'),'rows':[{'total':2.,'x':1.,'scratch':2.},{'total':8.,'x':3.,'scratch':6.}]},
        'tail':{'schema':{'x':'number'},'rows':[{'x':1.}]}},
        'log':['3 ','1 2 2 ','3 8 6 ','1 ']}


def corpus_source():
    path=Path(os.environ.get('SASCHI_ROKU_CORPUS',ROOT.parent/'saschi-roku/corpus'))
    if not path.is_absolute():raise ValueError('SASCHI_ROKU_CORPUS must be absolute')
    return path/'flow_control_structures.sas'


def corpus_expected():
    return {'datasets':{},'log':[f'{n} {p} ' for p in range(1,11) for n in range(1,p+1)]+['2 15 1 ','533 221 13 ','8 44 4 ']}


def case(name,source,expected=None,catalog=None,trace=None):
    return {'name':name,'source':source,'catalog':{} if catalog is None else catalog,'expected':expected,'trace':trace}


def simple(names,rows,logs=()):
    return {'datasets':{'d':{'schema':dict.fromkeys(names.split(),'number'),'rows':[dict(zip(names.split(),values)) for values in rows]}},'log':list(logs)}


def original_trace():
    """Hand schedule from the original source, independent of either engine."""
    t=['row|1','pc|0','pc|1','assign|n|0']
    for n in (1,2,3):
        t.extend(['pc|2','label|again','pc|3',f'assign|n|{n}','pc|4',f'if|{int(n<3)}'])
        if n<3:t.append('goto|again')
    t.extend(['pc|5','put|3320','pc|6','output|n=3','pc|7','stop'])
    for row,x,total,scratch in ((1,1,2,2),(2,2,None,None),(3,3,8,6)):
        t.extend([f'row|{row}','pc|0','pc|1','pc|2','pc|3',f'input|x={x}','pc|4','if|0','pc|5',f'if|{int(x==2)}'])
        if x==2:t.extend(['return','next-record']);continue
        t.extend(['pc|6','link|adjust','call|7','pc|10','label|adjust','pc|11',f'assign|scratch|{scratch}','pc|12',f'sum|total|{total}','pc|13','return','resume|explicit|7','pc|7','put|'+f'{x} {total} {scratch} '.encode().hex(),'pc|8',f'output|total={total};x={x};scratch={scratch}','pc|9','return','next-record'])
    t.extend(['row|1','pc|0','pc|1','assign|x|0','pc|2','link|bump','call|3','pc|6','label|bump','pc|7','assign|x|1','pc|8','return','resume|explicit|3','pc|3','put|3120','pc|4','output|x=1','pc|5','stop'])
    return t


def corpus_trace():
    """Independent hand schedule for both unchanged corpus DATA steps."""
    t=['row|1','pc|0','pc|1','assign|n|1','pc|2','assign|p|1']
    for p in range(1,11):
        for n in range(1,p+1):
            t.extend(['pc|3','label|l1','pc|4','put|'+f'{n} {p} '.encode().hex(),'pc|5',f'assign|n|{n+1}','pc|6',f'if|{int(n<p)}'])
            if n<p:t.append('goto|l1')
        t.extend(['pc|7',f'assign|p|{p+1}','pc|8','assign|n|1','pc|9',f'if|{int(p==10)}'])
        t.extend(['stop'] if p==10 else ['pc|10','goto|l1'])
    schedules=((2,15,1,((2,15,2),(15,2,1),(2,1,0))),
               (533,221,13,((533,221,91),(221,91,39),(91,39,13),(39,13,0))),
               (8,44,4,((8,44,8),(44,8,4),(8,4,0))))
    for row,(a,b,gcd,steps) in enumerate(schedules,1):
        t.extend([f'row|{row}','pc|0','pc|1',f'input|a={a};b={b}','pc|2','link|gcd','call|3','pc|5','label|gcd','pc|6',f'assign|_a|{a}','pc|7',f'assign|_b|{b}','pc|8'])
        for trip,(left,right,remainder) in enumerate(steps,1):
            t.extend(['test|while|1',f'iteration|while|{trip}',f'assign|_r|{remainder}',f'assign|_a|{right}',f'assign|_b|{remainder}'])
        t.extend(['test|while|0','loop|exit|while','pc|9',f'assign|gcd|{gcd}','pc|10','return','resume|explicit|3','pc|3','put|'+f'{a} {b} {gcd} '.encode().hex(),'pc|4','return','next-record'])
    return t


def hand_cases(mode='jump'):
    common=[case('original',ORIGINAL.read_text(),original_expected(),trace=original_trace())]
    if mode=='jump':return common+[
      case('backward','data d;x=0;again:x=x+1;if x<3 then goto again;put x;output;stop;run;',simple('x',[(3.,)],['3 '])),
      case('GO_TO','data d;x=1;go to done;x=99;done:put x;run;',simple('x',[(1.,)],['1 '])),
      case('namespace','data d;gcd=7;x=1;goto gcd;x=99;gcd:put gcd x;run;',simple('gcd x',[(7.,1.)],['7 1 '])),
      case('old_STOP_group','data d;x=1;do;stop;end;run;',simple('x',[])),
      case('keyword_variables','data d;set=1;keep=2;drop=3;output;stop;run;',simple('set keep drop',[(1.,2.,3.)])),
      case('STOP_snapshots','data d;x=1;output;x=2;stop;run;',simple('x',[(1.,)])),
      case('dead_OUTPUT','data d;x=1;if 0 then output;goto done;done:x=2;run;',simple('x',[])),
      case('missing_truth','data d;x=.;if x then goto done;x=2;done:put x;run;',simple('x',[(2.,)],['2 '])),
      case('STOP_before_increment','data d;do i=2147483647 to 2147483647 by 2147483647;output;stop;end;run;',simple('i',[(2147483647.,)])),
      case('STOP_before_test','data d;x=2147483647;do until(x+1);output;stop;end;run;',simple('x',[(2147483647.,)])),
      case('quoted_stage2','data d;x=1;put "return; link sub; mod(1,2)";stop;run;',simple('x',[],['return; link sub; mod(1,2)']))]
    return common+[
      case('whole_external',corpus_source().read_text(),corpus_expected(),trace=corpus_trace()),
      case('same_code_line_INPUT','data d;retain total 0;input x;link r;total+x;return;r:scratch=x*2;return;datalines;\n1\n3\n.\n;\nrun;',simple('total x scratch',[(1.,1.,2.),(4.,3.,6.),(4.,None,None)])),
      case('same_PDV','data d;x=0;link sub;put x;link sub;put x;stop;sub:x=x+1;return;run;',simple('x',[],['1 ','2 '])),
      case('active_GOTO','data d;x=0;link sub;output;stop;sub:goto done;done:x=2;return;run;',simple('x',[(2.,)])),
      case('implicit_caller_return','data d;input x;link sub;put x;return;sub:x=x+1;\ncards;\n1\n2\n;\nrun;',simple('x',[(2.,),(3.,)],['2 ','3 '])),
      case('next_record','data d;input x;if x=1 then scratch=9;total+x;return;\ncards;\n1\n2\n;\nrun;',simple('x scratch total',[(1.,9.,1.),(2.,None,3.)])),
      case('explicit_suppression','data d;input x;if 0 then output;return;\ncards;\n1\n2\n;\nrun;',simple('x',[])),
      case('STOP_input','data d;input x;if x=2 then stop;output;return;\ncards;\n1\n2\n3\n;\nrun;',simple('x',[(1.,)])),
      case('FLOWOVER_EOF','data d;input a b;put a b;return;\ncards;\n1\n2 99\n3\n;\nrun;',simple('a b',[(1.,2.)],['1 2 '])),
      case('RETURN_before_increment','data d;x=0;link sub;output;stop;sub:do i=2147483647 to 2147483647 by 2147483647;x=x+1;return;end;run;',simple('x i',[(1.,2147483647.)])),
      case('empty_INPUT','data d;input a b;link sub;return;sub:future=9;return;\ncards;\n;\nrun;',simple('a b future',[])),
      case('signed_MOD','data d;x=-8;y=3;link sub;put r;stop;sub:r=mod(x,y);return;run;',simple('x y r',[],['-2 ']))]


def generated_cases(mode='jump',count=160):
    rng=random.Random(6401 if mode=='jump' else 6501);out=[]
    for i in range(count):
        if mode=='jump':
            start=rng.randint(-12,12);limit=rng.randint(1,12);delta=rng.randint(-4,4)
            source=f'data d;n=0;x={start};again:n=n+1;x=x+{delta};if n<{limit} then goto again;put n x;output;stop;run;'
            expected=simple('n x',[(float(limit),float(start+limit*delta))],[f'{limit} {start+limit*delta} '])
        else:
            import math
            pairs=[(rng.randint(1,10000),rng.randint(1,10000)) for _ in range(3)]
            source='data d;input a b;link gcd;put a b gcd;output;return;gcd:_a=a;_b=b;do while(_b>0);_r=mod(_a,_b);_a=_b;_b=_r;end;gcd=_a;return;\ncards;\n'+''.join(f'{a} {b}\n' for a,b in pairs)+';\nrun;'
            expected=simple('a b _a _b _r gcd',[(float(a),float(b),float(math.gcd(a,b)),0.,0.,float(math.gcd(a,b))) for a,b in pairs],[f'{a} {b} {math.gcd(a,b)} ' for a,b in pairs])
        out.append(case(f'generated_{i}',source,expected))
    return out


def refusal_cases(mode='jump'):
    common=[
      ('undefined','data d;x=1;if 0 then goto absent;run;'),
      ('duplicate','data d;x=1;a:x=2;A:stop;run;'),
      ('label_in_group','data d;x=1;do;a:x=2;end;goto a;run;'),
      ('label_in_loop','data d;do i=1 to 1;a:x=2;end;goto a;run;'),
      ('GOTO_from_group','data d;x=1;do;goto a;end;a:stop;run;'),
      ('GOTO_from_loop','data d;do i=1 to 1;goto a;end;a:stop;run;'),
      ('cross_step','data d;x=1;goto a;run;data other;a:x=2;stop;run;'),
      ('fraction','data d;x=.5;stop;run;'),
      ('division','data d;x=1/2;stop;run;'),
      ('power','data d;x=1**1;stop;run;'),
      ('new_call','data d;x=1;stop;if 0 then y=sin(0);run;'),
      ('dead_overflow','data d;x=1;stop;y=2147483647+1;run;'),
      ('dynamic_overflow','data d;x=2147483647;x=x+1;stop;run;'),
      ('Unicode','data d;K=1;stop;run;'),
      ('array','data d;array a{1} x;x=1;stop;run;'),
      ('SET','data d;set raw;stop;run;'),
      ('foreign_OUTPUT','data d;x=1;output other;stop;run;'),
      ('no_PDV','data _null_;stop;run;'),
      ('unknown_selector','data d(keep=absent);x=1;stop;run;'),
      ('missing_RUN','data d;x=1;stop;'),
      ('after_RUN','data d;x=1;stop;run;proc print;run;'),
      ('instruction_budget','data d;x=1;again:goto again;run;')]
    if mode=='link':common +=[
      ('unlinked_no_INPUT','data d;x=1;return;run;'),
      ('dead_unlinked_no_INPUT','data d;x=1;if 0 then return;stop;run;'),
      ('zero_loop_return','data d;x=1;do while(0);return;end;stop;run;'),
      ('nested_LINK','data d;x=1;link sub;stop;sub:link sub;return;run;'),
      ('multiple_targets','data d;x=1;link a;link b;stop;a:return;b:return;run;'),
      ('recursive_GOTO','data d;x=1;again:link sub;stop;sub:goto again;return;run;'),
      ('LINK_from_group','data d;x=1;do;link sub;end;stop;sub:return;run;'),
      ('INPUT_reentry','data d;again:input x;goto again;\ncards;\n1\n;\nrun;'),
      ('multiple_INPUT','data d;input x;input y;return;\ncards;\n1\n;\nrun;'),
      ('fraction_INPUT','data d;input x;return;\ncards;\n.5\n;\nrun;'),
      ('incomplete_fraction','data d;input x y;return;\ncards;\n1.5\n;\nrun;'),
      ('incomplete_bad','data d;input x y;return;\ncards;\nbad\n;\nrun;'),
      ('empty_MOD_zero','data d;input x;link sub;return;sub:y=mod(x,0);return;\ncards;\n;\nrun;'),
      ('dynamic_MOD_zero','data d;x=1;y=0;link sub;stop;sub:z=mod(x,y);return;run;'),
      ('missing_MOD','data d;x=.;link sub;stop;sub:y=mod(x,2);return;run;')]
    return [case(n,s) for n,s in common]


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



def wrong_cases(mode='jump'):
    valid=hand_cases(mode)[0];out=[]
    for damage in ('schema_order','snapshot','missing','multiplicity','metadata','value'):
        wrong=deepcopy(valid['expected']);table=wrong['datasets']['saved']
        if damage=='schema_order':table['schema']=dict(reversed(list(table['schema'].items())))
        elif damage=='snapshot':table['rows'][0]['scratch']=99.
        elif damage=='missing':table['rows'][0]['scratch']=None
        elif damage=='multiplicity':table['rows'].pop()
        elif damage=='metadata':table['label']='invented'
        else:table['rows'][0]['total']=-99.
        out.append({**valid,'name':damage,'wrong':wrong})
    return out


def wrong_comparators(mode='jump',actual_cli=True):
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
    trace=original_trace();wrong_trace=trace.copy();wrong_trace.remove(next(e for e in trace if e.startswith('resume|')))
    try:assert_trace(wrong_trace,trace)
    except AssertionError:pass
    else:raise AssertionError('event comparator missed caller resumption')
    return len(controls)+2


def promotion_cases():
    return [case('old_STOP_group','data d;x=1;do;stop;end;run;',simple('x',[]))]


def assert_stop_promotion(test,source):
    from examples.verify_grouped_control import batch_witness as old_witness
    from saschi.plan import _compile_legacy_plan
    from saschi.grouped_control import compile_program as old_compile
    test.assertEqual(source,promotion_cases()[0]['source']);test.assertTrue(old_compile(source,_compile_legacy_plan).blocked)
    test.assertEqual(old_witness([case('old',source)]),[None])
    observed=execute(source,emitted=True);assert_tree(observed['result'],promotion_cases()[0]['expected'])
    independent=batch_witness([case('new',source)])[0];test.assertIsNotNone(independent);assert_tree(independent['result'],observed['result']);assert_trace(independent['trace'],observed['trace'])
    old=compile_plan(source).to_dict();old['steps'][0]['kind']='control_data';old['steps'][0]['operations'][0]={'kind':'control_profile','line':old['steps'][0]['line'],'args':{'name':'bounded-control-v1'}}
    with test.assertRaises(ValueError):run_plan(old)


def main(mode='jump'):
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==SOURCE_PIN
    assert hashlib.sha256(json.dumps(original_expected(),separators=(',',':')).encode()).hexdigest()==RESULT_PIN
    assert hashlib.sha256(logical_stdout(original_expected()).encode()).hexdigest()==STDOUT_PIN
    assert hashlib.sha256(json.dumps(original_trace(),separators=(',',':')).encode()).hexdigest()==TRACE_PIN
    assert mode in ('jump','link');hand=hand_cases(mode);generated=generated_cases(mode);valid=hand+generated;seen=batch_witness(valid)
    for index,(c,witness) in enumerate(zip(valid,seen)):
        assert witness is not None,('R missing valid',c['name'],c['source']);o=execute(c['source'],c['catalog'],index<len(hand) or index%40==0);assert_tree(o['result'],witness['result']);assert_trace(o['trace'],witness['trace']);assert_tree(o['result'],c['expected'])
        if c['trace'] is not None:assert_trace(o['trace'],c['trace'])
    bad=refusal_cases(mode);seen=batch_witness(bad)
    for c,witness in zip(bad,seen):
        try:execute(c['source'])
        except (ValueError,RuntimeError,AssertionError):pass
        else:raise AssertionError('source missing refusal '+c['name'])
        assert witness is None,('R missing refusal',c['name'])
    cli_check(ORIGINAL.read_text(),expected=original_expected())
    atomic='data earlier;x=1;put x;output;stop;run;data late;x=2147483647;x=x+1;stop;run;'
    cli_check(atomic);assert batch_witness([case('late',atomic)])==[None]
    stream=io.StringIO()
    with contextlib.redirect_stdout(stream):
        try:exec(translate(atomic).code,{})
        except ValueError:pass
        else:raise AssertionError('late failure accepted')
    assert stream.getvalue()==''
    controls=wrong_comparators(mode)
    if mode=='link':
        assert hashlib.sha256(corpus_source().read_bytes()).hexdigest()==CORPUS_SOURCE_PIN
        assert hashlib.sha256(json.dumps(corpus_expected(),separators=(',',':')).encode()).hexdigest()==CORPUS_RESULT_PIN
        assert hashlib.sha256(json.dumps(corpus_trace(),separators=(',',':')).encode()).hexdigest()==CORPUS_TRACE_PIN
        source=corpus_source().read_text();expected=corpus_expected();r=batch_witness([case('whole',source)])[0];o=execute(source,emitted=True);assert_tree(r['result'],expected);assert_tree(o['result'],expected);assert_trace(r['trace'],corpus_trace());assert_trace(o['trace'],corpus_trace());cli_check(source,expected=expected)
        assert r['accounting']=={'statements':27,'steps':[{'name':'_null_','iterations':1,'trips':0},{'name':'_null_','iterations':3,'trips':10}]}
        assert hashlib.sha256(logical_stdout(expected).encode()).hexdigest()=='b9550d1174ff5ffcd7fb23a0c323a60f8d7a12ba8f06565632074fc75a19df25'
        print('VERIFIED corpus: flow_control_structures.sas; complete unchanged 27-statement/two-step source,58 logical records,10 GCD WHILE bodies,698 hand/R/runtime/emitted events and actual CLI; no live SAS')
    print(f'VERIFIED: scalar-{mode} {len(hand)} hand pins,{len(generated)} generated full-source/runtime/R schedules,{len(bad)} shared refusals,{controls} wrong comparators (6 actual CLI dataset,1 exact logical text,1 exact trace); emitted/CLI/atomic; no live SAS')


if __name__=='__main__':main()
