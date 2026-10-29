"""DS-046 numeric output discovery, independent PDV schedules and controls."""
import contextlib
import csv
import io
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from saschi.emit_py import translate
from saschi.plan import compile_plan
from saschi.runtime import run_plan


def source(value,mode='skip'):
    prefix={'skip':'if 0 then put c d;', 'direct':'put c d;',
            'zero':'do i=1 to 0;put c d;end;',
            'else':'if 1 then output;else put c d;'}[mode]
    return f'data d;a={"." if value is None else value};{prefix}output;c=a+1;put a c d;output;run;'


def execute(text):
    plan=compile_plan(text)
    if plan.blocked:raise AssertionError(plan.tickets)
    runtime=run_plan(plan.to_dict());ns={};stream=io.StringIO()
    with contextlib.redirect_stdout(stream):exec(translate(text).code,ns)
    assert ns['result']==runtime
    return runtime,stream.getvalue()


def main():
    rng=random.Random(4601)
    cases=[(i,None if i%7==0 else rng.randint(-10000,10000),mode)
           for i,mode in enumerate(mode for mode in ('skip','direct','zero','else') for _ in range(100))]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'cases.csv'
        with path.open('w',newline='') as f:
            writer=csv.writer(f);writer.writerow(['id','a','mode'])
            writer.writerows((i,'.' if value is None else value,mode) for i,value,mode in cases)
        r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        run=subprocess.run([r,str(HERE/'numeric_discovery.R'),str(path)],check=True,capture_output=True,text=True,timeout=60)
    records=list(csv.reader(io.StringIO(run.stdout),delimiter='\t'));assert len(records)==len(cases)
    for (i,value,mode),record in zip(cases,records):
        result,stdout=execute(source(value,mode));table=result['datasets']['d']
        ident,names,first,last,count,logs,*tail=record
        assert ident==str(i) and list(table['schema'])==names.split(',')
        def row(values):return {name:None if x=='.' else float(x) for name,x in zip(names.split(','),values.split(','))}
        expected=[row(first)]*(int(count)-1)+[row(last)]
        assert table['rows']==expected and result['log']==logs.split('|'),(i,mode,result,record)
        assert all(x=='number' for x in table['schema'].values())
        assert stdout=='\n'.join(result['log'])+'\n'
    # Hand pins distinguish missing from zero and preserve static snapshot columns.
    pins=[('data d;put c;run;',{'datasets':{'d':{'schema':{'c':'number'},'rows':[{'c':None}]}},'log':['. ']}),
          ('data d;if 0 then put c;run;',{'datasets':{'d':{'schema':{'c':'number'},'rows':[{'c':None}]}},'log':[]}),
          ('data d;output;put c;run;',{'datasets':{'d':{'schema':{'c':'number'},'rows':[{'c':None}]}},'log':['. ']}),
          ('data d;put c c;run;',{'datasets':{'d':{'schema':{'c':'number'},'rows':[{'c':None}]}},'log':['. . ']})]
    for text,expected in pins:assert execute(text)[0]==expected
    assert execute('data _null_;put '+' '.join('v'+str(i) for i in range(32))+';run;')[1]=='. '*32+'\n'
    for text in ('data d;put _n_;run;', 'data d;put _error_;run;',
                 'data d;put "x" c;run;', 'data d;length a $3;put a c;run;',
                 'data d;put '+ ' '.join('v'+str(i) for i in range(33))+';run;',
                 'data d;put \u212a;run;'):
        assert compile_plan(text).blocked,text
    correct=execute('data d;put c;run;')[0]
    assert correct['datasets']['d']['rows']!=[{'c':0.}]
    assert correct['log']!=['0 '] and correct['log']!=['.']
    assert execute('data d;if 0 then put c;run;')[0]['datasets']['d']['schema']!={}
    print('VERIFIED: numeric discovery4 hand pins,400 independent base-R/source/runtime/emitted schedules,6 source refusals,4 naive controls; no live SAS')


if __name__=='__main__':main()
