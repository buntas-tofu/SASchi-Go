#!/usr/bin/env python3
"""Whole immutable vendor input KEEP program under existing logical report policy."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.vendor_sources import verify_sources
from vendor_sort_input_keep_hand import build,bodies,encode,LINES,SOURCE_SHA256,SOURCE_BYTES
from verify_vendor_sorted_copy import ordered_equal,need,cli
from saschi.plan import compile_plan
from saschi.emit_py import translate
from saschi.emit_cpp import translate as translate_cpp
from saschi.job import build_job
from saschi import character_input,mixed_reports,runtime,sort_projection

IDENTITY='sas-code-examples-sort-input-keep-v1'
FROZEN={
 'result.json':'4f29665f2d4d0d6eb075bac8c80d44d6e27d33cf7f30cb33c60f739c0e2f2789',
 'accounting.json':'99dcb422e7b8769d6d4c699bb939741a796272db201354ac78c3c8c03caa6ad3',
 'trace.json':'fb325dd842b07826d31f39cab6aa49630d8603a99a294648738eb54bd235717a',
 'print_01.txt':'965c813bf45fcd5a95ee4d557820536b7126ad67dd3e207d729f7af78574d997',
 'print_02.txt':'11038d8cc5e709bb22f72b78f29f9346f71b739c1fe6e81895fd23608036aa12',
}


def traced_run(plan):
    """Observe actual input/report/sort execution, never supply expected values."""
    trace=[]
    input_engine,title_engine=character_input.execute_step,mixed_reports.execute_title
    print_engine,sort_engine=mixed_reports.execute_print,sort_projection.execute_sort
    def input_observer(step,tables,version=2,**kwargs):
        observed=[];table,logs=input_engine(step,tables,version,trace=observed)
        lines=step['operations'][0]['args']['source_lines']
        trace.append({'event':'data_begin','line':step['line'],'table':step['name']})
        for event in observed:
            if event['kind']=='character_input':
                item={'event':'input_attempt','line':event['line'],'record':event['attempt']}
                if event['complete']:item['record_line']=lines[3]+event['attempt']
                item['eof']=not event['complete'];trace.append(item)
            else:
                need(event['kind']=='character_output','unexpected actual input event')
                trace.append({'event':'implicit_output','table':step['name'],'observation':event['observation']})
        trace.append({'event':'data_end','line':lines[-1],'table':step['name'],'rows':len(table['rows'])})
        return table,logs
    def title_observer(step,version=2,**kwargs):
        text=title_engine(step,version)
        item={'event':'title_reset' if text is None else 'title_set','line':step['line']}
        if text is not None:item['text']=text
        trace.append(item);return text
    def print_observer(step,tables,title=None,ordinal=1,version=2,**kwargs):
        artifacts=print_engine(step,tables,title,ordinal,version)
        trace.append({'event':'print','line':step['line'],'table':step['inputs'][0],
                      'report':next(iter(artifacts)),'rows':len(tables[step['inputs'][0]]['rows']),'title':title})
        return artifacts
    def sort_observer(step,tables,version=2,**kwargs):
        observed=[];table=sort_engine(step,tables,version,trace=observed)
        need(len(observed)==1,'one actual sort event required');trace.extend(observed);return table
    with patch.object(character_input,'execute_step',input_observer),patch.object(mixed_reports,'execute_title',title_observer),\
         patch.object(mixed_reports,'execute_print',print_observer),patch.object(sort_projection,'execute_sort',sort_observer):
        result=runtime.run_plan(plan)
    return result,trace


def late_failure(area):
    # Owned adversarial source. First projected SORT and report complete before
    # the second retained numeric fraction reaches the integer-only renderer.
    def producer(name,value):
        return ('data '+name+';infile datalines dsd;input word :$2. n;datalines4;\nA,'+
                value+'\n;;;;\nrun;\n')
    text=producer('first','2')
    text+='proc sort data=first(keep=word) out=first_sorted nodupkey;by word;run;\n'
    text+='proc print data=first_sorted;run;\n'+producer('second','0.5')
    text+='proc sort data=second(keep=word n) out=second_sorted;by word;run;\n'
    text+='proc print data=second_sorted;run;\n'
    sorts=[];prints=[];sort_engine=sort_projection.execute_sort;print_engine=mixed_reports.execute_print
    def sort_observer(*args,**kwargs):
        result=sort_engine(*args,**kwargs);sorts.append(args[0]['name']);return result
    def print_observer(*args,**kwargs):
        result=print_engine(*args,**kwargs);prints.append(next(iter(result)));return result
    with patch.object(sort_projection,'execute_sort',sort_observer),patch.object(mixed_reports,'execute_print',print_observer):
        job=build_job(text)
    need(not job.plan.blocked and job.code==1 and job.result is None and
         sorts==['first_sorted','second_sorted'] and prints==['print_01.txt'],
         'actual late renderer failure did not follow two SORTs and a buffered first report')
    source=area/'owned-late.sas';source.write_text(text);output=area/'late-cli'
    run,receipt=cli(source,output)
    need(run.returncode==1 and receipt['accepted'] is False,'late actual CLI failure accepted')
    need(not any((output/name).exists() for name in ('reports','exports','result.json','observed.json')),
         'late job published a partial accepted result or report')


def main():
    with patch('tools.vendor_sources.urlopen',side_effect=AssertionError('offline gate attempted network')):
        bound=verify_sources()[IDENTITY]
    original=bound['source'].read_bytes();license_bytes=bound['license'].read_bytes()
    need(len(original)==SOURCE_BYTES and hashlib.sha256(original).hexdigest()==SOURCE_SHA256,'complete original source differs')
    expected,accounting,expected_trace=build(original);artifacts=bodies(original)
    need({name:hashlib.sha256(raw).hexdigest() for name,raw in artifacts.items()}==FROZEN,
         'independent pre-engine frozen expectation changed')
    external=Path(tempfile.gettempdir())/'saschi-sort-input-keep-20261102'
    need(not external.is_symlink() and not external.resolve().is_relative_to(ROOT),'external vendor output root is redirected')
    external.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='gate-',dir=external) as temporary:
        area=Path(temporary).resolve();source=area/'original.sas';source.write_bytes(original)
        reference=area/'R'
        run=subprocess.run([os.environ.get('ROSETTA_RSCRIPT','Rscript'),str(ROOT/'examples/vendor_sort_input_keep.R'),
                            str(source),str(reference)],capture_output=True,timeout=120)
        need(run.returncode==0,'independent full-source R failed: '+run.stderr.decode(errors='replace'))
        need({p.name for p in reference.iterdir()}==set(artifacts),'independent R artifact universe differs')
        for name,raw in artifacts.items():need((reference/name).read_bytes()==raw,'whole-source hand/R differs: '+name)
        plan=compile_plan(original.decode('ascii'))
        need(not plan.blocked and len(plan.steps)==7,'whole unchanged source not fully admitted')
        need([line for _,_,line in plan.matched]==LINES,'complete rule-application line accounting differs')
        actual,trace=traced_run(plan.to_dict())
        need(ordered_equal(actual,expected),'whole runtime datasets, descriptors or reports differ')
        need(ordered_equal(trace,expected_trace) and len(trace)==37,'actual whole-source event schedule differs')
        emitted=translate(original.decode('ascii'));need(not emitted.blocked,'whole Python emitter refused')
        namespace={};stdout=io.StringIO()
        with redirect_stdout(stdout):exec(emitted.code,namespace)
        need(stdout.getvalue()=='' and ordered_equal(namespace['result'],expected),'whole emitted outcome differs')
        need(translate_cpp(original.decode('ascii')).blocked,'unadmitted C++ target accepted')
        data_path=area/'expected.json';reports_path=area/'expected-reports.json'
        data_path.write_bytes(encode(expected['datasets']));reports_path.write_bytes(encode(expected['reports']))
        output=area/'accepted';run,receipt=cli(source,output,expected=data_path,reports=reports_path)
        need(run.returncode==0 and receipt['accepted'] is True and
             receipt['comparison']==receipt['report_comparison']=='passed' and
             receipt['report_contract']=='ascii-titled-mixed-integer-v1','whole actual CLI comparison failed')
        need(ordered_equal(json.loads((output/'result.json').read_text()),expected),'published whole CLI result differs')
        completeness=receipt['completeness']
        need([completeness[k] for k in ('n_statements','n_routed','n_unrouted','n_functions','n_tickets')]==[16,15,1,0,0],
             'whole source catalog accounting differs')
        need({p.name for p in (output/'reports').iterdir()}==set(expected['reports']),'published report basenames differ')
        for name,text in expected['reports'].items():need((output/'reports'/name).read_bytes()==text.encode('ascii'),'published report differs')
        wrong=[];tables=expected['datasets']
        value=deepcopy(tables);value['classtest_sort']['schema']['name']['length']=8;wrong.append(value)
        value=deepcopy(tables);value['classtest_sort']['schema']['subject']={'type':'character','length':7}
        for row in value['classtest_sort']['rows']:row['subject']='X      '
        wrong.append(value)
        value=deepcopy(tables);value['classtest']['schema']={'name':value['classtest']['schema']['name']}
        value['classtest']['rows']=[{'name':row['name']} for row in value['classtest']['rows']];wrong.append(value)
        value=deepcopy(tables);value['classtest_sort']['rows'][0]['name']='Wrong  ';wrong.append(value)
        value=deepcopy(tables);value['classtest_sort']['rows'].reverse();wrong.append(value)
        value=deepcopy(tables);value['classtest_sort']['rows'].append(deepcopy(value['classtest_sort']['rows'][0]));wrong.append(value)
        value=deepcopy(tables);value['classtest_sort']['rows'].pop();wrong.append(value)
        value=deepcopy(tables);value['unexpected']=deepcopy(value['classtest_sort']);wrong.append(value)
        for index,value in enumerate(wrong):
            path=area/('wrong-data-'+str(index)+'.json');path.write_bytes(encode(value));destination=area/('wrong-data-'+str(index))
            failed,record=cli(source,destination,expected=path,reports=reports_path)
            need(failed.returncode==1 and record['accepted'] is False and not (destination/'reports').exists(),
                 'wrong dataset comparator accepted or leaked report artifacts: '+str(index))
        # The generic CLI permits selected expected-table subsets. The strict
        # independent complete-result comparator additionally binds catalog and
        # descriptor order, without broadening that CLI contract.
        value=deepcopy(expected);value['datasets'].pop('classtest_sort')
        need(not ordered_equal(value,expected),'complete-catalog omission comparator is weak')
        value=deepcopy(expected);value['datasets']['classtest']['schema']=dict(reversed(list(value['datasets']['classtest']['schema'].items())))
        need(not ordered_equal(value,expected),'descriptor-order comparator is weak')
        value=deepcopy(expected);value['datasets']['classtest_sort']['rows'][1]['name']='Henry'
        need(not ordered_equal(value,expected),'stored-padding comparator is weak')
        wrong_reports=[]
        for transform in (lambda t:t.split('\n',1)[1],lambda t:t.rstrip('\n'),lambda t:t.replace('\n1 ','\n99 ',1)):
            value=deepcopy(expected['reports']);value['print_02.txt']=transform(value['print_02.txt']);wrong_reports.append(value)
        value=deepcopy(expected['reports']);value.pop('print_02.txt');wrong_reports.append(value)
        value=deepcopy(expected['reports']);value['other.txt']=value.pop('print_02.txt');wrong_reports.append(value)
        for index,value in enumerate(wrong_reports):
            path=area/('wrong-report-'+str(index)+'.json');path.write_bytes(encode(value));destination=area/('wrong-report-'+str(index))
            failed,record=cli(source,destination,expected=data_path,reports=path)
            need(failed.returncode==1 and record['accepted'] is False and not (destination/'reports').exists(),
                 'wrong report comparator accepted or leaked artifacts: '+str(index))
        late_failure(area)
        need(source.read_bytes()==original,'staged original changed during gate')
    with patch('tools.vendor_sources.urlopen',side_effect=AssertionError('offline gate attempted network')):verify_sources()
    need(bound['source'].read_bytes()==original and bound['license'].read_bytes()==license_bytes,'external source/license pins changed')
    print('VERIFIED vendor: '+IDENTITY+'; unchanged1824bytes; independent whole hand/baseR; '
          '15statements+1opaque/14rows/15attempts/37events;2datasets/2exactreports375+142; '
          'actualCLI+8wrongdatasets+5wrongreports+latebuffered-report-atomic; no live SAS or physical-layout claim')
    return 0


if __name__=='__main__':raise SystemExit(main())
