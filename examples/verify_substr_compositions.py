#!/usr/bin/env python3
"""Complete runtime/Python/base-R composition evidence, no live SAS claim."""
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
from saschi.plan import compile_plan
from saschi.runtime import run_plan

MODES=('stored-reverse','stored-concat','stored-catx','catx-substr','substr-reverse-source','substr-concat-source')
# mode, source, source width, position, size, stored target width (0=new), tail, delimiter.
PINS=[('stored-reverse','abcde',5,2,3,0,'Q','|','  dcb'),
      ('stored-concat','abcde',5,2,3,0,'Q','|','bcd  Q'),
      ('stored-reverse','abcde',8,2,3,2,'Q','|','cb'),
      ('stored-catx',' aZ  ',5,2,3,0,'Q',' / ','aZ / Q'.ljust(200)),
      ('catx-substr',' aZ  ',5,2,3,0,'Q',' / ','aZ / Q'.ljust(200)),
      ('catx-substr','    ',4,2,2,0,'Q','|','Q'.ljust(200)),
      ('substr-reverse-source','aZ',5,3,2,0,'Q','|',' Z   '),
      ('substr-concat-source','AB',4,4,2,0,'QZ','|',' Q    ')]


def literal(value): return "'"+value.replace("'","''")+"'"


def program(case):
    mode,value,width,start,size,target,tail,delimiter=case
    declaration=f'length a ${width}; '+(f'length x ${target}; ' if target else '')
    source=f'data d; {declaration} a={literal(value)}; '
    expr=f'substr(a,{start},{size})'
    if mode.startswith('stored-'):
        source+=f'x={expr}; '
        rhs={'stored-reverse':'reverse(x)','stored-concat':f'x!!{literal(tail)}','stored-catx':f'catx({literal(delimiter)},x,{literal(tail)})'}[mode]
    elif mode=='catx-substr': rhs=f'catx({literal(delimiter)},{expr},{literal(tail)})'
    elif mode=='substr-reverse-source': rhs=f'substr(reverse(a),{start},{size})'
    elif mode=='substr-concat-source': rhs=f'substr(a!!{literal(tail)},{start},{size})'
    else: raise AssertionError(mode)
    return source+f'result={rhs}; run;'


def execute(case):
    plan=compile_plan(program(case))
    assert not plan.blocked,plan.tickets
    table=run_plan(plan.to_dict())['datasets']['d']
    return table['schema']['result']['length'],table['rows'][0]['result']


def main():
    rng=random.Random(3101);cases=[pin[:-1] for pin in PINS]
    for i in range(1000):
        mode=MODES[i%len(MODES)];width=rng.randrange(1,41)
        source=''.join(rng.choice(' abZ09') for _ in range(rng.randrange(1,width+1)))
        tail=''.join(rng.choice(' QR0') for _ in range(rng.randrange(1,8)))
        extent=width+len(tail) if mode=='substr-concat-source' else width
        start=rng.randrange(1,extent+1);size=rng.randrange(1,extent-start+2)
        target=rng.choice((0,1,3,50)) if mode.startswith('stored-') else 0
        cases.append((mode,source,width,start,size,target,tail,rng.choice(('|',' / ',' '))))
    cases += [('stored-reverse','x',32767,32767,1,0,'Q','|'),
              ('stored-concat','x',32766,1,1,0,'Q','|')]
    accepted=len(cases)
    cases += [('catx-substr','abc',3,3,2,0,'Q','|'),('substr-reverse-source','a',3,0,1,0,'Q','|'),
              ('substr-concat-source','a',2,4,1,0,'Q','|'),('stored-concat','x',32767,1,1,0,'Q','|'),
              ('catx-substr','x'*100,100,1,100,0,'y'*100,'|'),('stored-reverse','é',1,1,1,0,'Q','|')]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'cases.tsv'
        with path.open('w',newline='') as handle:
            writer=csv.writer(handle,delimiter='\t');writer.writerow(['id','mode','source','source_width','position','length','target_width','tail','delimiter'])
            for i,(mode,value,width,start,size,target,tail,delimiter) in enumerate(cases):
                writer.writerow([i,mode,value.encode().hex(),width,start,size,target,tail.encode().hex(),delimiter.encode().hex()])
        r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        output=subprocess.run([r,str(HERE/'substr_compositions.R'),str(path)],capture_output=True,text=True,check=True,timeout=60).stdout
        records=list(csv.DictReader(io.StringIO(output)))
    assert len(records)==len(cases)
    for i,(case,row) in enumerate(zip(cases,records)):
        if i>=accepted:
            try:execute(case)
            except (ValueError,AssertionError):pass
            else:raise AssertionError(('missing runtime refusal',i))
            assert row['status']=='REFUSED',(i,row)
        else:
            width,value=execute(case)
            assert row['status']=='OK' and width==int(row['width']) and value.encode().hex()==row['result'],(i,case,row)
            if i<len(PINS):assert value==PINS[i][-1],(i,value)
    assert PINS[0][-1]!='bcd'[::-1] # Wrong extraction-count target width.
    assert PINS[1][-1]!='bcdQ' # Trimming before operator concatenation.
    assert PINS[0][-1]!='dcb  ' # Reversing raw temporary is not reversing a stored value.
    print('VERIFIED: SUBSTR compositions 8 pins, 1000 generated complete-runtime/R cases, 2 width boundaries, 6 shared refusals, 3 naive errors caught; CATX raw/padded models agree; no live SAS')


if __name__=='__main__':main()
