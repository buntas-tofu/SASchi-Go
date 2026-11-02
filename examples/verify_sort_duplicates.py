#!/usr/bin/env python3
"""Independent original PROC SORT DUPOUT gate for maintainer review.

Hand/base-R qualification runs before new translator comparisons. No live SAS.
"""
from copy import deepcopy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('SASCHI_REPOSITORY_ROOT', str(HERE.parent))).resolve()
sys.path.insert(0, str(ROOT))
ORIGINAL = HERE / 'sort_duplicates_capture.sas'
SOURCE_PIN = '6d6ba2a3bd035fe5b90a1ce238870fa8e814ac3f38b2cae7b2133bc365e60273'
RESULT_PIN = '361820ae2d5d0916b78112877e23fa84fffce2c250fa4c730afce69d604a46f4'
TRACE_PIN = '8c94f432c87d76ad5bec8c45d4bc4cabcbaa716f93aed1aea23f2167f709edc7'
ACCOUNT_KEYS = ('statements', 'physical_records', 'observations', 'attempts', 'outputs')


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()


def exact(actual, expected):
    if type(expected) is dict:
        assert type(actual) is dict and list(actual) == list(expected), (actual, expected)
        for name in expected: exact(actual[name], expected[name])
    elif type(expected) is list:
        assert type(actual) is list and len(actual) == len(expected), (actual, expected)
        for a, b in zip(actual, expected, strict=True): exact(a, b)
    elif type(expected) in (int, float):
        assert type(actual) in (int, float) and actual == expected, (actual, expected)
    else: assert type(actual) is type(expected) and actual == expected, (actual, expected)


def table(columns, values):
    schema = {name: {'type': 'character' if width else 'number', 'length': width or 8} for name, width in columns}
    return {'schema': schema, 'rows': [{name: str(value).ljust(width) if width else None if value is None else float(value)
                                      for (name, width), value in zip(columns, row, strict=True)} for row in values]}


COLUMNS = [('zebra', 3), ('alpha', 0), ('payload', 0), ('mark', 2)]
ORIGINAL_VALUES = [('B', 2, 10, 'X'), ('A', 1, 20, 'Y'), ('B', 2, 30, 'Z'),
                   ('A', None, 40, 'U'), ('', 9, 50, 'V'), ('A', 1, 60, 'W'),
                   ('a', -1, 70, 'M'), ('B', None, 80, 'N'), ('A', 1, 60, 'W'),
                   ('', 9, 90, 'P'), ('B', 2, 10, 'X'), ('A', None, 100, 'Q'),
                   ('C', -2, 110, 'R'), ('a', -1, 120, 'S')]


def view(raw, ordinals):
    return {'schema': deepcopy(raw['schema']), 'rows': [deepcopy(raw['rows'][i-1]) for i in ordinals]}


def logical_report(dataset, title):
    lines = [] if title is None else ['TITLE: ' + title]
    lines.append('obs ' + ' '.join(dataset['schema']))
    for i, row in enumerate(dataset['rows'], 1):
        fields = []
        for name, spec in dataset['schema'].items():
            value = row[name]
            if spec['type'] == 'character': fields.append(json.dumps(value.rstrip(' '), ensure_ascii=True))
            else:
                assert value is None or value == int(value)
                fields.append('.' if value is None else str(int(value)))
        lines.append(str(i) + ' ' + ' '.join(fields))
    return '\n'.join(lines) + '\n'


def report_events(title, dataset, name, content, rows):
    records = content.splitlines(); first = 0 if title is None else 1
    events = ['mixed-print|input|' + dataset + '|' + str(rows)]
    if title is not None: events.append('mixed-print|title|' + records[0].encode().hex())
    events.append('mixed-print|header|' + records[first].encode().hex())
    events.extend('mixed-print|row|' + line.encode().hex() for line in records[first+1:])
    events.append('mixed-print|output|' + name + '|' + str(len(content.encode())))
    return events


def input_trace(line, count):
    events = []
    for attempt in range(1, count+2):
        events.append({'kind': 'character_input', 'line': line, 'attempt': attempt, 'complete': attempt <= count})
        if attempt <= count: events.append({'kind': 'character_output', 'line': line, 'observation': attempt})
    return events


def original_expected():
    raw = table(COLUMNS, ORIGINAL_VALUES)
    firsts = view(raw, [5, 4, 2, 8, 1, 13, 7])
    extras = view(raw, [10, 12, 6, 9, 3, 11, 14])
    ranked = view(raw, [10, 12, 6, 8, 3, 13, 14])
    removed = view(raw, [5, 4, 9, 2, 1, 11, 7])
    before = view(raw, [14, 13, 12, 10, 8, 7, 6, 9, 5, 4, 3, 2, 1, 11])
    return {'datasets': {'raw': raw, 'ranked': ranked, 'firsts': firsts, 'extras': extras, 'ranked_removed': removed},
            'log': [], 'reports': {'print_01.txt': logical_report(before, 'Ranked before replacement'),
                                   'print_02.txt': logical_report(firsts, 'First encounter survivors'),
                                   'print_03.txt': logical_report(removed, 'Removed after replacement')}}


def original_trace():
    events = input_trace(4, 14)
    events.append({'event': 'sort', 'line': 22, 'source': 'raw', 'destination': 'ranked',
                   'source_ordinals': [14, 13, 12, 10, 8, 7, 6, 9, 5, 4, 3, 2, 1, 11],
                   'kept_ordinals': [14, 13, 12, 10, 8, 7, 6, 9, 5, 4, 3, 2, 1, 11]})
    reports = original_expected()['reports']
    def report(title, dataset, name, rows):
        events.append('title|set|' + title.encode().hex())
        events.extend(report_events(title, dataset, name, reports[name], rows))
    report('Ranked before replacement', 'ranked', 'print_01.txt', 14)
    events.append({'event': 'sort_dupout', 'line': 28, 'source': 'raw', 'destination': 'firsts',
                   'duplicate_destination': 'extras', 'replace': False,
                   'source_ordinals': [5, 10, 4, 12, 2, 6, 9, 8, 1, 3, 11, 13, 7, 14],
                   'kept_ordinals': [5, 4, 2, 8, 1, 13, 7], 'removed_ordinals': [10, 12, 6, 9, 3, 11, 14]})
    report('First encounter survivors', 'firsts', 'print_02.txt', 7)
    events.append({'event': 'sort_dupout', 'line': 34, 'source': 'ranked', 'destination': 'ranked',
                   'duplicate_destination': 'ranked_removed', 'replace': True,
                   'source_ordinals': [4, 9, 3, 10, 7, 8, 12, 5, 11, 13, 14, 2, 1, 6],
                   'kept_ordinals': [4, 3, 7, 5, 11, 2, 1], 'removed_ordinals': [9, 10, 8, 12, 13, 14, 6]})
    report('Removed after replacement', 'ranked_removed', 'print_03.txt', 7)
    events.append('title|reset')
    return events


def source(cards, columns='z :$3. n payload q :$2.', by='z n', *, replacement=False, reports=0, directed=False):
    text = ('data raw;\ninfile datalines dsd;\ninput ' + columns + ';\ndatalines4;\n'
            + ''.join(card + '\n' for card in cards) + ';;;;\nrun;\n')
    if replacement: text += 'proc sort data=raw out=ordered;\nby ' + ('descending payload' if directed else by) + ';\nrun;\n'
    text += 'proc sort data=' + ('ordered' if replacement else 'raw out=ordered') + ' dupout=removed nodupkey;\nby ' + by + ';\nrun;\n'
    for i in range(reports):
        text += 'title "Snapshot ' + str(i+1) + '";\nproc print data=' + ('raw', 'ordered', 'removed')[i % 3] + ';\nrun;\n'
    return text


def batch_witness(sources, r_name='sort_duplicates.R'):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory); paths = []
        for i, text in enumerate(sources):
            path = folder / f'{i}.sas'; path.write_text(text); paths.append(path)
        listing = folder / 'sources.txt'; listing.write_text(''.join(str(path) + '\n' for path in paths))
        rscript = os.environ.get('ROSETTA_RSCRIPT') or shutil.which('Rscript') or 'Rscript'
        run = subprocess.run([rscript, str(HERE / r_name), str(listing)], cwd=ROOT,
                             env={**os.environ, 'SASCHI_EXAMPLES_ROOT': str(ROOT / 'examples')},
                             text=True, capture_output=True, check=True, timeout=120)
    answers = []; active = None; current = None
    for line in run.stdout.splitlines():
        if line.startswith('BEGIN '):
            assert active is None; active = int(line[6:]); refused = False
            result = {'datasets': {}, 'log': []}; trace = []; accounting = None; reports = {}
        elif line == 'REFUSED': refused = True
        elif line == 'OK': pass
        elif line.startswith('TABLE '): current = {'schema': {}, 'rows': []}; result['datasets'][line[6:]] = current
        elif line.startswith('COL '):
            _, name, kind, width = line.split(); current['schema'][name] = {'type': kind, 'length': int(width)}
        elif line.startswith('ROW '):
            fields = [None if item == 'M' else bytes.fromhex(item[2:]).decode('ascii') if item.startswith('C:') else float(item[2:]) for item in line[4:].split('|')]
            current['rows'].append(dict(zip(current['schema'], fields, strict=True)))
        elif line == 'ENDTABLE': current = None
        elif line.startswith('ACCOUNT '): accounting = dict(zip(ACCOUNT_KEYS, map(int, line[8:].split()), strict=True))
        elif line.startswith('REPORT '):
            _, name, body = line.split(); reports[name] = bytes.fromhex(body).decode('ascii')
        elif line.startswith('EVENT '): trace.append(json.loads(line[6:]))
        elif line == 'END':
            assert active == len(answers) + 1
            if reports: result['reports'] = reports
            answers.append(None if refused else {'result': result, 'trace': trace, 'accounting': accounting}); active = None
        else: raise AssertionError((line, run.stderr))
    assert active is None and len(answers) == len(sources)
    return answers


def hand_partition(raw, keys, descending=False, deduplicate=True):
    def key(row):
        return tuple((0, 0) if row[name] is None else (1, row[name].rstrip(' ') if isinstance(row[name], str) else row[name]) for name in keys)
    # Python's stable sort is independent from the R insertion algorithm.
    ordered = sorted(range(1, len(raw['rows'])+1), key=lambda i:key(raw['rows'][i-1]), reverse=descending)
    kept = []; removed = []; previous = None
    for ordinal in ordered:
        current = key(raw['rows'][ordinal-1])
        (removed if deduplicate and current == previous else kept).append(ordinal)
        previous = current
    return view(raw, kept), view(raw, removed), ordered, kept, removed


def hand_case(values, by, replacement=False, reports=0, directed=False):
    raw = table([('z', 3), ('n', 0), ('payload', 0), ('q', 2)], values)
    before = hand_partition(raw, ['payload'] if directed else by, descending=directed, deduplicate=False)[0] if replacement else raw
    selected, removed, ordered, kept, discarded = hand_partition(before, by)
    result = {'datasets': {'raw': raw, 'ordered': selected, 'removed': removed}, 'log': []}
    count = len(values); trace = input_trace(3, count); header_line = count+7
    if replacement:
        _, _, initial_order, initial_kept, _ = hand_partition(raw, ['payload'] if directed else by, descending=directed, deduplicate=False)
        trace.append({'event': 'sort', 'line': header_line, 'source': 'raw', 'destination': 'ordered',
                      'source_ordinals': initial_order, 'kept_ordinals': initial_kept});header_line += 3
    trace.append({'event': 'sort_dupout', 'line': header_line, 'source': 'ordered' if replacement else 'raw', 'destination': 'ordered',
                  'duplicate_destination': 'removed', 'replace': replacement, 'source_ordinals': ordered,
                  'kept_ordinals': kept, 'removed_ordinals': discarded})
    if reports:
        result['reports'] = {}
        for i in range(reports):
            dataset = ('raw', 'ordered', 'removed')[i]; title = 'Snapshot ' + str(i+1);name = 'print_%02d.txt' % (i+1)
            content = logical_report(result['datasets'][dataset], title);result['reports'][name] = content
            trace.append('title|set|' + title.encode().hex());trace.extend(report_events(title, dataset, name, content, len(result['datasets'][dataset]['rows'])))
    return {'result': result, 'trace': trace, 'accounting': dict(zip(ACCOUNT_KEYS, [8+(3 if replacement else 0)+3*reports, count, count, count+1, count], strict=True))}


def generated_cases(count=72):
    rng = random.Random(7601);cases = []
    for i in range(count):
        fractional = i % 4 == 0
        values = [(rng.choice(['', 'A', 'B', 'a']), rng.choice([None, -2, -.5, 0, .5, 2] if fractional else [None, -2, 0, 2]),
                   rng.randrange(5), rng.choice(['X', 'Y', ''])) for _ in range(rng.randrange(25))]
        by = ['z', 'n'] if i % 2 else ['n', 'z']; replacement = False;reports = 0;directed = False
        cards = [','.join('.' if value is None else str(value) for value in row) for row in values]
        text = source(cards, by=' '.join(by), replacement=replacement, reports=reports, directed=directed)
        cases.append((text, hand_case(values, by, replacement, reports, directed)))
    return cases


def boundary_cases():
    full = source([])
    for i in range(62): full += f'proc sort data=raw out=s{i};by z;run;\n'
    titles = source([]) + 'title "A";\n' * 32
    return [source([]), source(['A,1,2,X']*1000),
            source(['A,-2147483647,1,X', 'B,2147483647,2,Y', ',.,3,Z']),
            source(['A,.5,1,X', ',.,2,Y', 'a,-.5,3,Z']),
            source(['Z'*64+',1'], columns='z :$64. n', by='z'),
            source([], columns='z :$1. ' + ' '.join('n'+str(i) for i in range(31)), by='z'),
            source([], columns='z :$1. ' + ' '.join('n'+str(i) for i in range(7)), by='z ' + ' '.join('n'+str(i) for i in range(7))),
            full, titles, source(['A,1,2,X']).replace('\n','\r\n')]


def refusal_cases():
    base = source([]);result = []
    for label, old, new in [('missing-nodupkey', ' nodupkey', ''),
                            ('dupout-input', 'dupout=removed', 'dupout=raw'), ('dupout-output', 'dupout=removed', 'dupout=ordered'),
                            ('explicit-inplace', 'out=ordered', 'out=raw'), ('direct-producer-replacement', ' out=ordered', ''),
                            ('by-unknown','by z n','by absent'), ('by-duplicate','by z n','by z z'),
                            ('by-descending','by z n','by descending z'), ('by-all','by z n','by _all_'),
                            ('by-empty','by z n','by'), ('input-keep','data=raw out','data=raw(keep=z n) out'),
                            ('input-drop','data=raw out','data=raw(drop=q) out'), ('output-option','out=ordered','out=ordered(keep=z)'),
                            ('dupout-option','dupout=removed','dupout=removed(keep=z)'), ('unknown-option',' nodupkey',' nodupkey force'),
                            ('option-order',' out=ordered dupout=removed',' dupout=removed out=ordered')]:
        result.append((label, base.replace(old,new)))
    result += [('fourth-report', source([], reports=4)), ('fractional-print', source(['A,.5,1,X'], reports=1)),
               ('no-run', base.rsplit('run;',1)[0]), ('extra-statement', base.replace('by z n;', 'by z n;where n=1;')),
               ('rows1001',source(['A,1,2,X']*1001)), ('width65',source([], columns='z :$65. n',by='z')),
               ('columns33',source([],columns='z :$1. ' + ' '.join('n'+str(i) for i in range(32)),by='z')),
               ('by9',source([],columns='z :$1. ' + ' '.join('n'+str(i) for i in range(8)),by='z ' + ' '.join('n'+str(i) for i in range(8)))),
               ('step65',boundary_cases()[7]+'proc sort data=raw out=excess;by z;run;\n'),
               ('title33',boundary_cases()[8]+'title "B";\n'), ('nonascii',source(['A,1,2,é'])),
               ('inexact',source(['A,0.1,2,X'])), ('tagged',source(['A,.A,2,X'])), ('quoted',source(['"A",1,2,X'])),
               ('empty-invalid-descriptor',source([], columns='z :$0. n',by='z')),
               ('sort-replacement-other',source([], replacement=True).replace('data=ordered dupout','data=raw dupout')),
               ('legacy-inplace',source([], replacement=True).replace('data=raw out=ordered','data=raw')),
               ('reuse-dupout',base+'proc sort data=raw out=second dupout=removed nodupkey;by z;run;\n'),
               ('reuse-survivor',base+'proc sort data=raw out=ordered dupout=second nodupkey;by z;run;\n')]
    return result


def qualify_anchor(witness=batch_witness):
    text = ORIGINAL.read_text();truth = original_expected();trace = original_trace()
    if SOURCE_PIN: assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == SOURCE_PIN
    if RESULT_PIN: assert digest(truth) == RESULT_PIN
    if TRACE_PIN: assert digest(trace) == TRACE_PIN
    assert not any(name == 'saschi' or name.startswith('saschi.') or name == 'sas_semantics' for name in sys.modules)
    independent = witness([text])[0]
    exact(independent['result'],truth);exact(independent['trace'],trace)
    exact(independent['accounting'],dict(zip(ACCOUNT_KEYS,[24,14,14,15,14],strict=True)))
    extras = truth['datasets']['extras']['rows'];raw=truth['datasets']['raw']
    assert extras != view(raw,[3,6,9,10,11,12,14])['rows']
    assert extras.count(raw['rows'][8]) == 2 and len(extras) == 7
    assert truth['reports']['print_01.txt'] != logical_report(truth['datasets']['ranked'],'Ranked before replacement')
    return {'original':text,'truth':truth,'trace':trace,'anchor':independent}


def family_selection_controls():
    return [('legacy-no-dupout',source([]).replace(' dupout=removed',''))]


def qualify():
    q = qualify_anchor();generated = generated_cases();boundaries = boundary_cases();refused = refusal_cases();selection = family_selection_controls()
    sources = [text for text,_ in generated] + boundaries + [text for _,text in refused] + [text for _,text in selection]
    independent = batch_witness(sources)
    for (_,expected),answer in zip(generated,independent[:len(generated)],strict=True):exact(answer,expected)
    assert all(item is not None for item in independent[len(generated):len(generated)+len(boundaries)])
    for (label,_),answer in zip(refused,independent[len(generated)+len(boundaries):len(generated)+len(boundaries)+len(refused)],strict=True):assert answer is None,label
    for (label,_),answer in zip(selection,independent[len(generated)+len(boundaries)+len(refused):],strict=True):assert answer is None,label
    return {**q,'generated':generated,'boundaries':boundaries,'refused':refused,'selection':selection,'sources':sources,'independent':independent}


def qualification_record(q):
    return {'status':'Independent first-party complete-source hand/base-R oracle qualification for maintainer review. No new translator imports/comparisons, live SAS or implementation acceptance.',
            'passed':True,'original_language_statements':24,'original_opaque_payloads':1,'original_physical_rows':14,'original_input_attempts':15,
            'original_outputs':14,'original_steps':11,'original_trace_events':len(q['trace']),
            'generated_programs':len(q['generated']),'positive_boundaries':len(q['boundaries']),'shared_source_refusals':len(q['refused']),'new_family_selection_controls':len(q.get('selection',[])),
            'complete_original_result_equal':True,'complete_original_trace_equal':True,'complete_generated_result_trace_accounting_equal':True,
            'actual_new_translator_comparisons':0,'new_translator_imports':0,
            'result_policy_sha256':digest(q['truth']),'trace_policy_sha256':digest(q['trace']),
            'reports':[{'name':name,'bytes':len(body.encode()),'sha256':hashlib.sha256(body.encode()).hexdigest()} for name,body in q['truth']['reports'].items()]}


# Post-freeze runtime adapters below. Hand/R expectations above are unchanged.
def execute(text):
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    from saschi.emit_py import translate
    from saschi.sort_duplicates import run_program
    plan = compile_plan(text);assert not plan.blocked, plan.tickets
    portable=plan.to_dict();before=deepcopy(portable);trace=[]
    result=run_plan(portable);exact(portable,before)
    exact(run_program(portable,trace=trace),result);exact(portable,before)
    namespace={};output=io.StringIO()
    with contextlib.redirect_stdout(output):exec(translate(text).code,namespace)
    exact(namespace['result'],result);assert output.getvalue()==''
    return result,trace


def check_refused(label,text):
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    plan=compile_plan(text)
    if not plan.blocked:
        try:run_plan(plan.to_dict())
        except (ValueError,TypeError,KeyError,RecursionError):pass
        else:raise AssertionError(label)


def check_old_selection(label,text):
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    plan=compile_plan(text);assert not plan.blocked,(label,plan.tickets)
    assert not any(step.kind in ('duplicate_sort','duplicate_print') for step in plan.steps),label
    assert run_plan(plan.to_dict()) is not None


def cli_check(text,truth,wrong=False):
    from saschi.cli import main
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);src=folder/'input.sas';src.write_text(text)
        expected=folder/'expected.json';expected.write_text(json.dumps(truth['datasets']))
        reports=folder/'reports.json';reports.write_text(json.dumps(truth.get('reports',{})))
        output=folder/'job';console=io.StringIO()
        argv=['run',str(src),'--expect',str(expected),'--output',str(output)]
        if 'reports' in truth:argv+=['--expect-reports',str(reports)]
        with contextlib.redirect_stdout(console):code=main(argv)
        receipt=json.loads((output/'receipt.json').read_text())
        assert code==(1 if wrong else 0),(code,receipt.get('error'))
        assert receipt['accepted'] is (not wrong)
        assert receipt['source_sha256']==hashlib.sha256(src.read_bytes()).hexdigest()
        assert not (output/'exports').exists()
        if wrong:
            assert not (output/'result.json').exists() and (output/'observed.json').is_file()
            assert not (output/'reports').exists()
        else:
            exact(json.loads((output/'result.json').read_text()),truth)
            if 'reports' in truth:
                assert receipt['report_contract']=='ascii-dupout-mixed-integer-v1'
                assert sorted(path.name for path in (output/'reports').iterdir())==sorted(truth['reports'])
                for name,body in truth['reports'].items():assert (output/'reports'/name).read_bytes()==body.encode()
        assert not list(folder.glob('.job.*'))
    return receipt


def cli_source_refusal(text):
    from saschi.cli import main
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);src=folder/'refused.sas';src.write_text(text);output=folder/'job'
        with contextlib.redirect_stdout(io.StringIO()):code=main(['run',str(src),'--output',str(output)])
        receipt=json.loads((output/'receipt.json').read_text())
        assert code in (1,2) and receipt['accepted'] is False
        assert not any((output/name).exists() for name in ('result.json','observed.json','reports','exports'))
        assert not list(folder.glob('.job.*'))
    return 1


def wrong_partition_cases(truth):
    result=[]
    for mode in ('last-survivor','missing-removed','equal-row-multiplicity','reversed-removed','encounter-order',
                 'descriptor-order','padding','survivor-leak','removed-value'):
        wrong=deepcopy(truth);tables=wrong['datasets'];extras=tables['extras'];firsts=tables['firsts']
        if mode=='last-survivor':firsts['rows'][0]['payload']=90.
        elif mode=='missing-removed':extras['rows'].pop()
        elif mode=='equal-row-multiplicity':extras['rows'].pop(3)
        elif mode=='reversed-removed':extras['rows'].reverse()
        elif mode=='encounter-order':extras['rows']=view(tables['raw'],[3,6,9,10,11,12,14])['rows']
        elif mode=='descriptor-order':extras['schema']=dict(reversed(list(extras['schema'].items())))
        elif mode=='padding':extras['rows'][0]['zebra']=''
        elif mode=='survivor-leak':extras['rows'].append(deepcopy(firsts['rows'][0]))
        else:extras['rows'][0]['payload']=-999.
        result.append((mode,wrong))
    return result


def comparator_refuses(actual,wrong):
    try:exact(actual,wrong)
    except AssertionError:return
    raise AssertionError('known-wrong complete comparator control admitted')


def trace_controls(trace):
    controls=[]
    for mode in ('removed-order','missing-removed','partition-leak','replace-flag','source-ordinal','destination','omitted-event'):
        wrong=deepcopy(trace);event=next(item for item in wrong if type(item) is dict and item.get('event')=='sort_dupout')
        if mode=='removed-order':event['removed_ordinals'].reverse()
        elif mode=='missing-removed':event['removed_ordinals'].pop()
        elif mode=='partition-leak':event['removed_ordinals'].append(event['kept_ordinals'][0])
        elif mode=='replace-flag':event['replace']=True
        elif mode=='source-ordinal':event['source_ordinals'][0]=999
        elif mode=='destination':event['duplicate_destination']='wrong'
        else:wrong.remove(event)
        controls.append(wrong)
    for wrong in controls:comparator_refuses(trace,wrong)
    return len(controls)


def portable_refusals():
    from saschi.plan import compile_plan
    from saschi.sort_duplicates import execute_partition,run_program
    plan=compile_plan(source([])).to_dict();step=next(item for item in plan['steps'] if item['kind']=='duplicate_sort')
    empty=table([('z',3),('n',0),('payload',0),('q',2)],[]);count=0
    def rejected(s=step,t=empty,version=2):
        nonlocal count
        prior=json.dumps(t,separators=(',',':'))
        try:execute_partition(s,{'raw':t},version=version)
        except (ValueError,TypeError,KeyError,RecursionError):pass
        else:raise AssertionError(s)
        assert json.dumps(t,separators=(',',':'))==prior;count+=1
    for name,value in [('by',['z']),('nodupkey',True),('line',True),('inputs',[]),('name','raw'),('extra',1),('where',True)]:
        changed=deepcopy(step);changed[name]=value;rejected(changed)
    for name,value in [('by',[]),('by',['z','z']),('by',['absent']),('by',['descending','z']),('by',('z',)),
                       ('dupout','raw'),('dupout','ordered'),('dupout','Bad'),('replace',1),('replace',True),
                       ('source_lines',[]),('source_lines',[True,3]),('profile','old-sort'),('extra',1)]:
        changed=deepcopy(step);changed['operations'][0]['args'][name]=value;rejected(changed)
    for name in ('profile','by','dupout','replace','source_lines'):
        changed=deepcopy(step);del changed['operations'][0]['args'][name];rejected(changed)
    rejected(version=True)
    for value in [True,float('nan'),'.A',2147483648,.1]:
        changed=deepcopy(empty);changed['rows']=[{'z':'A  ','n':value,'payload':1.,'q':'X '}];rejected(t=changed)
    changed=deepcopy(empty);changed['schema']['q']['length']=True;rejected(t=changed)
    changed=deepcopy(empty);changed['rows']=[{'z':'A  ','n':1.,'payload':1.,'q':'é '}];rejected(t=changed)
    changed=deepcopy(step);changed['operations'][0]['args']['by'].append(changed);rejected(changed)
    for changed,catalog in [(deepcopy(plan),{'external':empty}),(deepcopy(plan),None)]:
        if catalog is None:changed['steps'][0]['operations'][0]['args']['hidden']={'profile':'sort-dupout-v1'}
        try:run_program(changed,catalog)
        except (ValueError,TypeError,KeyError,RecursionError):count+=1
        else:raise AssertionError('supplied catalog or hidden marker admitted')
    return count


def preflight_and_once(text):
    from saschi.plan import compile_plan
    from saschi.runtime import run_plan
    from saschi import sort_duplicates
    plan=compile_plan(text).to_dict();calls=[];real=sort_duplicates.execute_partition
    def forbidden(*args,**kwargs):raise AssertionError('preflight executed partition')
    with patch.object(sort_duplicates,'execute_partition',forbidden),patch.object(sort_duplicates.existing,'execute_sort',forbidden):
        sort_duplicates.validate_program(plan)
    def counted(*args,**kwargs):
        answer=real(*args,**kwargs);calls.append(args[0]['name']);return answer
    joins=[];real_sort=sort_duplicates.existing.execute_sort
    def join_counted(*args,**kwargs):
        answer=real_sort(*args,**kwargs);joins.append(args[0]['name']);return answer
    with patch.object(sort_duplicates,'execute_partition',counted),patch.object(sort_duplicates.existing,'execute_sort',join_counted):
        run_plan(plan)
    assert calls==['firsts','ranked'] and joins==['ranked'],(calls,joins)
    return len(calls)


def atomic_check(text,mode):
    from saschi import sort_duplicates
    from saschi.cli import main
    real_partition=sort_duplicates.execute_partition;real_print=sort_duplicates.execute_print
    partitions=[];reports=[]
    def partitioned(*args,**kwargs):
        result=real_partition(*args,**kwargs);partitions.append(deepcopy(result))
        if mode=='partition' and len(partitions)==1:raise ValueError('DUPOUT fresh partition late runtime fault')
        if mode=='replacement' and len(partitions)==2:raise ValueError('DUPOUT replacement late runtime fault')
        return result
    def printed(*args,**kwargs):
        result=real_print(*args,**kwargs);reports.append(deepcopy(result))
        if mode=='third-report' and len(reports)==3:raise ValueError('DUPOUT third report late runtime fault')
        return result
    messages={'partition':'DUPOUT fresh partition late runtime fault','replacement':'DUPOUT replacement late runtime fault','third-report':'DUPOUT third report late runtime fault'}
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);src=folder/'original.sas';src.write_text(text);output=folder/'job'
        with patch.object(sort_duplicates,'execute_partition',partitioned),patch.object(sort_duplicates,'execute_print',printed),contextlib.redirect_stdout(io.StringIO()):
            code=main(['run',str(src),'--output',str(output)])
        receipt=json.loads((output/'receipt.json').read_text())
        assert code==1 and receipt['accepted'] is False and receipt['error']==messages[mode],receipt
        assert len(partitions)==(1 if mode=='partition' else 2)
        assert len(reports)=={'partition':1,'replacement':2,'third-report':3}[mode] and all(reports)
        assert not any((output/name).exists() for name in ('result.json','observed.json','reports','exports'))
        assert not list(folder.glob('.job.*'))
    return 1


def run():
    q=qualify();result,trace=execute(q['original']);exact(result,q['truth']);exact(trace,q['trace'])
    for (text,expected) in q['generated']:
        actual,events=execute(text);exact(actual,expected['result']);exact(events,expected['trace'])
    start=len(q['generated'])
    for text,witness in zip(q['boundaries'],q['independent'][start:start+len(q['boundaries'])],strict=True):
        actual,events=execute(text);exact(actual,witness['result']);exact(events,witness['trace'])
    for label,text in q['refused']:check_refused(label,text)
    for label,text in q['selection']:check_old_selection(label,text)
    cli_check(q['original'],q['truth'])
    wrong=wrong_partition_cases(q['truth'])
    for _,incorrect in wrong:comparator_refuses(result,incorrect);cli_check(q['original'],incorrect,True)
    negative=cli_source_refusal(next(text for label,text in q['refused'] if label=='dupout-input'))
    summary={'construct':'sort-dupout','original_statements':24,'original_rows':14,'input_attempts':15,'full_runtime_events':76,
             'generated':len(q['generated']),'positive_boundaries':len(q['boundaries']),'source_refusals':len(q['refused']),
             'old_family_controls':len(q['selection']),'portable_refusals':portable_refusals(),'wrong_actual_cli_datasets':len(wrong),
             'wrong_full_trace_controls':trace_controls(trace),'actual_negative_cli':negative,
             'once_partition_executions':preflight_and_once(q['original']),'late_actual_cli_faults':atomic_check(q['original'],'partition')}
    print('sort-dupout: '+json.dumps(summary,sort_keys=True));return summary


if __name__=='__main__':run()
