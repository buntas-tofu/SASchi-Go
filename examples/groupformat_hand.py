"""Independent whole-source formatted-group and detail-report oracle."""
from copy import deepcopy
from datetime import timedelta
import json
import re
from format_oracle_scan import scan
from picture_dates_hand import read_date,EPOCH,MONTHS

NAME=r'[A-Za-z_][A-Za-z0-9_]{0,31}'
MINIMUM=-2147483647;MAXIMUM=2147483647


def definition(text):
    match=re.fullmatch(r'value\s+('+NAME+r')\s+(.+)',text,re.I|re.S);assert match
    remain=match[2];entries=[]
    pattern=re.compile(r"\s*(low|[+-]?[0-9]+)\s*-\s*(<)?\s*(high|[+-]?[0-9]+)\s*=\s*('(?:[^']|'')*')",re.I)
    while remain.strip():
        item=pattern.match(remain);assert item
        lower=MINIMUM if item[1].lower()=='low' else int(item[1]);upper=MAXIMUM if item[3].lower()=='high' else int(item[3])
        entries.append((lower,upper-int(item[2] is not None),item[4][1:-1].replace("''","'")));remain=remain[item.end():]
    return match[1].lower(),entries


def formatted(value,entries):
    if value is None:return '.'
    for lo,hi,text in entries:
        if lo<=value<=hi:return text
    raise ValueError('independent value outside covered domain')


def data(texts,index,payload):
    name=re.fullmatch(r'data\s+('+NAME+r')',texts[index],re.I)[1].lower()
    assert texts[index+1].lower()=='infile cards' and texts[index+3].lower()=='cards' and texts[index+4].lower()=='run'
    remain=re.sub(r'^input\s+','',texts[index+2],flags=re.I);schema={};reads=[];datecols=[]
    pattern=re.compile(r'\s*('+NAME+r')(?:\s*:\s*(?:\$([0-9]+)\.|(date9)\.))?(?=\s|$)',re.I)
    while remain.strip():
        item=pattern.match(remain);assert item
        col=item[1].lower();kind='character' if item[2] else 'date' if item[3] else 'number';width=int(item[2]) if item[2] else 8
        schema[col]={'type':'character' if kind=='character' else 'number','length':width};reads.append((col,kind,width));remain=remain[item.end():]
        if kind=='date':datecols.append(col)
    rows=[]
    for record in payload['records']:
        cells=record.split();assert len(cells)==len(reads);row={}
        for (col,kind,width),cell in zip(reads,cells,strict=True):
            if kind=='character':value=cell.ljust(width)
            elif kind=='date':value=read_date(cell);value=None if value is None else float(value)
            else:value=None if cell=='.' else float(int(cell))
            row[col]=value
        rows.append(row)
    return name,{'schema':schema,'rows':rows},datecols


def report_column(text):
    entries=[]
    for token in re.sub(r'^columns?\s+','',text,flags=re.I).split():
        pair=token.lower().split('=');assert len(pair) in (1,2)
        entries.append({'source':pair[0],'alias':pair[-1]})
    return entries


def report_definition(text):
    match=re.fullmatch(r'define\s+('+NAME+r')\s*/\s*(.*)',text,re.I|re.S);assert match
    rest=match[2];label=None;format_name=None;display=False
    tokens=re.findall(r"'(?:[^']|'')*'|[^\s]+",rest)
    for token in tokens:
        if token.lower()=='display':display=True
        elif token.lower().startswith('format='):format_name=token[7:-1].lower()
        elif token.startswith("'"):label=token[1:-1].replace("''","'")
        else:raise ValueError('hand REPORT definition option')
    return match[1].lower(),{'display':display,'format':format_name,'label':label}


def token(value,spec,fmt,formats):
    if fmt=='date9':
        if value is None:text='.'
        else:
            day=EPOCH+timedelta(days=value);text=f'{day.day:02}{MONTHS[day.month-1]}{day.year:04}'
        return json.dumps(text)
    if fmt=='dollar12':return json.dumps('.' if value is None else '$'+format(int(value),','))
    if fmt:return json.dumps(formatted(value,formats[fmt]))
    if spec['type']=='character':return json.dumps(value.rstrip(' '))
    return '.' if value is None else str(int(value))


def build(source):
    statements,events=scan(source);texts=[s['text'] for s in statements];payloads=iter(e for e in events if e['kind']=='opaque_data')
    tables={};formats={};reports={};trace=[];title=None;i=0;steps=0;inputs=0;producers=0;titles=0;groups=0;outputs=0
    while i<len(texts):
        text=texts[i];norm=' '.join(text.lower().split())
        if norm=='proc format':
            name,entries=definition(texts[i+1]);assert texts[i+2].lower()=='run';formats[name]=entries
            trace.append(f'numeric_value|{name}|{len(entries)}');i+=3
        elif norm.startswith('data ') and texts[i+1].lower()=='infile cards':
            name,table,datecols=data(texts,i,next(payloads));tables[name]=table
            for index in range(len(table['rows'])):trace.extend([f'group_input|{name}|{index+1}|1',f'group_output|{name}|{index+1}'])
            trace.append(f'group_input|{name}|{len(table["rows"])+1}|0');inputs+=len(table['rows']);producers+=1;i+=5
        elif norm.startswith('data '):
            name=re.fullmatch(r'data\s+('+NAME+r')',text,re.I)[1].lower();previous=re.fullmatch(r'set\s+('+NAME+r')',texts[i+1],re.I)[1].lower()
            key=re.fullmatch(r'by\s+groupformat\s+('+NAME+r')',texts[i+2],re.I)[1].lower()
            bind=re.fullmatch(r'format\s+('+NAME+r')\s+('+NAME+r')\.',texts[i+3],re.I);assert bind[1].lower()==key;fmt=bind[2].lower()
            assert texts[i+4].lower()==f'if first.{key} then output' and texts[i+5].lower()==f'if last.{key} then output' and texts[i+6].lower()=='run'
            original=tables[previous];rows=original['rows'];labels=[formatted(row[key],formats[fmt]) for row in rows];result=[]
            trace.append(f'groupformat_begin|{name}|{previous}|{key}|{fmt}')
            for index,row in enumerate(rows):
                first=index==0 or labels[index]!=labels[index-1];last=index==len(rows)-1 or labels[index]!=labels[index+1]
                trace.append(f'groupformat_row|{index+1}|{int(first)}|{int(last)}|'+labels[index].encode().hex())
                if first:result.append(deepcopy(row));trace.append(f'groupformat_output|first|{index+1}')
                if last:result.append(deepcopy(row));trace.append(f'groupformat_output|last|{index+1}')
            trace.append(f'groupformat_end|{name}|{len(result)}');tables[name]={'schema':deepcopy(original['schema']),'rows':result};groups+=1;outputs+=len(result);i+=7
        elif norm.startswith('proc report '):
            name=re.fullmatch(r'proc\s+report\s+data\s*=\s*('+NAME+r')\s+nowd',text,re.I)[1].lower();i+=1
            columns=report_column(texts[i]);definitions={};i+=1
            while texts[i].lower().startswith('define '):
                alias,spec=report_definition(texts[i]);definitions[alias]=spec;i+=1
            if texts[i].lower().startswith('title'):
                title=None if texts[i].lower()=='title' else re.fullmatch(r"title\s+'((?:[^']|'')*)'",texts[i],re.I)[1].replace("''","'");titles+=1
                trace.append('group_title|reset' if title is None else 'group_title|set|'+title.encode().hex());i+=1
            assert texts[i].lower()=='run';i+=1
            lines=[] if title is None else ['TITLE: '+title]
            lines.append(' '.join(json.dumps(definitions.get(c['alias'],{}).get('label') or c['alias']) for c in columns))
            ordinal=len(reports)+1;trace.append(f'group_report|{name}|{ordinal}|{len(tables[name]["rows"])}')
            trace.append('group_header|'+lines[-1].encode().hex())
            for index,row in enumerate(tables[name]['rows'],1):
                line=' '.join(token(row[c['source']],tables[name]['schema'][c['source']],definitions.get(c['alias'],{}).get('format'),formats) for c in columns)
                lines.append(line);trace.append(f'group_report_row|{ordinal}|{index}|'+line.encode().hex())
            key=f'report_{ordinal:02}.txt';reports[key]='\n'.join(lines)+'\n';trace.append('group_artifact|'+key+'|'+str(len(reports[key])))
        elif norm=='title' or norm.startswith('title '):
            title=None if norm=='title' else re.fullmatch(r"title\s+'((?:[^']|'')*)'",text,re.I)[1].replace("''","'");titles+=1
            trace.append('group_title|reset' if title is None else 'group_title|set|'+title.encode().hex());i+=1
        else:raise ValueError('unconsumed hand source: '+text)
        steps+=1
    result={'datasets':tables,'log':[]}
    if reports:result['reports']=reports
    accounting={'language_statements':len(statements),'opaque_payloads':producers,'steps':steps,'input_records':inputs,'input_attempts':inputs+producers,
                'group_steps':groups,'explicit_outputs':outputs,'title_sets':titles,'reports':len(reports),'statement_lines':[s['line'] for s in statements]}
    return result,accounting,trace
