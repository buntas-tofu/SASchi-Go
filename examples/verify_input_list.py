"""DS-044 numeric parsing and physical-record scheduling, independent base R."""
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
from sas_semantics import sas_input_number, sas_input_records
from saschi.plan import compile_plan
from saschi.runtime import run_plan

ORIGINAL=HERE/'input_capture.sas'
PINS=[([],2,[]),([''],2,[]),(['1 2'],2,[[1.,2.]]),
      (['1','2 99','3 4'],2,[[1.,2.],[3.,4.]]),
      (['1 2 3 4','5 6'],2,[[1.,2.],[5.,6.]]),
      (['  ','1','  ','2','3'],2,[[1.,2.]]),
      (['. 2','3 .'],2,[[None,2.],[3.,None]]),
      (['+1.25 -2.5','5e-1 2E+2'],2,[[1.25,-2.5],[.5,200.]]),
      (['-0 +.0'],2,[[0.,0.]]),
      (['2147483647 -2147483647'],2,[[2147483647.,-2147483647.]]),
      (['1 ignored','2 /*not-code*/'],1,[[1.],[2.]]),
      (['7'],2,[])]
BAD_TOKENS=['x','.A','._','NaN','Inf','1,000','0x10','1_0','"1"','0.1','1e-15',
            '2147483648','-2147483648','1e16','1e-16','1234567890123456','+' ,'-','..','1d2']
REFUSALS=[([token],1) for token in BAD_TOKENS]+[(['1\t2'],2),(['é'],1),(['1'*81],1),(['1;'],1)]


def source(records,names=('a','b'),body='',header='datalines',prefix=''):
    return 'data d;'+prefix+'input '+' '.join(names)+';'+body+header+';\n'+''.join(r+'\n' for r in records)+';\nrun;'


def rrun(*args):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'input_list.R'),*map(str,args)],capture_output=True,
                          text=True,check=True,timeout=60).stdout


def program_witness(path):
    result={'datasets':{},'log':[]};steps=[];reads=[];schema=[];table=None
    lines=rrun('program',path).splitlines()
    for line in lines[1:]:
        tag,value=line.split(':',1)
        if tag=='STEP':
            steps.append(value);table={'schema':{},'rows':[]}
            if value!='_null_':result['datasets'][value]=table
        elif tag=='SCHEMA':
            schema=value.split(',');table['schema']={n:'number' for n in schema}
        elif tag=='READS':reads.append(int(value))
        elif tag=='ROW':table['rows'].append(dict(zip(schema,[None if x=='.' else float(x) for x in value.split(',')])))
        elif tag=='LOG':result['log'].append(bytes.fromhex(value).decode('ascii'))
        else:raise AssertionError(line)
    return result,{'statements':int(lines[0].split(':')[1]),'steps':steps,'reads':reads}


def original_expected():
    names=['total','a','b','before','scratch','seq']
    values=[[1,1,2,None,1,1],[1,99,2,None,1,1],
            [1,None,5,None,None,2],[1,99,5,None,None,2],[5,4,None,None,None,3]]
    return {'datasets':{'capture':{'schema':{n:'number' for n in names},
             'rows':[dict(zip(names,[float(v) if v is not None else None for v in row])) for row in values]}},
            'log':['total=1 seq=1','total=1 seq=2','total=5 seq=3']}


def comparison_expected():
    # Hand truth table, preserving every distinct source operator spelling.
    labels=[['^=','~=','<','<=','ne','lt','le'],['^=','~=','>','>=','ne','gt','ge'],
            ['=','<=','>=','eq','le','ge']]
    log=[]
    for (a,b),operators in zip([(1,2),(2,1),(1,1)],labels):
        log.append(f'a={a} b={b}');log.extend('a '+op+' b' for op in operators)
    return {'datasets':{},'log':log}


def main():
    cases=list(PINS);rng=random.Random(4401)
    for _ in range(600):
        width=rng.randint(1,4);expected=[];records=[]
        for _ in range(rng.randint(1,6)):
            values=[None if rng.randrange(5)==0 else rng.randint(-200,200)/4 for _ in range(width)]
            expected.append(values)
            tokens=['.' if v is None else str(v) for v in values]
            # Construct known observations before randomly breaking physical lines.
            for k in range(width-1):
                if rng.randrange(2):records.append(' '*rng.randrange(3)+tokens.pop(0))
                else:break
            records.append('  '.join(tokens)+' unread')
            if rng.randrange(2):records.append(' ')
        if width>1:records.append('7')  # Incomplete EOF never emits a row.
        cases.append((records,width,expected))
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'cases.csv'
        with path.open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['records','count','width'])
            for records,width,_ in cases+[(r,w,None) for r,w in REFUSALS]:
                writer.writerow([':'.join(r.encode().hex() for r in records),len(records),width])
        observed=rrun('cases',path).splitlines()
    assert len(observed)==len(cases)+len(REFUSALS)
    for (records,width,expected),line in zip(cases,observed):
        assert sas_input_records(records,width)==expected
        encoded='|'.join(','.join('.' if v is None else format(v,'.17g') for v in row) for row in expected)
        assert line=='OK:'+encoded,(records,line,encoded)
        names=[f'x{i}' for i in range(width)]
        plan=compile_plan(source(records,names));assert not plan.blocked,plan.tickets
        table=run_plan(plan.to_dict())['datasets']['d']
        assert table=={'schema':{n:'number' for n in names},'rows':[dict(zip(names,row)) for row in expected]}
    for (records,width),line in zip(REFUSALS,observed[len(cases):]):
        try:sas_input_records(records,width)
        except ValueError:pass
        else:raise AssertionError(('missing refusal',records))
        assert line=='REFUSE',(records,line)
    independent,accounting=program_witness(ORIGINAL)
    assert run_plan(compile_plan(ORIGINAL.read_text()).to_dict())==independent==original_expected()
    assert accounting=={'statements':13,'steps':['capture'],'reads':[3]}
    # Four competing interpretations fail independent hand pins.
    assert PINS[3][2]!=[[1.,None],[2.,99.],[3.,4.]]  # MISSOVER substitution.
    assert PINS[4][2]!=[[1.,2.],[3.,4.],[5.,6.]]   # Flattening all tokens.
    assert PINS[11][2]!=[[7.,None]]                # Partial EOF publication.
    assert PINS[6][2]!=[[0.,2.],[3.,0.]]            # Coercing missing to zero.
    print('VERIFIED: numeric INPUT 12 hand pins,600 constructive source/runtime/R cases,24 shared refusals,4 naive controls and original five-snapshot program; no live SAS')


if __name__=='__main__':main()
