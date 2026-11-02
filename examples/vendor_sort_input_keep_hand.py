"""Pinned independent expectations for one whole external input KEEP program.

No translator or semantic helper imports; vendor bodies remain external.
"""
from copy import deepcopy
import hashlib
import json
import re
from vendor_sort_options_lex import scan, classify

SOURCE_SHA256 = '1629f949f87db58983ea06f8fab23d9ca2c7b96e9e360ad5ffda26d3180b1fc1'
SOURCE_BYTES = 1824
LINES = [13,14,15,19,35,37,38,39,41,42,43,45,46,47,48]
KINDS = ['data','infile','input','datalines4','run','title_set','proc_print','run',
         'proc_sort','by','run','title_set','proc_print','run','title_reset']
ORDER = [3,4,5,10,11,12,13,14,1,2,6,7,8,9]
KEPT = [3,10,13,1,6,8]


def encode(value):
    return (json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def title(text):
    literal=text[5:].strip();delimiter=literal[0]
    if delimiter not in ('"',"'") or literal[-1]!=delimiter:
        raise ValueError('one independent TITLE literal required')
    return literal[1:-1].replace(delimiter*2,delimiter)


def report(table,text):
    records=['TITLE: '+text,'obs '+' '.join(table['schema'])]
    for index,row in enumerate(table['rows'],1):
        values=[]
        for name,spec in table['schema'].items():
            value=row[name]
            if spec['type']=='character':values.append(json.dumps(value.rstrip(' ')))
            elif value is None:values.append('.')
            elif isinstance(value,(int,float)) and value==int(value):values.append(str(int(value)))
            else:raise ValueError('independent integer report frontier')
        records.append(str(index)+' '+' '.join(values))
    return '\n'.join(records)+'\n'


def build(original):
    if len(original)!=SOURCE_BYTES or hashlib.sha256(original).hexdigest()!=SOURCE_SHA256:
        raise ValueError('whole unchanged SORT4 source required')
    statements,events=scan(original.decode('ascii'))
    if [s['line'] for s in statements]!=LINES or [classify(s['text']) for s in statements]!=KINDS:
        raise ValueError('whole-source statement accounting differs')
    texts=[s['text'] for s in statements]
    normalized=[' '.join(s.lower().split()) for s in texts]
    if normalized[0]!='data classtest' or normalized[1]!='infile datalines dsd' or normalized[9]!='by name':
        raise ValueError('independent source grammar differs')
    declarations=re.findall(r'([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*\$([0-9]+)\.)?',texts[2][5:])
    if [(name.lower(),width) for name,width in declarations]!=[('name','7'),('subject','7'),('score','')]:
        raise ValueError('source INPUT descriptor declarations differ')
    schema={'name':{'type':'character','length':7},'subject':{'type':'character','length':7},
            'score':{'type':'number','length':8}}
    payload,=[e for e in events if e['kind']=='opaque_data']
    if payload['line']!=20 or payload['terminator_line']!=34 or len(payload['records'])!=14:
        raise ValueError('complete physical payload accounting differs')
    rows=[]
    for card in payload['records']:
        values=card.split(',')
        if len(values)!=3 or any(v!=v.strip(' ') for v in values) or not re.fullmatch(r'[0-9]+',values[2]):
            raise ValueError('finite original input record frontier')
        if any(len(value)>7 for value in values[:2]):raise ValueError('source character width differs')
        rows.append({'name':values[0].ljust(7),'subject':values[1].ljust(7),'score':float(values[2])})
    raw={'schema':deepcopy(schema),'rows':rows}
    sort=re.fullmatch(r'proc\s+sort\s+data\s*=\s*(\w+)\s*\(\s*keep\s*=\s*(\w+)\s*\)\s+out\s*=\s*(\w+)\s+nodupkey',texts[8],re.I)
    if sort is None or tuple(s.lower() for s in sort.groups())!=('classtest','name','classtest_sort'):
        raise ValueError('exact original input-side KEEP/NODUPKEY boundary differs')
    # Hand ordinals predate the new translator. Sorting below only qualifies the
    # pin against source values; it does not supply its initial expected order.
    if ORDER!=sorted(range(1,15),key=lambda i:(rows[i-1]['name'].encode('ascii'),i)):
        raise ValueError('hand stable Name order differs')
    selected=[name for name in schema if name=='name']
    observed=[];seen=set()
    for ordinal in ORDER:
        key=rows[ordinal-1]['name'].rstrip(' ')
        if key not in seen:observed.append(ordinal)
        seen.add(key)
    if observed!=KEPT:raise ValueError('hand first-survivor pin differs')
    ordered={'schema':{name:deepcopy(schema[name]) for name in selected},
             'rows':[{name:deepcopy(rows[i-1][name]) for name in selected} for i in KEPT]}
    before,after=title(texts[5]),title(texts[11])
    artifacts={'print_01.txt':report(raw,before),'print_02.txt':report(ordered,after)}
    result={'datasets':{'classtest':raw,'classtest_sort':ordered},'log':[],'reports':artifacts}
    accounting={'language_statements':15,'opaque_payloads':1,'steps':7,'input_records':14,
                'data_iterations':14,'input_attempts':15,'implicit_outputs':14,'sort_rows':14,
                'sort_source_ordinals':ORDER,'sort_kept_ordinals':KEPT,'title_sets':2,'title_resets':1,
                'prints':2,'report_records':[16,8],'final_title':None}
    trace=[{'event':'data_begin','line':13,'table':'classtest'}]
    for i in range(1,15):
        trace.append({'event':'input_attempt','line':15,'record':i,'record_line':19+i,'eof':False})
        trace.append({'event':'implicit_output','table':'classtest','observation':i})
    trace.extend([{'event':'input_attempt','line':15,'record':15,'eof':True},
                  {'event':'data_end','line':35,'table':'classtest','rows':14},
                  {'event':'title_set','line':37,'text':before},
                  {'event':'print','line':38,'table':'classtest','report':'print_01.txt','rows':14,'title':before},
                  {'event':'sort','line':41,'source':'classtest','destination':'classtest_sort',
                   'source_ordinals':ORDER,'kept_ordinals':KEPT},
                  {'event':'title_set','line':45,'text':after},
                  {'event':'print','line':46,'table':'classtest_sort','report':'print_02.txt','rows':6,'title':after},
                  {'event':'title_reset','line':48}])
    if len(trace)!=37:raise ValueError('hand complete event count differs')
    return result,accounting,trace


def bodies(original):
    result,accounting,trace=build(original)
    return {'result.json':encode(result),'accounting.json':encode(accounting),'trace.json':encode(trace),
            **{name:text.encode('ascii') for name,text in result['reports'].items()}}
