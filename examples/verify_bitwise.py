#!/usr/bin/env python3
"""DS-032 unsigned32 pins and independent base-R evidence, no live SAS."""
import csv
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from sas_semantics import sas_bitwise, SAS_BITWISE_ARITY

PINS=[('band',(3,5),1),('band',(0,4294967295),0),('band',(4294967295,2147483648),2147483648),
      ('bor',(3,5),7),('bor',(0,4294967295),4294967295),('bor',(2147483648,1),2147483649),
      ('bxor',(3,5),6),('bxor',(4294967295,4294967295),0),('bxor',(2147483648,1),2147483649),
      ('bnot',(0,),4294967295),('bnot',(4294967295,),0),('bnot',(2147483648,),2147483647),
      ('blshift',(3,2),12),('blshift',(1,31),2147483648),('blshift',(2147483648,1),0),
      ('blshift',(4294967295,1),4294967294),('blshift',(4294967295,31),2147483648),
      ('brshift',(12,2),3),('brshift',(4294967295,1),2147483647),('brshift',(4294967295,31),1),
      ('blshift',(2147483648,0),2147483648),('brshift',(2147483648,0),2147483648)]


def successes():
    result=list(PINS);rng=random.Random(3201)
    for _ in range(1000):
        a,b=rng.getrandbits(32),rng.getrandbits(32);shift=rng.randrange(32)
        result.extend([('band',(a,b),a&b),('bor',(a,b),a|b),('bxor',(a,b),a^b),
                       ('bnot',(a,),4294967295-a),('blshift',(a,shift),(a*2**shift)%2**32),
                       ('brshift',(a,shift),a//2**shift)])
    for value in (0,1,2147483647,2147483648,4294967295):
        for shift in range(32):
            result.extend([('blshift',(value,shift),(value*2**shift)%2**32),
                           ('brshift',(value,shift),value//2**shift)])
    return result


def refusals():
    result=[]
    bad=(None,{'missing':'A'},True,False,'3',-1,1.5,4294967296,10**400,float('nan'),float('inf'),float('-inf'))
    for name,arity in SAS_BITWISE_ARITY.items():
        for value in bad:
            result.append((name,(value,) if arity==1 else (value,0),None))
        if arity==2:
            for value in bad:
                result.append((name,(0,value),None))
        result.extend([(name,(),None),(name,(1,1,1),None)])
    result.extend((name,(1,value),None) for name in ('blshift','brshift') for value in (32,4294967295))
    result.append(('unsupported',(1,1),None))
    return result


def rrun(mode,path):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'bitwise.R'),mode,str(path)],capture_output=True,text=True,check=True,timeout=60).stdout


def program_state(path):
    lines=rrun('program',path).splitlines();header=lines[0].split('\t')
    if len(header)!=3 or header[0]!='WIDTH_REFUSED':raise AssertionError('independent width refusal missing')
    fields=[]
    for line in lines[1:]:
        tag,name,value=line.split('\t')
        if tag!='VALUE':raise AssertionError('unexpected witness state')
        fields.append({'name':name,'kind':'number','value':int(value)})
    assert len(fields)==int(header[2])
    return int(header[1]),fields


def kind(value):
    if isinstance(value,bool):return 'boolean'
    if isinstance(value,(int,float)):return 'number'
    if value is None:return 'missing'
    if isinstance(value,dict):return 'tagged'
    return 'text'


def main():
    good=successes();bad=refusals();cases=good+bad
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'cases.csv'
        with path.open('w',newline='') as handle:
            writer=csv.writer(handle);writer.writerow(['id','name','count','first_kind','first','second_kind','second'])
            for i,(name,args,_) in enumerate(cases):
                a=args[0] if args else None;b=args[1] if len(args)>1 else None
                writer.writerow([i,name,len(args),kind(a),str(a),kind(b),str(b)])
        rows=rrun('cases',path).splitlines()
    assert len(rows)==len(cases)
    for i,((name,args,expected),row) in enumerate(zip(cases,rows)):
        if i<len(good):
            assert sas_bitwise(name,*args)==expected,(i,name)
            assert row==str(i)+':OK:'+str(expected),(i,row)
        else:
            try:sas_bitwise(name,*args)
            except ValueError:pass
            else:raise AssertionError(('missing refusal',i,name))
            assert row==str(i)+':REFUSE',(i,row)
    assert ~0!=PINS[9][2] # Unbounded Python NOT is not unsigned32 NOT.
    assert 2147483648<<1!=PINS[14][2] # Left overflow is discarded.
    assert -1>>1!=PINS[18][2] # Signed right shift is not uint32 logical shift.
    assert (1<<30)!=PINS[13][2] # Shift count is exact, with no off-by-one.
    print(f'VERIFIED: uint32 bitwise {len(PINS)} pins, {len(good)-len(PINS)} generated/boundary cases, '
          f'{len(bad)} shared typed/range/arity refusals, 4 naive errors caught; independent32-bit-vector base R; no live SAS')


if __name__=='__main__':main()
