"""DS-042 original pins and independent base-R records, no live SAS."""
import csv
import io
import itertools
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from sas_semantics import sas_put_mixed_numeric
from saschi.plan import compile_plan
from saschi.runtime import run_plan

def literal(value):return {'kind':'literal','value':value}
def numeric(value):return {'kind':'numeric','value':value}
PINS=[
    ([literal("'n:'"),numeric(7)],'n:7 '),
    ([numeric(7),literal("'.'")],'7 .'),
    ([literal("'['"),numeric(-3),literal("']'")],'[-3 ]'),
    ([literal("'  n:  '"),numeric(None)],'  n:  . '),
    ([literal("''"),numeric(-0.0),literal('""')],"'0 \""),
    ([literal("'O''Neil:'"),numeric(99999999999)],"O'Neil:99999999999 "),
    ([literal('"a""b"'),numeric(-99999999999)],'a"b-99999999999 '),
    ([literal("'x'"),literal("'y'"),numeric(1),numeric(2)],'xy1 2 '),
    ([literal("'"+'x'*62+"'"),numeric(0)],'x'*62+'0 '),
]
REFUSALS=[[],[literal("'x'")],[numeric(1),numeric(2)],
          [literal("'x'"),literal("'y'")],
          [literal("'x'"),{'kind':'character','value':'a'}],
          [literal("'"+'x'*63+"'"),numeric(0)],
          [literal('"&name"'),numeric(1)],
          [literal("'é'"),numeric(1)],[literal("'a\tb'"),numeric(1)],
          [literal("'unclosed"),numeric(1)]]
REFUSALS += [[literal("'x'"),numeric(v)] for v in
             (True,'1',{'missing':'A'},1.25,100000000000,-100000000000,float('inf'),float('nan'))]

def generated_cases():
    values=(-99999999999,-10000000000,-17,-1,0,1,17,10000000000,99999999999,None)
    literals=[("'['",'['),("' ] '",' ] '),("'  '",'  '),("''","'"),
              ('""','"'),("'a''b'","a'b"),('"a""b"','a"b'),("'&x %y'",'&x %y')]
    for a,b,(token,text),position in itertools.product(values,values,literals,range(3)):
        items=[numeric(a),numeric(b)];items.insert(position,literal(token))
        pieces=[('.' if v is None else str(v))+' ' for v in (a,b)];pieces.insert(position,text)
        yield items,''.join(pieces)

def rrun(*args):
    r=os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    return subprocess.run([r,str(HERE/'put_mixed_numeric.R'),*map(str,args)],
                          capture_output=True,text=True,check=True,timeout=60).stdout

def original_expected():
    return {'datasets':{'records':{'schema':dict.fromkeys(['x','y','i','total'],'number'),
            'rows':[{'x':1.,'y':None,'i':1.,'total':None},
                    {'x':1.,'y':2.,'i':2.,'total':None},
                    {'x':1.,'y':2.,'i':3.,'total':3.}]}},
            'log':['i:1 x:1 y:. ','i:2 x:1 y:2 ','total:3 ']}

def original_witness():
    lines=rrun('original').splitlines()
    rows=[{k:float(v) if v else None for k,v in row.items()} for row in csv.DictReader(lines[:4])]
    logs=[bytes.fromhex(line.removeprefix('RECORD:')).decode('ascii') for line in lines[4:]]
    expected=original_expected();assert rows==expected['datasets']['records']['rows'];assert logs==expected['log']
    return expected

def program_witness(path):
    state,record=rrun('program',path).splitlines()
    _,outer,inner,trips,cells,total=state.split(':')
    # Divisor pairs toggle twice; only squares have an unpaired divisor.
    squares={n*n for n in range(1,11)}
    assert list(map(int,cells.split('|')))==[int(n in squares) for n in range(1,101)]
    assert (int(outer),int(inner),int(trips),int(total))==(101,200,482,10)
    assert record.startswith('RECORD:')
    return bytes.fromhex(record[7:]).decode('ascii')

def main():
    successes=PINS+list(generated_cases())
    for items,expected in successes:assert sas_put_mixed_numeric(items)==expected
    for items in REFUSALS:
        try:sas_put_mixed_numeric(items)
        except ValueError:pass
        else:raise AssertionError(('must refuse',items))
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'cases.csv'
        with path.open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['id','kind','type','value'])
            for n,items in enumerate([x[0] for x in successes]+REFUSALS):
                if not items:writer.writerow([n,'empty','empty',''])
                for item in items:
                    v=item['value'];typ=('missing' if v is None else 'boolean' if isinstance(v,bool) else
                        'text' if isinstance(v,str) else 'tagged' if isinstance(v,dict) else 'number')
                    writer.writerow([n,item['kind'],typ,str(v)])
        records=rrun('cases',path).splitlines()
    assert len(records)==len(successes)+len(REFUSALS)
    for n,record in enumerate(records):
        if n<len(successes):assert record=='OK:'+successes[n][1].encode().hex(),(n,record)
        else:assert record=='REFUSE',(n,record)
    # Execute every constructive case through the source parser and runtime too.
    for items,expected in successes:
        assignments=[];tokens=[];expected_rows={}
        for i,item in enumerate(items):
            if item['kind']=='literal':tokens.append(item['value'])
            else:
                name=f'n{i}';v=item['value'];assignments.append(f'{name}={"." if v is None else int(v)};')
                tokens.append(name);expected_rows[name]=None if v is None else float(v)
        source='data d;'+''.join(assignments)+'put '+' '.join(tokens)+';run;'
        p=compile_plan(source);assert not p.blocked,p.tickets
        assert run_plan(p.to_dict())=={'datasets':{'d':{'schema':dict.fromkeys(expected_rows,'number'),'rows':[expected_rows]}},'log':[expected]}
    original=compile_plan((HERE/'mixed_put_capture.sas').read_text());assert not original.blocked,original.tickets
    assert run_plan(original.to_dict())==original_witness()
    assert 'n: 7 '!=PINS[0][1] and '7.'!=PINS[1][1] and '[-3]'!=PINS[2][1]
    assert '  n:  . '!=PINS[3][1].strip() and '0.0' not in PINS[4][1]
    print(f'VERIFIED: mixed numeric PUT {len(PINS)} pins,{len(successes)-len(PINS)} constructive source/runtime/R cases,'
          f'{len(REFUSALS)} shared refusals,5 spacing/format controls,original three-snapshot witness; no live SAS')

if __name__=='__main__':main()
