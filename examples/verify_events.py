"""OUTPUT, WHERE/IF timing, and retained state: original pins plus base R."""
import csv
import io
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
from saschi.compare import equal, table_equal


def execute(source, inputs=None):
    plan = compile_plan(source)
    if plan.blocked:
        raise AssertionError(plan.tickets)
    return run_plan(plan.to_dict(), inputs)['datasets']


def r_rows(scenario):
    r = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
    run = subprocess.run([r, str(HERE/'events.R'), scenario], capture_output=True, text=True, timeout=30)
    if run.returncode:
        raise RuntimeError(run.stderr)
    return [{k:float(v) if v else None for k,v in row.items()} for row in csv.DictReader(io.StringIO(run.stdout))]


def main():
    fixture = HERE/'events'
    expected = json.loads((fixture/'expected.json').read_text())['snapshots']
    actual = execute((fixture/'job.sas').read_text(), json.loads((fixture/'inputs.json').read_text()))['snapshots']
    assert table_equal(actual, expected), 'composed Python event output differs from pin'
    assert equal(r_rows('snapshots'), expected['rows']), 'base-R snapshots differ from pin'
    pins = [{'x':13.}, {'x':29.}]
    assert equal(execute('data d; x=13; output; x=29; output; x=47; run;')['d']['rows'], pins)
    assert equal(r_rows('output'), pins)
    assert pins != [{'x':47.}], 'known-wrong end-of-row output must fail'
    assert execute('data d; x=13; if 0 then output; run;')['d']['rows'] == []
    catalog = {'a':{'schema':{'g':'number','keep':'number'},'rows':[{'g':7,'keep':0},{'g':7,'keep':1},{'g':9,'keep':1}]}}
    template = 'data d; set a; by g; FILTER keep=1; f=first.g; run;'
    where = execute(template.replace('FILTER','where'), catalog)['d']['rows']
    subset = execute(template.replace('FILTER','if'), catalog)['d']['rows']
    observed = [{'where_first':a['f'], 'if_first':b['f']} for a,b in zip(where,subset)]
    filter_pin = [{'where_first':1., 'if_first':0.}, {'where_first':1., 'if_first':1.}]
    assert equal(observed, filter_pin) and equal(r_rows('filter'), filter_pin)
    assert observed[0]['where_first'] != observed[0]['if_first'], 'known-wrong early IF must fail'
    print('VERIFIED: original OUTPUT/filter/retention pins and three base-R witnesses; no live SAS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
