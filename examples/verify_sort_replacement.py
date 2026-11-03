#!/usr/bin/env python3
"""Independent survivor-only replacement and snapshot gate for maintainers."""
from copy import deepcopy
import json
import random
import verify_sort_duplicates as shared


def batch_witness(sources):
    return shared.batch_witness(sources, 'sort_replacement.R')


def generated_cases(count=48):
    rng = random.Random(7701);cases = []
    for i in range(count):
        fractional = i % 3 == 0
        values = [(rng.choice(['', 'A', 'B', 'a']), rng.choice([None, -.5, 0, .5, 2] if fractional else [None, -2, 0, 2]),
                   rng.randrange(6), rng.choice(['X', 'Y', ''])) for _ in range(rng.randrange(21))]
        by = ['z', 'n'] if i % 2 else ['n', 'z'];reports = 0 if fractional else 2;directed = i % 2 == 0
        cards = [','.join('.' if v is None else str(v) for v in row) for row in values]
        text = shared.source(cards, by=' '.join(by), replacement=True, reports=reports, directed=directed)
        cases.append((text, shared.hand_case(values, by, True, reports, directed)))
    return cases


def repeated_survivor_case():
    values = [('B', 1, 1, 'Y'), ('A', 2, 2, 'X'), ('B', 1, 3, 'X'), ('A', 3, 4, 'X')]
    text = shared.source([','.join(map(str,row)) for row in values])
    expected = shared.hand_case(values, ['z', 'n'])
    prior = expected['result']['datasets']['ordered']
    kept, removed, order, survivor, discarded = shared.hand_partition(prior, ['q'])
    expected['result']['datasets']['ordered'] = kept;expected['result']['datasets']['again_removed'] = removed
    expected['trace'].append({'event':'sort_dupout','line':14,'source':'ordered','destination':'ordered',
                              'duplicate_destination':'again_removed','replace':True,'source_ordinals':order,
                              'kept_ordinals':survivor,'removed_ordinals':discarded})
    expected['accounting']['statements'] += 3
    text += 'proc sort data=ordered dupout=again_removed nodupkey;\nby q;\nrun;\n'
    return text,expected


def refusal_cases():
    first = shared.source([]);replacement = shared.source([], replacement=True)
    return [('original-producer-replacement',first.replace(' out=ordered','')),
            ('explicit-input-equals-out',replacement.replace('data=ordered dupout','data=ordered out=ordered dupout')),
            ('prior-dupout-side-output',first+'proc sort data=removed dupout=other nodupkey;by z;run;\n'),
            ('unknown-input',replacement.replace('data=ordered dupout','data=unknown dupout')),
            ('overwrite-another-table',replacement.replace('data=ordered dupout','data=ordered out=raw dupout')),
            ('side-output-collision',replacement.replace('dupout=removed','dupout=raw')),
            ('replacement-without-nodupkey',replacement.replace(' nodupkey','')),
            ('plain-sort-inplace',replacement.replace('data=raw out=ordered','data=raw')),
            ('plain-sort-overwrite',replacement.replace('out=ordered','out=raw'))]


def qualify():
    q = shared.qualify_anchor(batch_witness);generated=generated_cases()+[repeated_survivor_case()];refused=refusal_cases()
    answers=batch_witness([text for text,_ in generated]+[text for _,text in refused])
    for (_,expected),answer in zip(generated,answers[:len(generated)],strict=True):shared.exact(answer,expected)
    for (label,_),answer in zip(refused,answers[len(generated):],strict=True):assert answer is None,label
    return {**q,'generated':generated,'boundaries':[],'refused':refused,'independent':answers}


def qualification_record(q):
    record=shared.qualification_record(q);record['construct']='DS-077 survivor-only omitted-OUT replacement'
    record['distinct_obligations']=['plain and directed prior survivor destinations','repeated prior duplicate survivor destination',
      'DUPOUT side output is not replacement-owned','original producer and arbitrary overwrite refused','full pre-replacement snapshot anchor']
    return record


# Post-freeze public-runtime and CLI checks; independent expectations stay above.
def wrong_replacement_cases(truth):
    result=[]
    for mode in ('unreplaced-input','last-survivor','raw-mutated','missing-new-side-output','lost-earlier-output','snapshot-updated','replacement-source-order'):
        wrong=deepcopy(truth);tables=wrong['datasets']
        if mode=='unreplaced-input':tables['ranked']=shared.view(tables['raw'],[14,13,12,10,8,7,6,9,5,4,3,2,1,11])
        elif mode=='last-survivor':tables['ranked']['rows'][0]['payload']=50.
        elif mode=='raw-mutated':tables['raw']['rows'].pop()
        elif mode=='missing-new-side-output':tables['ranked_removed']['rows']=[]
        elif mode=='lost-earlier-output':tables['firsts']['rows'].reverse()
        elif mode=='snapshot-updated':wrong['reports']['print_01.txt']=shared.logical_report(tables['ranked'],'Ranked before replacement')
        else:tables['ranked_removed']['rows'].reverse()
        result.append((mode,wrong))
    return result


def portable_lineage_refusals():
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    count=0
    def rejected(plan,catalog=None):
        nonlocal count
        before=deepcopy(plan)
        try:run_plan(plan,catalog)
        except (ValueError,TypeError,KeyError,RecursionError):pass
        else:raise AssertionError('malformed replacement lineage admitted')
        shared.exact(plan,before);count+=1
    base=compile_plan(shared.source([],replacement=True)).to_dict()
    changed=deepcopy(base);step=changed['steps'][-1];step['name']='raw';step['inputs']=['raw'];rejected(changed)
    changed=deepcopy(base);step=changed['steps'][-1];step['operations'][0]['args']['replace']=False;rejected(changed)
    changed=deepcopy(base);step=changed['steps'][-1];step['name']='another';rejected(changed)
    changed=deepcopy(base);changed['steps'].pop(1);rejected(changed)
    text,_=repeated_survivor_case();chain=compile_plan(text).to_dict()
    changed=deepcopy(chain);step=changed['steps'][-1];step['name']='removed';step['inputs']=['removed'];rejected(changed)
    changed=deepcopy(chain);step=changed['steps'][-1];step['operations'][0]['args']['dupout']='removed';rejected(changed)
    rejected(deepcopy(base),{'raw':shared.table([('z',3),('n',0),('payload',0),('q',2)],[])})
    return count


def run():
    q=qualify();actual,trace=shared.execute(q['original']);shared.exact(actual,q['truth']);shared.exact(trace,q['trace'])
    for text,expected in q['generated']:
        result,events=shared.execute(text);shared.exact(result,expected['result']);shared.exact(events,expected['trace'])
    for label,text in q['refused']:shared.check_refused(label,text)
    wrong=wrong_replacement_cases(q['truth'])
    for _,incorrect in wrong:shared.comparator_refuses(actual,incorrect);shared.cli_check(q['original'],incorrect,True)
    shared.cli_check(q['original'],q['truth'])
    negative=shared.cli_source_refusal(next(text for label,text in q['refused'] if label=='prior-dupout-side-output'))
    summary={'construct':'sort-replacement','generated_lineage_cases':len(q['generated']),'source_refusals':len(q['refused']),
             'portable_lineage_refusals':portable_lineage_refusals(),'wrong_actual_cli_comparators':len(wrong),
             'actual_negative_cli':negative,'late_actual_cli_faults':shared.atomic_check(q['original'],'replacement'),
             'earlier_snapshot_bytes':len(q['truth']['reports']['print_01.txt'].encode())}
    print('sort-replacement: '+json.dumps(summary,sort_keys=True));return summary


if __name__=='__main__':run()
