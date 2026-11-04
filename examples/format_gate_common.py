"""Complete-result/R/portable/CLI controls shared by separate FORMAT gates."""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from verify_vendor_sorted_copy import ordered_equal,encode


def external_temporary(prefix):
    from tools.vendor_sources import cache_root
    root=cache_root(Path(tempfile.gettempdir())/'saschi-format-scratch')
    root.mkdir(parents=True,exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=prefix,dir=root)


def witness(text,script):
    with external_temporary('saschi-format-witness-') as temporary:
        area=Path(temporary);source=area/'original.sas';source.write_text(text,encoding='utf-8')
        output=area/'R'
        run=subprocess.run([os.environ.get('ROSETTA_RSCRIPT','Rscript'),str(ROOT/'examples'/script),str(source),str(output)],
                           capture_output=True,text=True,timeout=120)
        assert run.returncode==0,run.stderr
        return tuple(json.loads((output/(name+'.json')).read_text()) for name in ('result','accounting','trace'))


def frozen(values,pins):
    for name,value in zip(('result.json','accounting.json','trace.json'),values,strict=True):
        assert hashlib.sha256(encode(value)).hexdigest()==pins[name],('pre-engine oracle pin differs',name)


def execute(text,expected,accounting,expected_trace,runner):
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    from saschi.emit_py import translate
    from saschi.emit_cpp import translate as cpp
    parsed=compile_plan(text);assert not parsed.blocked,parsed.tickets
    assert len(parsed.steps)==accounting['steps']
    assert len(parsed.matched)==accounting['language_statements']
    assert [line for _,_,line in parsed.matched]==accounting['statement_lines']
    actual_trace=[];actual=runner(parsed.to_dict(),trace=actual_trace)
    assert ordered_equal(actual,expected),'whole original runtime result differs'
    assert ordered_equal(actual_trace,expected_trace),'whole original execution trace differs'
    assert ordered_equal(run_plan(parsed.to_dict()),expected),'runtime dispatch differs'
    namespace={};stdout=io.StringIO();emitted=translate(text)
    with redirect_stdout(stdout):exec(compile(emitted.code,'<FORMAT original>','exec'),namespace)
    assert stdout.getvalue()=='' and ordered_equal(namespace['result'],expected),'emitted complete result or stdout differs'
    assert cpp(text).blocked,'unqualified C++ target accepted'


def cli_check(text,expected,contract,*,wrong=None):
    with external_temporary('saschi-format-cli-') as temporary:
        area=Path(temporary);path=area/'source.sas';path.write_text(text,encoding='utf-8');truth=expected if wrong is None else wrong
        for name,value in [('datasets',truth['datasets']),('reports',truth.get('reports',{})),('log',truth['log'])]:
            (area/(name+'.json')).write_bytes(encode(value))
        command=[sys.executable,'-m','saschi','run',str(path),'--expect',str(area/'datasets.json'),'--expect-log',str(area/'log.json'),'--output',str(area/'job')]
        if expected.get('reports'):command.extend(['--expect-reports',str(area/'reports.json')])
        run=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=120)
        record=json.loads((area/'job'/'receipt.json').read_text())
        assert run.returncode==(0 if wrong is None else 1),(run.stderr,record)
        assert record['accepted']==(wrong is None)
        if wrong is None:
            assert record['comparison']==record['log_comparison']=='passed'
            if expected.get('reports'):assert record['report_comparison']=='passed' and record['report_contract']==contract
            assert ordered_equal(json.loads((area/'job'/'result.json').read_text()),expected)
            for name,text in expected.get('reports',{}).items():assert (area/'job'/'reports'/name).read_bytes()==text.encode('ascii')
        else:
            assert not (area/'job'/'result.json').exists() and not (area/'job'/'reports').exists()
        return record


def wrong_results(expected):
    result=[];names=[name for name,table in expected['datasets'].items() if table['rows']]
    if names:
        table_name=names[-1]
        value=deepcopy(expected);table=value['datasets'][table_name];col=next(iter(table['schema']));row=table['rows'][0]
        row[col]=None if row[col] is not None else 0.;result.append(('missing',value))
        value=deepcopy(expected);table=value['datasets'][table_name]
        for col,item in table['rows'][0].items():
            if item is not None:
                table['rows'][0][col]=str(item) if type(item) is not str else 1.;break
        result.append(('type',value))
        if len(table['schema'])>1:
            value=deepcopy(expected);value['datasets'][table_name]['schema']=dict(reversed(list(value['datasets'][table_name]['schema'].items())));result.append(('column-order',value))
        if len(table['rows'])>1:
            value=deepcopy(expected);value['datasets'][table_name]['rows'].reverse();result.append(('row-order',value))
        value=deepcopy(expected);col=next(iter(value['datasets'][table_name]['schema']));value['datasets'][table_name]['schema'][col]['length']+=1;result.append(('descriptor',value))
    if expected.get('reports'):
        first=next(iter(expected['reports']))
        for mode in ('newline','title','value','basename'):
            value=deepcopy(expected)
            if mode=='newline':value['reports'][first]=value['reports'][first][:-1]
            elif mode=='title':value['reports'][first]='TITLE: Wrong\n'+value['reports'][first]
            elif mode=='value':value['reports'][first]=value['reports'][first].replace('1','9',1)
            else:value['reports']['other.txt']=value['reports'].pop(first)
            if not ordered_equal(value,expected):result.append((mode,value))
    return result


def complete_cli_controls(text,expected,accounting,contract):
    record=cli_check(text,expected,contract);counts=record['completeness']
    assert counts['status']=='recorded'
    assert (counts['n_statements'],counts['n_routed'],counts['n_unrouted'],counts['n_tickets'])==(
        accounting['language_statements']+accounting['opaque_payloads'],accounting['language_statements'],accounting['opaque_payloads'],0)
    wrong=wrong_results(expected)
    for label,value in wrong:
        assert not ordered_equal(value,expected),label
        cli_check(text,expected,contract,wrong=value)
    return len(wrong)
