#!/usr/bin/env python3
"""Whole immutable vendor INVALUE example under named repository report policies."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.vendor_sources import verify_sources
from vendor_invalue_hand import build, LINES
from vendor_invalue_lex import SOURCE_SHA256, checksum
from verify_vendor_sorted_copy import ordered_equal, encode, need, cli
from saschi.plan import compile_plan
from saschi.emit_py import translate
from saschi.emit_cpp import translate as translate_cpp
from saschi.formatted_program import run_program
from saschi.runtime import run_plan
from saschi.job import build_job

IDENTITY = 'sas-code-examples-invalue-v1'
FROZEN = {
    'result.json': '8478893f8b11b8d768df590264685c423e121d85fced3ab09f3a8fa0f64b4cc2',
    'accounting.json': '477e7fb938fe80d2e51c6f4135dbcb147e50acb1efca3a53e7e09c991fbb6a10',
    'trace.json': '756f9607ac286905f03de4372c91e85507030ae87e50107ed293db205ac3cbbe',
    'print_01.txt': '89683d28bc7779962387d7074323cbfb31491514970f5df23ecc316a8d473d07',
    'means_01.txt': 'aa5ddd2b348b1f693be8f9851e5a9b01b39be4e2503eb60c9f9e8019bd674d9b',
}


def late_failure(area):
    # Owned source makes MEANS succeed before the later PRINT row exceeds its
    # independent415-byte rendering cap. Every table/schema preflight is valid.
    raw = 'A ' + 'x' * 30
    source = "proc format; invalue eval '" + raw + "'=1; run;\n"
    source += 'data owned; input id $ ' + ' '.join('@1 c'+str(i)+' $32.' for i in range(13)) + ' @1 number eval.;\n'
    source += 'datalines;\n' + raw + '\n;\nrun;\n'
    source += 'proc means data=owned; run; proc print data=owned label noobs; label id="ID"; run;'
    from saschi import informat_reports
    seen = []
    original = informat_reports.execute_means
    def observer(*args, **kwargs):
        result = original(*args, **kwargs)
        seen.append('means completed')
        return result
    with patch.object(informat_reports, 'execute_means', observer):
        job = build_job(source)
    need(not job.plan.blocked and seen == ['means completed'] and job.code == 1 and job.result is None,
         'actual late PRINT rendering failure did not remain atomic')
    path = area / 'owned-late.sas'; path.write_text(source)
    output = area / 'late'
    run, receipt = cli(path, output)
    need(run.returncode == 1 and not receipt['accepted'] and '415' in receipt['error'], 'late actualCLI failure differs')
    need(not any((output/name).exists() for name in ('result.json','observed.json','reports','exports')), 'late failure leaked artifacts')


def main():
    with patch('tools.vendor_sources.urlopen', side_effect=AssertionError('offline gate attempted network')):
        bound = verify_sources()[IDENTITY]
    original = bound['source'].read_bytes()
    license_bytes = bound['license'].read_bytes()
    need(len(original) == 1802 and checksum(original) == SOURCE_SHA256, 'original whole source differs')
    expected, accounting, expected_trace = build(original)
    bodies = {'result.json': encode(expected), 'accounting.json': encode(accounting), 'trace.json': encode(expected_trace),
              **{name: text.encode('ascii') for name,text in expected['reports'].items()}}
    for name,pin in FROZEN.items():
        need(checksum(bodies[name]) == pin, 'pre-engine frozen expectation differs: '+name)
    with tempfile.TemporaryDirectory(prefix='saschi-vendor-invalue-') as temporary:
        area = Path(temporary).resolve()
        need(not area.is_relative_to(ROOT), 'vendor bodies require external temporary output')
        source_path = area/'original.sas'; source_path.write_bytes(original)
        reference = area/'R'
        run = subprocess.run([os.environ.get('ROSETTA_RSCRIPT','Rscript'), str(ROOT/'examples/vendor_invalue.R'),
                              str(source_path), str(reference)], cwd=ROOT, capture_output=True, timeout=120)
        need(run.returncode == 0, 'independent whole R failed: '+run.stderr.decode(errors='replace'))
        for name,raw in bodies.items(): need((reference/name).read_bytes() == raw, 'whole R/hand differs: '+name)
        text = original.decode('ascii'); plan = compile_plan(text)
        need(not plan.blocked and len(plan.steps) == 5 and len(plan.matched) == 13, 'whole admission differs')
        need([line for _,_,line in plan.matched] == LINES, 'whole source rule accounting differs')
        trace = []; actual = run_program(plan.to_dict(), trace=trace)
        need(ordered_equal(actual, expected) and ordered_equal(trace, expected_trace), 'whole values or36-event schedule differ')
        need(ordered_equal(run_plan(plan.to_dict()), expected), 'runtime dispatcher differs')
        emitted = translate(text); namespace = {}; stdout = io.StringIO()
        with redirect_stdout(stdout): exec(emitted.code, namespace)
        need(not emitted.blocked and stdout.getvalue() == '' and ordered_equal(namespace['result'],expected), 'whole emitted result differs')
        need(translate_cpp(text).blocked, 'unadmitted C++ target accepted')
        expected_path, reports_path = area/'expected.json', area/'reports.json'
        expected_path.write_bytes(encode(expected['datasets'])); reports_path.write_bytes(encode(expected['reports']))
        output = area/'accepted'; run, receipt = cli(source_path, output, expected=expected_path, reports=reports_path)
        need(run.returncode == 0 and receipt['accepted'] and receipt['comparison'] == receipt['report_comparison'] == 'passed'
             and receipt['report_contract'] == 'ascii-informat-reports-v1', 'actualCLI whole comparison failed')
        completeness = receipt['completeness']
        need([completeness[k] for k in ('n_statements','n_routed','n_unrouted','n_functions','n_tickets')] == [14,13,1,0,0], 'source-only accounting differs')
        need(ordered_equal(json.loads((output/'result.json').read_text()),expected), 'published complete result differs')
        for name,raw in bodies.items():
            if name.endswith('.txt'): need((output/'reports'/name).read_bytes() == raw, 'published report differs')
        wrong_data = []
        value=deepcopy(expected['datasets']);value['evals']['schema']['string']['length']=8;wrong_data.append(value)
        value=deepcopy(expected['datasets']);value['evals']['rows'][4]['id']='740     ';wrong_data.append(value)
        value=deepcopy(expected['datasets']);value['evals']['rows'][1]['evaluation']=3;wrong_data.append(value)
        wrong_reports = []
        for name,transform in [('print_01.txt',lambda t:t.replace('Value Read with Informat','evaluation')),
                               ('means_01.txt',lambda t:t.split('\n',1)[1]),
                               ('means_01.txt',lambda t:t.replace('1.03509834','1.03509833')),
                               ('print_01.txt',lambda t:t.rstrip('\n'))]:
            value=deepcopy(expected['reports']);value[name]=transform(value[name]);wrong_reports.append(value)
        value=deepcopy(expected['reports']);value['other.txt']=value.pop('means_01.txt');wrong_reports.append(value)
        for kind,values in [('data',wrong_data),('reports',wrong_reports)]:
            for index,value in enumerate(values):
                path=area/(kind+str(index)+'.json');path.write_bytes(encode(value))
                failed=area/(kind+str(index));run,record=cli(source_path,failed,
                    expected=path if kind=='data' else expected_path, reports=path if kind=='reports' else reports_path)
                need(run.returncode == 1 and not record['accepted'] and not (failed/'reports').exists(), 'wrong comparator accepted or published report')
        late_failure(area)
        need(source_path.read_bytes() == original, 'original source changed')
    need(bound['source'].read_bytes() == original and bound['license'].read_bytes() == license_bytes, 'external pins changed')
    print('VERIFIED vendor: '+IDENTITY+'; unchanged1802bytes; independent hand/baseR;13statements+1opaque/8rows/9attempts/36events;1dataset/2exactreports;actualCLI+8wrongcomparators+late-report-atomic;no live SAS or physical-layout claim')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
