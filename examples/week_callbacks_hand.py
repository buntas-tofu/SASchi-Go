"""Independent source-reading week callback and ordered/spanned REPORT oracle."""
from copy import deepcopy
from datetime import timedelta
import json
import re
from format_oracle_scan import scan
from groupformat_hand import data
from picture_dates_hand import EPOCH,MONTHS

NAME=r'[A-Za-z_][A-Za-z0-9_]{0,31}'
WEEKDAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
FULLMONTHS=['January','February','March','April','May','June','July','August','September','October','November','December']


def function(block):
    m=re.fullmatch(r'function\s+('+NAME+r')\s*\(\s*('+NAME+r')\s*\)\s*\$\s*9',block[0],re.I);assert m
    d=re.fullmatch(r'('+NAME+r')\s*=\s*intnx\(\s*\x27week\.([27])\x27\s*,\s*'+re.escape(m[2])+r'\s*,\s*([01])\s*\)\s*(?:-\s*(1))?',block[1],re.I);assert d
    assert (int(d[2]),int(d[3]),-int(d[4] or 0)) in [(2,0,0),(7,1,-1)]
    assert re.fullmatch(r'return\s*\(\s*put\(\s*'+re.escape(d[1])+r'\s*,\s*date9\.\s*\)\s*\)',block[2],re.I) and block[3].lower()=='endsub'
    return m[1].lower(),(int(d[2]),int(d[3]),-int(d[4] or 0))


def callback(value,definition):
    if value is None:return '.'
    date=EPOCH+timedelta(days=int(value));anchor,offset,adjust=definition
    # A calendar walk supplies the oracle independently of runtime modular math.
    target=0 if anchor==2 else 5
    while date.weekday()!=target:date-=timedelta(days=1)
    date+=timedelta(days=offset*7+adjust)
    assert 1753<=date.year<=3999
    return f'{date.day:02}{MONTHS[date.month-1]}{date.year:04}'


def columns(text):
    head=re.fullmatch(r'columns?\s+(.+)\s*\(\s*(\x27(?:[^\x27]|\x27\x27)*\x27)\s+(.+)\)',text,re.I|re.S);assert head
    result=[];span=head[2][1:-1].replace("''","'")
    for section,heading in [(head[1],None),(head[3],span)]:
        for token in section.split():
            pair=token.lower().split('=');assert len(pair) in (1,2)
            result.append({'source':pair[0],'alias':pair[-1],'span':heading})
    return result


def definition(text):
    head=re.fullmatch(r'define\s+('+NAME+r')\s*/\s*(.+)',text,re.I|re.S);assert head
    result={'display':False,'order':False,'format':None,'label':None}
    for token in re.findall(r"'(?:[^']|'')*'|[^\s]+",head[2]):
        lower=token.lower()
        if lower in ('order','display'):result[lower]=True
        elif lower.startswith('format='):result['format']=lower[7:-1]
        elif token.startswith("'"):result['label']=token[1:-1].replace("''","'")
        else:raise ValueError('unqualified callback report definition')
    return head[1].lower(),result


def build(source):
    statements,events=scan(source);texts=[s['text'] for s in statements];payloads=iter(e for e in events if e['kind']=='opaque_data')
    tables={};functions={};formats={};reports={};trace=[];title=None;library=None;active=None;i=0;steps=0;inputs=0;producers=0;titles=0;calls=0
    while i<len(texts):
        text=texts[i];norm=' '.join(text.lower().split())
        if norm.startswith('proc fcmp '):
            m=re.fullmatch(r'proc\s+fcmp\s+outlib\s*=\s*(work\.functions)\.('+NAME+r')',text,re.I);assert m
            library=m[1].lower();i+=1;count=0
            while texts[i].lower().startswith('function '):
                name,body=function(texts[i:i+4]);assert name not in functions;functions[name]=body
                trace.append(f'week_function|{name}|{body[0]}|{body[1]}|{body[2]}');count+=1;i+=4
            assert texts[i].lower()=='quit';trace.append(f'week_library|{library}|{m[2].lower()}|{count}');i+=1;steps+=1
        elif norm.startswith('options '):
            m=re.fullmatch(r'options\s+cmplib\s*=\s*(work\.functions)',text,re.I);assert m and m[1].lower()==library;active=library
            trace.append('week_cmplib|'+active);i+=1;steps+=1
        elif norm=='proc format':
            assert active==library;i+=1
            while texts[i].lower().startswith('value '):
                m=re.fullmatch(r'value\s+('+NAME+r')\s+other\s*=\s*\[\s*('+NAME+r')\s*\(\s*\)\s*\]',texts[i],re.I);assert m and m[2].lower() in functions
                name=m[1].lower();formats[name]=m[2].lower();trace.append(f'week_format|{name}|{formats[name]}');steps+=1;i+=1
            assert texts[i].lower()=='run';i+=1
        elif norm.startswith('data '):
            name,table,datecols=data(texts,i,next(payloads));tables[name]=table
            for row in range(len(table['rows'])):trace.extend([f'week_input|{name}|{row+1}|1',f'week_output|{name}|{row+1}'])
            trace.append(f'week_input|{name}|{len(table["rows"])+1}|0');producers+=1;inputs+=len(table['rows']);steps+=1;i+=5
        elif norm.startswith('proc report '):
            name=re.fullmatch(r'proc\s+report\s+data\s*=\s*('+NAME+r')\s+nowd',text,re.I)[1].lower();i+=1
            cols=columns(texts[i]);defs={};i+=1
            while texts[i].lower().startswith('define '):alias,spec=definition(texts[i]);defs[alias]=spec;i+=1
            if texts[i].lower().startswith('title'):
                title=None if texts[i].lower()=='title' else re.fullmatch(r"title\s+'((?:[^']|'')*)'",texts[i],re.I)[1].replace("''","'");titles+=1;i+=1
                trace.append('week_title|reset' if title is None else 'week_title|set|'+title.encode().hex())
            assert texts[i].lower()=='run';i+=1;steps+=1;ordinal=len(reports)+1
            header=' '.join(json.dumps((c['span']+'/' if c['span'] else '')+(defs.get(c['alias'],{}).get('label') or c['alias'])) for c in cols)
            lines=[] if title is None else ['TITLE: '+title];lines.append(header)
            trace.extend([f'week_report|{name}|{ordinal}|{len(tables[name]["rows"])}','week_header|'+header.encode().hex()]);previous=None
            for index,row in enumerate(tables[name]['rows'],1):
                cells=[]
                for col in cols:
                    value=row[col['source']];spec=defs.get(col['alias'],{});fmt=spec.get('format')
                    if spec.get('order'):
                        token=json.dumps('' if value==previous else str(int(value)));previous=value
                    elif fmt=='weekdate':
                        if value is None:label='.'
                        else:
                            day=EPOCH+timedelta(days=int(value));label=f'{WEEKDAYS[day.weekday()]}, {FULLMONTHS[day.month-1]} {day.day}, {day.year:04}'
                        token=json.dumps(label)
                    elif fmt and fmt.endswith('12'):
                        key=fmt[:-2];fn=formats[key];label=callback(value,functions[fn]);token=json.dumps(label);calls+=1
                        trace.append(f'week_callback|{fn}|{"." if value is None else int(value)}|'+label.encode().hex())
                    elif fmt=='10':token=json.dumps('.' if value is None else str(int(value)))
                    elif tables[name]['schema'][col['source']]['type']=='character':token=json.dumps(value.rstrip(' '))
                    else:token='.' if value is None else str(int(value))
                    cells.append(token)
                line=' '.join(cells);lines.append(line);trace.append(f'week_report_row|{ordinal}|{index}|'+line.encode().hex())
            key=f'report_{ordinal:02}.txt';reports[key]='\n'.join(lines)+'\n';trace.append('week_artifact|'+key+'|'+str(len(reports[key])))
        elif norm=='title' or norm.startswith('title '):
            title=None if norm=='title' else re.fullmatch(r"title\s+'((?:[^']|'')*)'",text,re.I)[1].replace("''","'");titles+=1;steps+=1;i+=1
            trace.append('week_title|reset' if title is None else 'week_title|set|'+title.encode().hex())
        else:raise ValueError('unconsumed independent callback source')
    result={'datasets':deepcopy(tables),'log':[]}
    if reports:result['reports']=reports
    accounting={'language_statements':len(statements),'opaque_payloads':producers,'steps':steps,'input_records':inputs,'input_attempts':inputs+producers,'functions':len(functions),'formats':len(formats),'callback_calls':calls,'title_sets':titles,'reports':len(reports),'statement_lines':[s['line'] for s in statements]}
    return result,accounting,trace
