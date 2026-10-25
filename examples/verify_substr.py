#!/usr/bin/env python3
"""DS-030 bounded source-width assignment, original Python/base-R evidence."""
import csv
import io
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from sas_semantics import sas_substr_checked, sas_substr, sas_length, sas_lengthn, sas_count
from saschi.plan import compile_plan
from saschi.runtime import run_plan

# source, position, count, target width (0 means new), raw, stored.
PINS = [('abcde',2,3,0,'bcd','bcd  '), ('abcde',1,1,0,'a','a    '),
        ('abcde',5,1,0,'e','e    '), (' aZ  ',2,3,0,'aZ ','aZ   '),
        ('    ',2,2,0,'  ','    '), ('abcde',2,3,2,'bcd','bc'),
        ('abcde',2,3,7,'bcd','bcd    '), ('Z  ',1,1,0,'Z','Z  ')]
REFUSALS = [(value,1,1) for value in ('',None,7,True,{'missing':'A'},'é','a\tb','a\nb','a\x00b','x'*32768)]
REFUSALS += [('abc',value,1) for value in (0,-1,1.5,None,True,'1',{'missing':'A'},float('nan'),float('inf'),32768)]
REFUSALS += [('abc',1,value) for value in (0,-1,1.5,None,True,'1',float('nan'),float('inf'),32768)]
REFUSALS += [('abc',3,2),('abc',4,1)]


def token(value):
    if isinstance(value,str): return 'S:'+value.encode('utf-8').hex()
    if isinstance(value,bool): return 'B:'+str(value)
    if isinstance(value,(int,float)): return 'N:'+str(value)
    return 'M:'


def main():
    rng=random.Random(300)
    cases=[pin[:4] for pin in PINS]
    for _ in range(1000):
        source=''.join(chr(rng.randrange(32,127)) for _ in range(rng.randrange(1,81)))
        start=rng.randrange(1,len(source)+1); size=rng.randrange(1,len(source)-start+2)
        cases.append((source,start,size,rng.choice((0,1,3,90))))
    cases.append(('x'*32767,32767,1,0))
    accepted=len(cases)
    cases += [(*case,0) for case in REFUSALS]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'cases.tsv'
        with path.open('w',newline='') as handle:
            writer=csv.writer(handle,delimiter='\t');writer.writerow(['id','source','position','length','target'])
            for i,(source,start,size,width) in enumerate(cases): writer.writerow([i,token(source),token(start),token(size),width])
        r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        output=subprocess.run([r,str(HERE/'substr.R'),str(path)],capture_output=True,text=True,check=True,timeout=60).stdout
        rows=list(csv.DictReader(io.StringIO(output)))
    assert len(rows)==len(cases)
    for i,((source,start,size,width),row) in enumerate(zip(cases,rows)):
        if i>=accepted:
            try: sas_substr_checked(source,start,size)
            except ValueError: pass
            else: raise AssertionError('unsupported SUBSTR input accepted')
            assert row['status']=='REFUSED',(i,row)
            continue
        raw=sas_substr_checked(source,start,size); stored=raw.ljust(width or len(source))[:width or len(source)]
        assert row['status']=='OK' and int(row['width'])==len(source),(i,row)
        assert raw.encode().hex()==row['raw'] and stored.encode().hex()==row['stored'],i
        assert [sas_length(raw),sas_lengthn(raw),sas_count(raw,'Z'),int(raw.rstrip(' ')=='Z')]==[
            int(row[key]) for key in ('length','lengthn','count','compare')],i
        if i<len(PINS): assert (raw,stored)==PINS[i][4:]
    source="data d; length a $8; length b $2; a='abcde'; x=substr(a,2,3); b=substr(a,2,3); n=lengthc(x); run;"
    plan=compile_plan(source);assert not plan.blocked,plan.tickets
    table=run_plan(plan.to_dict())['datasets']['d']
    assert table['schema']['x']=={'type':'character','length':8}
    assert table['rows']==[{'a':'abcde   ','b':'bc','x':'bcd     ','n':8.}]
    naive=[lambda s,p,n:s[p-1:p-1+n],lambda s,p,n:s[p:p+n].ljust(len(s)),
           lambda s,p,n:s.strip()[p-1:p-1+n].ljust(len(s))]
    assert all(any(fn(s,p,n)!=stored for s,p,n,w,raw,stored in PINS if w==0) for fn in naive)
    assert sas_substr('abc',3,2)=='c' # Old extraction-only fixture is not executable error-state evidence.
    try: sas_substr_checked('abc',3,2)
    except ValueError: pass
    else: raise AssertionError('unchecked overrun naive error escaped')
    print(f'VERIFIED: SUBSTR {len(PINS)} pins, 1000 generated cases, max-width boundary, {len(REFUSALS)} shared refusals, 4 naive errors caught; independent base R; no live SAS')


if __name__=='__main__': main()
