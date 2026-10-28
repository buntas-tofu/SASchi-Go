"""DS-040 native-R complete row snapshots and bounded schedules, no live SAS."""
import csv
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_do_over
from saschi.plan import compile_plan
from saschi.runtime import run_plan


def rrun(*args):
    r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r, str(HERE/'do_over.R'), *map(str,args)],
                          capture_output=True, text=True, check=True, timeout=60).stdout


def program_records(path):
    state, record = rrun('program',path).splitlines()
    assert state == 'STATE:11:1|2|3|4|5|6|7|8|9|10:55'
    assert record.startswith('RECORD:')
    return [bytes.fromhex(record[7:]).decode('ascii')]


def main():
    sizes = [1,2,7,1024,0,-1,1025,.5]
    records = rrun('sizes',','.join(map(str,sizes))).splitlines()
    for size,record in zip(sizes,records):
        offsets=[]
        if type(size) is not int or not 1<=size<=1024:
            try: sas_do_over(size,offsets.append)
            except ValueError: pass
            else: raise AssertionError('missing size refusal')
            assert record=='REFUSE' and not offsets
        else:
            assert sas_do_over(size,offsets.append)==size
            assert offsets==list(range(size))==list(map(int,record.split('|')))
    assert len(records)==len(sizes)
    # Reverse-order alias pin: direct x1 writes are visible when x1 is current.
    cases=[([2.,5.],[2,1],3.),([None,4.],[1,2],-2.)]
    rng=random.Random(4001)
    for _ in range(200):
        n=rng.randrange(1,9); order=list(range(1,n+1));rng.shuffle(order)
        cases.append(([None if rng.randrange(5)==0 else rng.randint(-1000,1000)/8 for _ in range(n)],order,rng.randint(-20,20)/8))
    cases.append(([0.]*1024,list(range(1024,0,-1)),1.))
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'cases.csv'
        with path.open('w',newline='') as stream:
            w=csv.writer(stream);w.writerow(['id','values','order','delta'])
            for i,(values,order,delta) in enumerate(cases):
                w.writerow([i,'|'.join('NA' if x is None else str(x) for x in values),'|'.join(map(str,order)),delta])
        records=rrun('cases',path).splitlines()
    expected={i:[] for i in range(len(cases))}
    for record in records:
        case,trip,values=record.split(':');case=int(case)
        assert int(trip)==len(expected[case])+1
        expected[case].append([None if x=='M' else float(x) for x in values.split('|')])
    for i,(values,order,delta) in enumerate(cases):
        names=['x'+str(n) for n in range(1,len(values)+1)]
        source=('data d; set raw; array a '+' '.join('x'+str(n) for n in order)+'; '
                'do over a; before=a; a=a+delta; x1=x1+1; after=a; output; end; final=sum(of a[*]); run;')
        columns=names+['delta','before','after','final']
        raw={'schema':dict.fromkeys(names+['delta'],'number'),'rows':[dict(zip(names+['delta'],values+[delta]))]}
        p=compile_plan(source);assert not p.blocked,p.tickets
        result=run_plan(p.to_dict(),{'raw':raw})
        table={'schema':dict.fromkeys(columns,'number'),'rows':[dict(zip(columns,row)) for row in expected[i]]}
        assert result=={'datasets':{'raw':raw,'d':table},'log':[]},i
    assert expected[0]==[[3.,8.,3.,5.,8.,None],[7.,8.,3.,3.,7.,None]]
    assert expected[1]==[[None,4.,-2.,None,None,None],[None,2.,-2.,4.,2.,None]]
    assert expected[0][1][-2]!=6, 'copied-current-value control must differ'
    assert expected[0][0][1]!=5, 'copy-only write control must differ'
    assert expected[0][0][-3]!=2, 'reversed iteration control must differ'
    print(f'VERIFIED: DO OVER2 hand-pinned snapshot sequences,{len(cases)-2} generated complete-runtime/R cases; '
          '8 size controls,3 wrong-alias/order controls; no live SAS')


if __name__=='__main__': main()
