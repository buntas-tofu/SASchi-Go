"""Independent source-reading hand oracle for canonical date-picture programs."""
from copy import deepcopy
from datetime import date,timedelta
import json
import re
from format_oracle_scan import scan

EPOCH=date(1960,1,1)
MONTHS=('JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC')
NAME=r'[A-Za-z_][A-Za-z0-9_]{0,31}'
BOUND=r"(?:low|high|'[0-9]{2}[A-Za-z]{3}[0-9]{4}'[dD])"


def read_date(token):
    if token=='.':return None
    match=re.fullmatch(r'([0-9]{2})([A-Za-z]{3})([0-9]{4})',token)
    if not match:raise ValueError('canonical hand DATE9 required')
    value=date(int(match[3]),MONTHS.index(match[2].upper())+1,int(match[1]))
    if not 1753<=value.year<=3999:raise ValueError('hand calendar bound')
    return (value-EPOCH).days


def quoted(text):
    if not text.startswith("'") or not text.endswith("'"):raise ValueError('hand single-quoted literal required')
    return text[1:-1].replace("''", "'")


def endpoint(text):
    return {'low':(date(1753,1,1)-EPOCH).days,'high':(date(3999,12,31)-EPOCH).days}.get(text.lower(),read_date(text[1:-2]) if text.lower() not in ('low','high') else None)


def definitions(text):
    head=re.fullmatch(r'picture\s+('+NAME+r')\s+(.+)',text,re.I|re.S)
    if not head:raise ValueError('hand PICTURE declaration')
    pattern=re.compile(r"\s*(other|("+BOUND+r")\s*-\s*(<)?\s*("+BOUND+r"))\s*=\s*('(?:[^']|'')*')\s*(\(\s*datatype\s*=\s*date\s*\))?",re.I|re.S)
    remaining=head[2];entries=[];other=None
    while remaining.strip():
        item=pattern.match(remaining)
        if not item:raise ValueError('hand PICTURE range')
        label=quoted(item[5]);directive=item[6] is not None
        if item[1].lower()=='other':
            if other is not None:raise ValueError('duplicate OTHER')
            other=(label,directive)
        else:entries.append((endpoint(item[2]),endpoint(item[4])-int(item[3] is not None),label,directive))
        remaining=remaining[item.end():]
    return head[1].lower(),(entries,other)


def display(value,definition):
    entries,other=definition;chosen=other
    if value is not None:
        for lo,hi,text,dt in entries:
            if lo<=value<=hi:chosen=(text,dt);break
    if chosen is None:return 'ERROR' if value is None else '.'
    text,dt=chosen
    if dt:
        if value is None:return 'ERROR'
        day=EPOCH+timedelta(days=value)
        # strftime is an independent host date renderer, under explicit C locale.
        mapping={'%0d':day.strftime('%d'),'%d':str(day.day),'%b':day.strftime('%b'),'%B':day.strftime('%B'),'%Y':day.strftime('%Y'),'%%':'%'}
        text=re.sub(r'%0d|%[dbBY%]',lambda m:mapping[m[0]],text)
        if '%' in text and '%%' not in chosen[0]:raise ValueError('hand unsupported directive')
    return text.rstrip(' ')


def build(source):
    import locale
    locale.setlocale(locale.LC_TIME,'C')
    statements,events=scan(source);payloads=iter(e for e in events if e['kind']=='opaque_data')
    tables={};formats={};reports={};title=None;trace=[];i=0;steps=0;input_count=0;title_count=0
    while i<len(statements):
        text=statements[i]['text'];normalized=' '.join(text.lower().split())
        if normalized=='proc format':
            assert statements[i+2]['text'].lower()=='run';name,definition=definitions(statements[i+1]['text']);formats[name]=definition
            trace.append('date_picture|'+name+'|'+str(len(definition[0]))+'|'+str(int(definition[1] is not None)))
            i+=3
        elif normalized.startswith('data '):
            name=re.fullmatch(r'data\s+('+NAME+r')',text,re.I)[1].lower()
            assert statements[i+1]['text'].lower()=='infile cards' and statements[i+3]['text'].lower()=='cards' and statements[i+4]['text'].lower()=='run'
            declaration=re.sub(r'^input\s+','',statements[i+2]['text'],flags=re.I)
            pattern=re.compile(r'\s*('+NAME+r')(?:\s*:\s*(?:\$([0-9]+)\.|(date9)\.))?(?=\s|$)',re.I)
            schema={};reads=[]
            while declaration.strip():
                item=pattern.match(declaration)
                if not item:raise ValueError('hand declaration')
                col=item[1].lower();kind='character' if item[2] else 'date' if item[3] else 'number';width=int(item[2]) if item[2] else 8
                schema[col]={'type':'character' if kind=='character' else 'number','length':width};reads.append((col,kind,width));declaration=declaration[item.end():]
            rows=[];payload=next(payloads)
            for index,record in enumerate(payload['records'],1):
                cells=record.split();assert len(cells)==len(reads);row={}
                for (col,kind,width),cell in zip(reads,cells,strict=True):
                    if kind=='date':value=read_date(cell);value=None if value is None else float(value)
                    elif kind=='character':value=cell.ljust(width)
                    else:value=None if cell=='.' else float(int(cell))
                    row[col]=value
                rows.append(row);trace.extend([f'picture_input|{name}|{index}|1',f'picture_output|{name}|{index}'])
            trace.append(f'picture_input|{name}|{len(rows)+1}|0');input_count+=len(rows)
            tables[name]={'schema':schema,'rows':rows};i+=5
        elif normalized.startswith('proc print '):
            header=re.fullmatch(r'proc\s+print\s+data\s*=\s*('+NAME+r')(?:\s*\(\s*obs\s*=\s*([0-9]+)\s*\))?',text,re.I)
            name=header[1].lower();limit=None if header[2] is None else int(header[2]);i+=1
            columns=re.fullmatch(r'var\s+(.+)',statements[i]['text'],re.I)[1].lower().split();i+=1
            binding=re.fullmatch(r'format\s+(.+)\s+('+NAME+r')\.',statements[i]['text'],re.I)
            bound=binding[1].lower().split();fmt=binding[2].lower();i+=1
            if statements[i]['text'].lower().startswith('title'):
                title=quoted(re.sub(r'^title\s+','',statements[i]['text'],flags=re.I));title_count+=1
                trace.append('picture_title|set|'+title.encode('ascii').hex());i+=1
            assert statements[i]['text'].lower()=='run';i+=1
            rows=tables[name]['rows'][:limit];ordinal=len(reports)+1;lines=[] if title is None else ['TITLE: '+title]
            lines.append('obs '+' '.join(columns));trace.append(f'picture_print|{name}|{ordinal}|{len(rows)}|'+','.join(columns))
            for index,row in enumerate(rows,1):
                cells=[]
                for col in columns:
                    value=row[col]
                    if col in bound:token=json.dumps(display(value,formats[fmt]))
                    elif schema_type(tables[name],col)=='character':token=json.dumps(value.rstrip(' '))
                    else:token='.' if value is None else str(int(value))
                    cells.append(token)
                line=str(index)+' '+' '.join(cells);lines.append(line);trace.append(f'picture_row|{ordinal}|{index}|'+line.encode('ascii').hex())
            key=f'print_{ordinal:02}.txt';reports[key]='\n'.join(lines)+'\n';trace.append('picture_artifact|'+key+'|'+str(len(reports[key])))
        elif normalized=='title' or normalized.startswith('title '):
            title=None if normalized=='title' else quoted(re.sub(r'^title\s+','',text,flags=re.I));title_count+=1
            trace.append('picture_title|reset' if title is None else 'picture_title|set|'+title.encode('ascii').hex());i+=1
        else:raise ValueError('unconsumed whole hand statement: '+normalized)
        steps+=1
    result={'datasets':deepcopy(tables),'log':[]}
    if reports:result['reports']=reports
    accounting={'language_statements':len(statements),'opaque_payloads':sum(e['kind']=='opaque_data' for e in events),'steps':steps,
                'input_records':input_count,'input_attempts':input_count+len(tables),'title_sets':title_count,'prints':len(reports),
                'statement_lines':[s['line'] for s in statements]}
    return result,accounting,trace


def schema_type(table,col):return table['schema'][col]['type']
