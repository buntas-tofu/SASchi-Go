#!/usr/bin/env python3
"""Original counted DO pins and independent base-R witness, no live SAS."""
import csv
import io
import itertools
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sas_semantics import sas_do_counted
from saschi.plan import compile_plan
from saschi.runtime import run_plan

ORIGINAL_PROGRAM = """data counted; total=0; do I=5 to -1 by -2;
  total=total+i; seen=_n_; output; end; run;"""
PINS = [((1, 4, 1), ([1,2,3,4],5)), ((5,-1,-2), ([5,3,1,-1],-3)),
        ((2,2,3), ([2],5)), ((2,2,-3), ([2],-1)),
        ((4,1,1), ([],4)), ((1,4,-1), ([],1)),
        ((-3,2,2), ([-3,-1,1],3)),
        ((2147483647,2147483647,2147483647), ([2147483647],4294967294)),
        ((-2147483647,-2147483647,-2147483647), ([-2147483647],-4294967294))]
REFUSALS = [(1,2,0),(0,10000,1),(10000,0,-1),(2147483648,1,1),
            (1,-2147483648,-1),(1,2,2147483648),(1.5,2,1)]


def rrun(*args):
    rscript = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([rscript,str(HERE/'do_counted.R'),*map(str,args)],
                          check=True,capture_output=True,text=True,timeout=60).stdout


def main():
    for controls, expected in PINS:
        assert sas_do_counted(*controls) == expected, controls
    controls = [pin[0] for pin in PINS] + list(itertools.product(range(-4,5),range(-4,5),(-3,-2,-1,1,2,3)))
    controls += [(1,10000,1),(10000,1,-1)]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'controls.csv'
        with path.open('w',newline='') as stream:
            writer=csv.writer(stream); writer.writerow(['id','start','stop','by'])
            writer.writerows((i,*values) for i,values in enumerate(controls+REFUSALS))
        rows=list(csv.DictReader(io.StringIO(rrun('controls',path))))
    assert len(rows) == len(controls)+len(REFUSALS)
    for values,row in zip(controls,rows):
        indices,final=sas_do_counted(*values)
        assert row['count'] == str(len(indices)) and row['final'] == str(final), (values,row)
        assert row['values'] == '|'.join(map(str,indices)), (values,row)
    for values,row in zip(REFUSALS,rows[len(controls):]):
        try: sas_do_counted(*values)
        except ValueError: pass
        else: raise AssertionError(('must refuse',values))
        assert row['count'] == 'REFUSE', (values,row)
    plan=compile_plan(ORIGINAL_PROGRAM)
    assert not plan.blocked, plan.tickets
    result=run_plan(plan.to_dict())['datasets']['counted']
    witness=list(csv.DictReader(io.StringIO(rrun('program'))))
    expected=[{name:float(value) for name,value in row.items()} for row in witness]
    assert result['rows'] == expected, (result,expected)
    assert list(result['schema']) == ['total','i','seen']
    print(f'PASS: counted DO {len(controls)} R control cases, {len(REFUSALS)} refusals, original explicit-OUTPUT program')


if __name__ == '__main__':
    main()
