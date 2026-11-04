#!/usr/bin/env python3
"""Original DATE9/nested-date logical reports, independently witnessed in base R."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from saschi.compare import equal, table_equal

PINS = {'date_profile.sas':'db41926205efcc89bf2b49a7d69f40fcb850dd34bba913a2bde7107516da4f2f',
        'date_profile.R':'238e60d62348c016b8c91dd19d6b3397c91d13b002b0412f8a637d9554552542',
        'date_profile_expected.json':'d196d1d317ddcb859fe13f872f356c2748dc313dffc850a176d03fc882237524'}


def source(records):
    original = (HERE/'date_profile.sas').read_text()
    before, payload = original.split('\ncards;\n',1)
    _, after = payload.split('\n;\n',1)
    return before+'\ncards;\n'+('\n'.join(records)+'\n' if records else '')+';\n'+after


def witness(text):
    with tempfile.TemporaryDirectory(prefix='saschi-date-profile-r-') as temporary:
        directory=Path(temporary);path=directory/'original.sas';path.write_text(text)
        executable=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        subprocess.run([executable,str(HERE/'date_profile.R'),str(path),str(directory/'out')],
                       check=True,capture_output=True,text=True,timeout=120)
        number=lambda token:None if token=='M' else float(token)
        rows=[]
        for line in (directory/'out'/'rows.txt').read_text().splitlines():
            a,b,c,d,e=line.split('|')
            rows.append(dict(id=number(a),sex=b,amount=number(c),born=number(d),hired=number(e)))
        schema=json.loads((HERE/'date_profile_expected.json').read_text())['datasets']['dates']['schema']
        result={'datasets':{'dates':{'schema':schema,'rows':rows}},'log':[],
                'reports':{'print_01.txt':(directory/'out'/'print_01.txt').read_text()}}
        accounting=[int(value) for value in (directory/'out'/'accounting.txt').read_text().strip().split('|')]
    return result,accounting


def qualified_cases():
    for name,pin in PINS.items():
        assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==pin,('preimplementation original oracle pin differs',name)
    text=(HERE/'date_profile.sas').read_text();hand=json.loads((HERE/'date_profile_expected.json').read_text())
    actual,accounting=witness(text)
    assert equal(actual,hand,ordered_maps=True),'independent original hand/R qualification failed'
    assert accounting==[13,1,4,3,5,1],accounting
    cases=[(text,hand,accounting)]
    date_pairs=[('01JAN1753','31DEC3999'),('31DEC1959','01JAN1960'),('31DEC1999','01JAN2000'),
                ('28FEB1900','01MAR1900'),('29FEB2000','01MAR2000'),('.','.'),('01jan1960','16mar2012')]
    cases.append((source([]),*witness(source([]))))
    boundary=[f'{i} F -{i} {a} {b}' for i,(a,b) in enumerate(date_pairs,1)]
    cases.append((source(boundary),*witness(source(boundary))))
    rng=random.Random(8013)
    for _ in range(14):
        records=[]
        for i in range(rng.randrange(1,35)):
            a,b=rng.choice(date_pairs)
            records.append(f'{i} {rng.choice("FM")} {rng.choice([".","-2147483647","+2147483647","0"])} {a} {b}')
        text=source(records);cases.append((text,*witness(text)))
    text=source(['1 F . . 01JAN1960']*1000);cases.append((text,*witness(text)))
    return cases


def cli(text, truth, *, wrong=None):
    with tempfile.TemporaryDirectory(prefix='saschi-date-profile-cli-') as temporary:
        directory=Path(temporary);path=directory/'original.sas';path.write_text(text)
        expected=truth if wrong is None else wrong
        for name,value in [('tables',expected['datasets']),('reports',expected['reports']),('log',expected['log'])]:
            (directory/(name+'.json')).write_text(json.dumps(value))
        run=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--expect',str(directory/'tables.json'),
                            '--expect-reports',str(directory/'reports.json'),'--expect-log',str(directory/'log.json'),
                            '--output',str(directory/'job')],cwd=ROOT,capture_output=True,text=True,timeout=120)
        receipt=json.loads((directory/'job'/'receipt.json').read_text())
        assert run.returncode==(0 if wrong is None else 1),(run.stderr,receipt)
        assert receipt['accepted']==(wrong is None)
        if wrong is None:
            assert receipt['comparison']==receipt['report_comparison']==receipt['log_comparison']=='passed'
            assert receipt['report_contract']=='ascii-date-fields-v1'
            result=json.loads((directory/'job'/'result.json').read_text())
            assert equal(result,truth,ordered_maps=True)
            for name,text in truth['reports'].items():assert (directory/'job'/'reports'/name).read_bytes()==text.encode('ascii')
        else:
            assert not (directory/'job'/'result.json').exists()
            assert not (directory/'job'/'reports').exists(),'failed comparison published report artifacts'
        return receipt


def wrong_cases(truth):
    result=[]
    for mode in ('epoch','missing','descriptor-order','row-order','date-type','range','weekday','alignment','newline','report-set'):
        wrong=deepcopy(truth);table=wrong['datasets']['dates'];reports=wrong['reports']
        if mode=='epoch':table['rows'][0]['born']=3652.
        elif mode=='missing':table['rows'][2]['born']=0.
        elif mode=='descriptor-order':table['schema']=dict(reversed(list(table['schema'].items())))
        elif mode=='row-order':table['rows'].reverse()
        elif mode=='date-type':table['rows'][1]['born']='0'
        elif mode=='range':reports['print_01.txt']=reports['print_01.txt'].replace('January 1, 1960','New era')
        elif mode=='weekday':reports['print_01.txt']=reports['print_01.txt'].replace('Thursday','Friday')
        elif mode=='alignment':reports['print_01.txt']=reports['print_01.txt'].replace('"January','"  January')
        elif mode=='newline':reports['print_01.txt']=reports['print_01.txt'][:-1]
        else:reports['print_02.txt']=reports['print_01.txt']
        assert not equal(wrong,truth,ordered_maps=True),mode
        result.append((mode,wrong))
    return result


def main():
    cases=qualified_cases()
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    from saschi.emit_py import translate
    from saschi.date_program import run_program
    from saschi.job import build_job
    for text,expected,accounting in cases:
        plan=compile_plan(text);assert not plan.blocked,plan.tickets
        actual=run_plan(plan.to_dict());assert equal(actual,expected,ordered_maps=True),'whole original runtime differs'
        emitted=translate(text);namespace={};exec(compile(emitted.code,'<date-profile>','exec'),namespace)
        assert equal(namespace['result'],expected,ordered_maps=True),'emitted date program differs'
        trace=[];run_program(plan.to_dict(),trace=trace)
        attempts=[item for item in trace if type(item) is dict and item.get('kind')=='date_input']
        outputs=[item for item in trace if type(item) is dict and item.get('kind')=='date_output']
        assert [accounting[2],accounting[3],accounting[4]]==[len(attempts),len(outputs),len(plan.steps)]
        assert attempts[-1]['complete'] is False
    text,truth,_=cases[0];receipt=cli(text,truth)
    counts=receipt['completeness'];assert counts['status']=='recorded'
    assert (counts['n_statements'],counts['n_routed'],counts['n_unrouted'],counts['n_tickets'])==(14,13,1,0)
    for mode,wrong in wrong_cases(truth):
        if mode in ('epoch','missing','descriptor-order','row-order','date-type'):
            assert not table_equal(truth['datasets']['dates'],wrong['datasets']['dates']),mode
        cli(text,truth,wrong=wrong)
    assert build_job(text).receipt['comparison']=='not requested'
    print(f'VERIFIED: original DATE9/nested-date profile, {len(cases)} complete independent R cases, '
          'runtime/emitted/CLI, complete report and typed table comparisons,10 wrong controls; H11 held, no vendor or live SAS proof')


if __name__=='__main__':main()
