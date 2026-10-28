"""Original A2 full-program pins and independent base-R schedules."""
import csv
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_counted_capture
from saschi.plan import compile_plan
from saschi.runtime import run_plan

PROGRAM = HERE / 'counted_capture.sas'
CASE_PROGRAM = '''data d; set raw; total=0;
do i=lo to hi by inc;
  lo=99; hi=-99; inc=7;
  do j=i+offset to i+span by stride;
    total=total+j; offset=offset+1; tick=_n_; output;
  end;
end;
after=i; inner_after=j; output;
run;'''
INPUTS = ['lo', 'hi', 'inc', 'offset', 'span', 'stride']
COLUMNS = INPUTS + ['total', 'i', 'j', 'tick', 'after', 'inner_after']


def rrun(*args):
    r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r, str(HERE / 'counted_nested.R'), *map(str, args)],
                          check=True, capture_output=True, text=True, timeout=60).stdout


def hand_result():
    names = ['first','second','third','start','finish','stride','total','i','j','before','seen','after','inner_after']
    # Five visited pairs (1,1),(1,2),(1,3),(2,2),(3,3), then final OUTPUT.
    rows = [
        [1,None,None,9,0,-1,1,1,1,None,1,None,None],
        [1,1,None,9,0,-1,2,1,2,None,1,None,None],
        [1,1,1,9,0,-1,3,1,3,None,1,None,None],
        [1,3,1,9,0,-1,5,2,2,1,1,None,None],
        [1,3,4,9,0,-1,8,3,3,1,1,None,None],
        [1,3,4,9,0,-1,8,4,6,1,1,4,6],
    ]
    return {'datasets': {'capture': {'schema': dict.fromkeys(names, 'number'),
            'rows': [dict(zip(names, [None if v is None else float(v) for v in row])) for row in rows]}},
            'log': ['total=8 i=4 j=6']}


def program_witness():
    records = rrun('program').splitlines()
    assert records.pop() == 'LOG:total=8 i=4 j=6'
    return [{k: float(v) if v else None for k,v in row.items()}
            for row in csv.DictReader(records)]


def main():
    pins = [((1.,3.,1.,0), ([1,2,3],4,3)),
            ((3.,-1.,-2.,2), ([3,1,-1],-3,5)),
            ((4.,1.,1.,10000), ([],4,10000)),
            ((2147483647.,2147483647.,2147483647.,9999), ([2147483647],4294967294,10000))]
    for controls, expected in pins:
        assert sas_counted_capture(*controls) == expected
    controls = [c for c,_ in pins] + [(*c,s) for c in itertools.product(range(-2,3), range(-2,3), (-2,-1,1,2)) for s in (0,9999)]
    controls += [(1,10000,1,0),(1,10000,1,1),(1,2,0,0),(1.5,2,1,0),
                 (2147483648,2,1,0),(1,2,1,-1),(1,2,1,1.5),(1,2,1,10001)]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'controls.csv'
        with path.open('w',newline='') as stream:
            w=csv.writer(stream);w.writerow(['start','stop','by','spent']);w.writerows(controls)
        records=rrun('controls',path).splitlines()
        assert len(records)==len(controls)
        for n,(case,record) in enumerate(zip(controls,records)):
            assert record.startswith(str(n)+':')
            record=record.partition(':')[2]
            try: values,final,spent=sas_counted_capture(*case)
            except ValueError:
                assert record=='REFUSE',(case,record)
            else:
                assert record==f'{len(values)}:{final}:{spent}:'+ '|'.join(map(str,values)),(case,record)
        cases=[(1,2,1,0,1,1),(3,1,-1,1,0,-1),(2,1,1,0,0,1)]
        rng=random.Random(4102)
        cases += [(rng.randint(-2,2),rng.randint(-2,2),rng.choice((-2,-1,1,2)),
                   rng.randint(-2,2),rng.randint(-2,2),rng.choice((-2,-1,1,2))) for _ in range(300)]
        path=Path(directory)/'cases.csv'
        with path.open('w',newline='') as stream:
            w=csv.writer(stream);w.writerow(INPUTS);w.writerows(cases)
        rows=list(csv.DictReader(io.StringIO(rrun('cases',path))))
    expected={n:[] for n in range(len(cases))}
    for row in rows:
        expected[int(row.pop('case'))].append({k:float(v) if v else None for k,v in row.items()})
    plan=compile_plan(CASE_PROGRAM);assert not plan.blocked,plan.tickets
    for n,case in enumerate(cases):
        raw={'schema':dict.fromkeys(INPUTS,'number'),'rows':[dict(zip(INPUTS,map(float,case)))]}
        actual=run_plan(plan.to_dict(),{'raw':raw})
        assert actual=={'datasets':{'raw':raw,'d':{'schema':dict.fromkeys(COLUMNS,'number'),'rows':expected[n]}},'log':[]},n
    # These pins also distinguish captured controls from reevaluation in the body.
    assert [(r['i'],r['j'],r['total']) for r in expected[0]]==[(1,1,1),(1,2,3),(3,4,3)]
    assert expected[2][0]['i']==2 and expected[2][0]['j'] is None
    original=compile_plan(PROGRAM.read_text());assert not original.blocked,original.tickets
    result=run_plan(original.to_dict());assert result==hand_result()
    assert result['datasets']['capture']['rows']==program_witness()
    print(f'VERIFIED: counted A2 4 hand control pins,{len(controls)} independent R control/budget cases,'
          f'{len(cases)} complete-runtime/R schedules,original six-snapshot nested alias program; no live SAS')


if __name__=='__main__': main()
