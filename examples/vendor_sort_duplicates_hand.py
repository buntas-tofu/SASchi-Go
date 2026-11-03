"""Independent complete immutable SORT5 expectations under reviewed repository policy.

No translator or semantic helper imports. Source and full results stay external.
"""
from copy import deepcopy
import hashlib
import json
import re
from vendor_sort_options_lex import scan, classify

SOURCE_SHA256='713bbf5931e7bd5416594929a2176bdddc60d383b95ec09fe81ff7f4eafda9db'
SOURCE_BYTES=2132
LINES=[13,14,15,19,35,37,38,39,41,42,43,45,46,47,49,50,51,53,54,55,56]
KINDS=['data','infile','input','datalines4','run','title_set','proc_print','run',
       'proc_sort','by','run','proc_sort','by','run','title_set','proc_print','run',
       'title_set','proc_print','run','title_reset']
FIRST=[3,5,4,10,12,11,13,14,2,1,6,7,8,9]
SECOND=list(range(1,15))
KEPT=[1,3,4,5,7,8,9,10,11,12,13,14]
REMOVED=[2,6]


def encode(value):
    return (json.dumps(value,ensure_ascii=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def title(text):
    literal=text[5:].strip();delimiter=literal[0]
    if delimiter not in ('"',"'") or literal[-1]!=delimiter:raise ValueError('one TITLE literal required')
    return literal[1:-1].replace(delimiter*2,delimiter)


def report(table,text):
    records=['TITLE: '+text,'obs '+' '.join(table['schema'])]
    for index,row in enumerate(table['rows'],1):
        values=[]
        for name,spec in table['schema'].items():
            value=row[name]
            if spec['type']=='character':values.append(json.dumps(value.rstrip(' ')))
            elif value is None:values.append('.')
            elif type(value) in (int,float) and value==int(value):values.append(str(int(value)))
            else:raise ValueError('integer report frontier')
        records.append(str(index)+' '+' '.join(values))
    return '\n'.join(records)+'\n'


def build(original):
    if len(original)!=SOURCE_BYTES or hashlib.sha256(original).hexdigest()!=SOURCE_SHA256:
        raise ValueError('whole unchanged SORT5 source required')
    statements,events=scan(original.decode('ascii'))
    if [s['line'] for s in statements]!=LINES or [classify(s['text']) for s in statements]!=KINDS:
        raise ValueError('complete statement accounting differs')
    texts=[s['text'] for s in statements];normalized=[' '.join(text.lower().split()) for text in texts]
    exact={0:'data classtest',1:'infile datalines dsd',3:'datalines4',4:'run',
           6:'proc print data=classtest',7:'run',8:'proc sort data=classtest out=classtest_sort',
           9:'by name subject descending score',10:'run',
           11:'proc sort data=classtest_sort dupout=classtest_dups nodupkey',12:'by name subject',13:'run',
           15:'proc print data=classtest_sort',16:'run',18:'proc print data=classtest_dups',19:'run',20:'title'}
    if any(normalized[index]!=text for index,text in exact.items()):raise ValueError('whole finite grammar differs')
    declarations=re.findall(r'([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*\$([0-9]+)\.)?',texts[2][5:])
    if [(name.lower(),width) for name,width in declarations]!=[('name','7'),('subject','7'),('score','')]:
        raise ValueError('source descriptor order differs')
    schema={'name':{'type':'character','length':7},'subject':{'type':'character','length':7},
            'score':{'type':'number','length':8}}
    payload,=[e for e in events if e['kind']=='opaque_data']
    if payload['line']!=20 or payload['terminator_line']!=34 or len(payload['records'])!=14:
        raise ValueError('whole physical payload differs')
    rows=[]
    for card in payload['records']:
        values=card.split(',')
        if len(values)!=3 or any(v!=v.strip(' ') for v in values) or not re.fullmatch(r'[0-9]+',values[2]):
            raise ValueError('finite original card grammar differs')
        if any(len(value)>7 for value in values[:2]):raise ValueError('character width differs')
        rows.append({'name':values[0].ljust(7),'subject':values[1].ljust(7),'score':float(values[2])})
    raw={'schema':deepcopy(schema),'rows':rows}
    # Literal hand ordinal pins above precede any new translator execution.
    if FIRST!=sorted(range(1,15),key=lambda i:(rows[i-1]['name'].encode('ascii'),rows[i-1]['subject'].encode('ascii'),-rows[i-1]['score'],i)):
        raise ValueError('hand directed order does not qualify against source')
    first={'schema':deepcopy(schema),'rows':[deepcopy(rows[i-1]) for i in FIRST]}
    if SECOND!=sorted(range(1,15),key=lambda i:(first['rows'][i-1]['name'].encode('ascii'),first['rows'][i-1]['subject'].encode('ascii'),i)):
        raise ValueError('hand second sorted stream does not qualify')
    seen=set();kept=[];removed=[]
    for ordinal in SECOND:
        row=first['rows'][ordinal-1];key=(row['name'],row['subject'])
        (removed if key in seen else kept).append(ordinal);seen.add(key)
    if kept!=KEPT or removed!=REMOVED:raise ValueError('hand partition differs')
    if [FIRST[i-1] for i in REMOVED]!=[5,11] or rows[2]!=rows[4] or not rows[10]['score']<rows[11]['score']:
        raise ValueError('equal-score tie and lower score identities differ')
    survivor={'schema':deepcopy(schema),'rows':[deepcopy(first['rows'][i-1]) for i in KEPT]}
    duplicates={'schema':deepcopy(schema),'rows':[deepcopy(first['rows'][i-1]) for i in REMOVED]}
    titles=[title(texts[index]) for index in (5,14,17)]
    artifacts={name:report(table,text) for name,table,text in zip(
        ('print_01.txt','print_02.txt','print_03.txt'),(raw,survivor,duplicates),titles)}
    result={'datasets':{'classtest':raw,'classtest_sort':survivor,'classtest_dups':duplicates},'log':[],'reports':artifacts}
    sorts=[{'line':41,'source_ordinals':FIRST,'kept_ordinals':FIRST,'removed_ordinals':[]},
           {'line':45,'source_ordinals':SECOND,'kept_ordinals':KEPT,'removed_ordinals':REMOVED}]
    accounting={'language_statements':21,'opaque_payloads':1,'steps':10,'input_records':14,
                'data_iterations':14,'input_attempts':15,'implicit_outputs':14,'sort_rows':28,'sorts':sorts,
                'title_sets':3,'title_resets':1,'prints':3,'report_records':[16,14,4],'final_title':None}
    trace=[{'event':'data_begin','line':13,'table':'classtest'}]
    for i in range(1,15):
        trace.append({'event':'input_attempt','line':15,'record':i,'record_line':19+i,'eof':False})
        trace.append({'event':'implicit_output','table':'classtest','observation':i})
    trace.extend([{'event':'input_attempt','line':15,'record':15,'eof':True},
                  {'event':'data_end','line':35,'table':'classtest','rows':14},
                  {'event':'title_set','line':37,'text':titles[0]},
                  {'event':'print','line':38,'table':'classtest','report':'print_01.txt','rows':14,'title':titles[0]},
                  {'event':'sort','line':41,'source':'classtest','destination':'classtest_sort',
                   'source_ordinals':FIRST,'kept_ordinals':FIRST},
                  {'event':'sort_dupout','line':45,'source':'classtest_sort','destination':'classtest_sort',
                   'duplicate_destination':'classtest_dups','replace':True,'source_ordinals':SECOND,
                   'kept_ordinals':KEPT,'removed_ordinals':REMOVED},
                  {'event':'title_set','line':49,'text':titles[1]},
                  {'event':'print','line':50,'table':'classtest_sort','report':'print_02.txt','rows':12,'title':titles[1]},
                  {'event':'title_set','line':53,'text':titles[2]},
                  {'event':'print','line':54,'table':'classtest_dups','report':'print_03.txt','rows':2,'title':titles[2]},
                  {'event':'title_reset','line':56}])
    if len(trace)!=40:raise ValueError('complete semantic event count differs')
    return result,accounting,trace


def bodies(original):
    result,accounting,trace=build(original)
    return {'result.json':encode(result),'accounting.json':encode(accounting),'trace.json':encode(trace),
            **{name:text.encode('ascii') for name,text in result['reports'].items()}}
