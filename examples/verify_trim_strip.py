"""DS-043 hand pins, constructive runtime cases and independent base R."""
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
from sas_semantics import sas_trim, sas_strip, sas_trim_concat
from saschi.plan import compile_plan
from saschi.runtime import run_plan

PINS=[('trim','  A  ','  A'),('strip','  A  ','A'),
      ('trim',' ',' '),('strip',' ',''),('trim','    ',' '),('strip','    ',''),
      ('trim','A B ','A B'),('strip',' A B ','A B'),
      ('trim','A','A'),('strip','A','A'),('trim','  A','  A'),('strip','  A','A')]
REFUSALS=['',None,1,True,{'missing':'A'},'é','a\tb','a\nb','\x00','x'*32768]
ORIGINAL=HERE/'trim_strip_capture.sas'


def rrun(*args):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'trim_strip.R'),*map(str,args)],capture_output=True,
                          text=True,check=True,timeout=60).stdout


def original_expected():
    chars={name:{'type':'character','length':width} for name,width in [('a',4),('t',4),('s',4),('joined',6)]}
    return {'datasets':{
        'capture':{'schema':chars,'rows':[
            {'a':' X  ','t':' X  ','s':'X   ','joined':'[X]   '},
            {'a':'    ','t':'    ','s':'    ','joined':'[ ]   '},
            {'a':'    ','t':'    ','s':'    ','joined':'[]    '}]},
        'after':{'schema':{'a':{'type':'character','length':3},'n':'number'},
                 'rows':[{'a':'*  ','n':1.},{'a':'** ','n':2.},{'a':'***','n':3.}]}},
        'log':['[] ']}


def program_witness(path):
    result={'datasets':{},'log':[]};states=[];trips=[];names=[];table=None
    def row(text):
        values={}
        for field in text.split('|'):
            name,value=field.split('=',1)
            values[name]=bytes.fromhex(value[1:]).decode('ascii') if value[0]=='C' else float(value[1:])
        return values
    lines=rrun('program',path).splitlines()
    assert lines[0].startswith('STATEMENTS:')
    for line in lines[1:]:
        tag,payload=line.split(':',1)
        if tag=='STEP':
            _,name=payload.split(':');names.append(name)
            table={'schema':{},'rows':[]}
            if name!='_null_':result['datasets'][name]=table
        elif tag=='SCHEMA':
            name,width=payload.split(':');width=int(width)
            table['schema'][name]={'type':'character','length':width} if width else 'number'
        elif tag=='ROW':table['rows'].append(row(payload))
        elif tag=='STATE':states.append(row(payload))
        elif tag=='TRIPS':trips.append(int(payload))
        elif tag=='RECORD':result['log'].append(bytes.fromhex(payload).decode('ascii'))
        else:raise AssertionError(line)
    return result,{'statements':int(lines[0].split(':')[1]),'steps':names,'states':states,'trips':trips}


def main():
    rng=random.Random(4301)
    cases=[(mode,value,7,expected) for mode,value,expected in PINS]
    for _ in range(800):
        value=''.join(rng.choice('   AbXY09[]') for _ in range(rng.randint(1,24)))
        for mode in ('trim','strip'):
            expected=(value.rstrip(' ') or ' ') if mode=='trim' else value.strip(' ')
            cases.append((mode,value,rng.randint(1,30),expected))
    refusals=[(mode,value,7,None) for mode in ('trim','strip') for value in REFUSALS]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'cases.csv'
        with path.open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['mode','type','value','width'])
            for mode,value,width,_ in cases+refusals:
                writer.writerow([mode,'character' if isinstance(value,str) else 'other',
                                 value.encode().hex() if isinstance(value,str) else repr(value),width])
        records=rrun('cases',path).splitlines()
    assert len(records)==len(cases)+len(refusals)
    for index,((mode,value,width,expected),record) in enumerate(zip(cases+refusals,records)):
        function=sas_trim if mode=='trim' else sas_strip
        if expected is None:
            try:function(value)
            except ValueError:pass
            else:raise AssertionError(('missing refusal',mode,value))
            assert record=='REFUSE',(index,record)
            continue
        assert function(value)==expected
        joined=sas_trim_concat(['[',expected,']'],[False,True,False])
        stored=expected[:width].ljust(width)
        fixed_join=joined.ljust(len(value)+2)
        assert record==':'.join(['OK',expected.encode().hex(),stored.encode().hex(),fixed_join.encode().hex()]),(index,record)
        source=f"data d; length a ${len(value)}; length stored ${width}; a='{value}'; stored={mode}(a); joined='['||{mode}(a)||']'; run;"
        plan=compile_plan(source);assert not plan.blocked,plan.tickets
        table=run_plan(plan.to_dict())['datasets']['d']
        assert table['rows']==[{'a':value,'stored':stored,'joined':fixed_join}]
        assert table['schema']['joined']=={'type':'character','length':len(value)+2}
    original=run_plan(compile_plan(ORIGINAL.read_text()).to_dict())
    independent,accounting=program_witness(ORIGINAL)
    assert original==original_expected()==independent
    assert accounting['statements']==26 and accounting['trips']==[0,3]
    # A repadded temporary, TRIM-as-STRIP and a one-blank STRIP each fail a hand pin.
    assert 'A  '+'!'!='A!'
    assert sas_trim(' A ')!=sas_strip(' A ')
    assert sas_strip(' ')!=' ' and sas_trim(' ')!=''
    print('VERIFIED: TRIM/STRIP 12 pins, 1600 source/runtime/R cases, 20 shared refusals, four naive controls and original six-snapshot program; no live SAS')


if __name__=='__main__':main()
