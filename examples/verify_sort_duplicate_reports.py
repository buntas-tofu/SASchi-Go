#!/usr/bin/env python3
"""Independent family-local three-report and TITLE gate for maintainers."""
from copy import deepcopy
import json
import random
import verify_sort_duplicates as shared


def batch_witness(sources):
    return shared.batch_witness(sources, 'sort_duplicate_reports.R')


def generated_cases(count=40):
    rng=random.Random(2401);cases=[]
    for i in range(count):
        values=[(rng.choice(['','A','a']),rng.choice([None,-1,0,2]),rng.randrange(5),rng.choice(['','X','Y'])) for _ in range(rng.randrange(16))]
        cards=[','.join('.' if v is None else str(v) for v in row) for row in values]
        reports=i%4;text=shared.source(cards,reports=reports)
        cases.append((text,shared.hand_case(values,['z','n'],reports=reports)))
    return cases


def title_reset_case():
    values=[('B',None,1,'X'),('A',2,2,'Y')];text=shared.source(['B,.,1,X','A,2,2,Y'])
    expected=shared.hand_case(values,['z','n']);reports={}
    text+='title "Repeated";\nproc print data=raw;run;\nproc print data=ordered;run;\ntitle;\nproc print data=removed;run;\n'
    expected['trace'].append('title|set|'+b'Repeated'.hex())
    for i,(dataset,title) in enumerate([('raw','Repeated'),('ordered','Repeated'),('removed',None)],1):
        if i==3:expected['trace'].append('title|reset')
        name='print_%02d.txt'%i;table=expected['result']['datasets'][dataset];content=shared.logical_report(table,title);reports[name]=content
        expected['trace'].extend(shared.report_events(title,dataset,name,content,len(table['rows'])))
    expected['result']['reports']=reports;expected['accounting']['statements']+=8
    return text,expected


def refusal_cases():
    three=shared.source([],reports=3)
    return [('fourth-report',shared.source([],reports=4)),
            ('fractional-print',shared.source(['A,.5,1,X'],reports=1)),
            ('unknown-report-input',three.replace('proc print data=removed','proc print data=unknown')),
            ('print-options',three.replace('proc print data=raw','proc print data=raw noobs')),
            ('empty-title',three.replace('title "Snapshot 1"','title ""')),
            ('title129',three.replace('title "Snapshot 1"','title "'+'A'*129+'"')),
            ('title-macro',three.replace('title "Snapshot 1"','title "%macro"')),
            ('title33',shared.source([])+'title "A";\n'*33),
            ('markerless-three-reports',three.replace(' dupout=removed nodupkey','').replace('data=removed','data=ordered')),
            ('print-has-by',three.replace('proc print data=raw;','proc print data=raw;by z;'))]


def qualify():
    q=shared.qualify_anchor(batch_witness);generated=generated_cases()+[title_reset_case()];refused=refusal_cases()
    selection=[('print-only-no-family','data raw;infile datalines dsd;input z :$1.;datalines4;\n;;;;\nrun;proc print data=raw;run;')]
    answers=batch_witness([text for text,_ in generated]+[text for _,text in refused]+[text for _,text in selection])
    for (_,expected),answer in zip(generated,answers[:len(generated)],strict=True):shared.exact(answer,expected)
    for (label,_),answer in zip(refused,answers[len(generated):len(generated)+len(refused)],strict=True):assert answer is None,label
    for (label,_),answer in zip(selection,answers[len(generated)+len(refused):],strict=True):assert answer is None,label
    return {**q,'generated':generated,'boundaries':[],'refused':refused,'selection':selection,'independent':answers}


def qualification_record(q):
    record=shared.qualification_record(q);record['construct']='ST-024 family-local three logical reports'
    record['distinct_obligations']=['zero through three report artifacts','three full original report snapshots','TITLE persistence and reset',
      'fourth report refused','fractional numeric PRINT refused separately from sortable exact fractions','markerless programs cannot select family']
    return record


# Post-freeze family-local report API/CLI checks; frozen hand/R output is above.
def wrong_report_cases(truth):
    result=[]
    for mode in ('third-bytes','third-missing','third-basename','third-newline','earlier-snapshot','title-reset','third-unicode'):
        wrong=deepcopy(truth);reports=wrong['reports']
        if mode=='third-bytes':reports['print_03.txt']+='extra\n'
        elif mode=='third-missing':del reports['print_03.txt']
        elif mode=='third-basename':reports['other.txt']=reports.pop('print_03.txt')
        elif mode=='third-newline':reports['print_03.txt']=reports['print_03.txt'].removesuffix('\n')
        elif mode=='earlier-snapshot':reports['print_01.txt']=shared.logical_report(wrong['datasets']['ranked'],'Ranked before replacement')
        elif mode=='title-reset':reports['print_03.txt']=reports['print_03.txt'].replace('TITLE: Removed after replacement\n','')
        else:reports['print_03.txt']+='é\n'
        result.append((mode,wrong))
    return result


def portable_report_refusals():
    from saschi.plan import compile_plan
    from saschi import sort_duplicates,mixed_reports
    from saschi.runtime import run_plan
    plan=compile_plan(shared.ORIGINAL.read_text()).to_dict();step=next(item for item in plan['steps'] if item['kind']=='duplicate_print')
    tables=shared.original_expected()['datasets'];count=0
    def rejected(changed=step,ordinal=3,version=2):
        nonlocal count
        before=deepcopy(tables)
        try:sort_duplicates.execute_print(changed,tables,ordinal=ordinal,version=version)
        except (ValueError,TypeError,KeyError,RecursionError):pass
        else:raise AssertionError('malformed duplicate PRINT admitted')
        shared.exact(tables,before);count+=1
    for name,value in [('name','raw'),('inputs',[]),('by',['zebra']),('nodupkey',True),('where',True),('lengths',{'x':1}),('line',True),('extra',1)]:
        changed=deepcopy(step);changed[name]=value;rejected(changed)
    for name,value in [('profile','ascii-titled-mixed-integer-v1'),('source_lines',[]),('source_lines',[True]),('source_lines',[1]),('extra',1)]:
        changed=deepcopy(step);changed['operations'][0]['args'][name]=value;rejected(changed)
    for ordinal in (False,0,4,1.0):rejected(ordinal=ordinal)
    rejected(version=True)
    # New PRINT markers cannot activate the new family without a real partition.
    changed=deepcopy(plan);changed['steps']=[item for item in changed['steps'] if item['kind']!='duplicate_sort']
    try:run_plan(changed)
    except (ValueError,TypeError,KeyError,RecursionError):count+=1
    else:raise AssertionError('PRINT marker activated new family')
    old=compile_plan(shared.source([],reports=1).replace(' dupout=removed','')).to_dict()
    old_step=next(item for item in old['steps'] if item['kind']=='mixed_print')
    try:mixed_reports.execute_print(old_step,{'raw':tables['raw']},ordinal=3)
    except (ValueError,TypeError,KeyError):count+=1
    else:raise AssertionError('old mixed PRINT cap grew')
    return count


def expected_report_contract_controls(truth):
    import tempfile
    from pathlib import Path
    from saschi.report_artifacts import read_expected_reports,report_manifest,MIXED_REPORT_CONTRACT,INFORMAT_REPORT_CONTRACT
    contract='ascii-dupout-mixed-integer-v1';count=0
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'reports.json';path.write_text(json.dumps(truth['reports']))
        shared.exact(read_expected_reports(path,contract=contract)[0],truth['reports'])
        assert list(report_manifest(truth['reports'],contract=contract))==list(truth['reports'])
        for old in (MIXED_REPORT_CONTRACT,INFORMAT_REPORT_CONTRACT):
            try:read_expected_reports(path,contract=old)
            except ValueError:count+=1
            else:raise AssertionError('old expected-report count grew')
        bad=[json.dumps({**truth['reports'],'fourth.txt':'wrong\n'}),json.dumps({'../bad.txt':'x'}),json.dumps({'print_01.txt':1}),
             '{"print_01.txt":"a","print_01.txt":"b"}', '{"print_01.txt":NaN}',json.dumps({'print_01.txt':'x'*(4*1024*1024)})]
        for raw in bad:
            path.write_text(raw)
            try:read_expected_reports(path,contract=contract)
            except ValueError:count+=1
            else:raise AssertionError('unsafe/oversize expected reports admitted')
    return count


def run():
    q=qualify();actual,trace=shared.execute(q['original']);shared.exact(actual,q['truth']);shared.exact(trace,q['trace'])
    for text,expected in q['generated']:
        result,events=shared.execute(text);shared.exact(result,expected['result']);shared.exact(events,expected['trace'])
    for label,text in q['refused']:shared.check_refused(label,text)
    for label,text in q['selection']:shared.check_old_selection(label,text)
    shared.cli_check(q['original'],q['truth']);wrong=wrong_report_cases(q['truth'])
    for _,incorrect in wrong:shared.comparator_refuses(actual,incorrect);shared.cli_check(q['original'],incorrect,True)
    negative=shared.cli_source_refusal(next(text for label,text in q['refused'] if label=='fourth-report'))
    summary={'construct':'sort-duplicate-reports','generated_report_cases':len(q['generated']),'source_refusals':len(q['refused']),
             'old_family_controls':len(q['selection']),'portable_report_refusals':portable_report_refusals(),
             'expected_report_contract_controls':expected_report_contract_controls(q['truth']),'wrong_actual_cli_reports':len(wrong),
             'actual_negative_cli':negative,'late_actual_cli_third_report_faults':shared.atomic_check(q['original'],'third-report'),
             'logical_report_bytes':[len(body.encode()) for body in q['truth']['reports'].values()]}
    print('sort-duplicate-reports: '+json.dumps(summary,sort_keys=True));return summary


if __name__=='__main__':run()
