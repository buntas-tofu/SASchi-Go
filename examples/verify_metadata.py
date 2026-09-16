"""Character widths, descriptors, encodings, missing identity: original base-R witness."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.compare import table_equal
from sas_semantics import sas_numeric_order, sas_fixed_character


def main():
    table = {'encoding':'utf-8', 'schema':{
        'id':{'type':'character','length':3},
        'day':{'type':'number','format':'DATE9.','label':'Day'},
        'text':{'type':'character','length':4}, 'value':'number'},
        'rows':[{'id':'007','day':0.,'text':'éé','value':{'missing':'A'}},
                {'id':'002','day':1.,'text':'北 ','value':None}]}
    actual = run_plan(compile_plan('data d; set a; output; run;').to_dict(), {'a':table})['datasets']['d']
    assert table_equal(actual, table)
    assert table_equal(json.loads(json.dumps(actual)), table)
    changed = json.loads(json.dumps(table)); changed['rows'][0]['id'] = 7
    assert not table_equal(changed, table), 'known-wrong identifier coercion must fail'
    changed = json.loads(json.dumps(table)); changed['rows'][0]['value'] = None
    assert not table_equal(changed, table), 'known-wrong missing collapse must fail'
    changed = json.loads(json.dumps(table)); del changed['schema']['day']['format']
    assert not table_equal(changed, table), 'known-wrong metadata loss must fail'
    values = [3., {'missing':'Z'}, None, {'missing':'A'}, {'missing':'_'}, -4.]
    render = lambda v: '.' if v is None else '.'+v['missing'] if isinstance(v,dict) else format(v,'.0f')
    observed = ['id|'+'|'.join(r['id'] for r in actual['rows']),
                'day|'+'|'.join(format(r['day'],'.0f') for r in actual['rows']),
                'format|'+actual['schema']['day']['format'], 'label|'+actual['schema']['day']['label'],
                'text_bytes|'+'|'.join(str(len(r['text'].encode('utf-8'))) for r in actual['rows']),
                'missing|'+'|'.join(render(v) for v in sorted(values,key=sas_numeric_order)),
                'width|'+sas_fixed_character('WXYZ',1)+'|'+sas_fixed_character('WXYZ',5)]
    pin = ['id|007|002','day|0|1','format|DATE9.','label|Day','text_bytes|4|4',
           'missing|._|.|.A|.Z|-4|3','width|W|WXYZ ']
    assert observed == pin, 'Python typed metadata witness differs'
    r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    run = subprocess.run([r,str(HERE/'metadata.R')],capture_output=True,text=True,timeout=30)
    assert run.returncode == 0, run.stderr
    assert run.stdout.splitlines() == pin, 'base-R typed metadata witness differs'
    print('VERIFIED: original metadata/width/tagged-missing pins and base R; no live SAS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
