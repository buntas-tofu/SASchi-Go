"""Independent original numeric PICTURE/fixed-input/detail-report oracle."""
from copy import deepcopy
import json
import re
from format_oracle_scan import scan
from groupformat_hand import report_column,report_definition

NAME=r'[A-Za-z_][A-Za-z0-9_]{0,31}'
MINIMUM=-2147483647;MAXIMUM=2147483647


def valid_template(text,noedit):
    if not text.isascii() or not 1<=len(text)<=40 or any(not 32<=ord(c)<=126 for c in text) or not text.strip() or '%' in text or '&' in text:raise ValueError('qualified numeric picture text required')
    if noedit:return
    if not any(c.isdigit() for c in text):return
    match=re.fullmatch(r'([0-9]{1,16})([A-Za-z ]*)',text)
    if match is None or not any(c!='0' for c in match[1]):raise ValueError('qualified digit selectors must start the picture')


def definition(text):
    head=re.fullmatch(r'picture\s+('+NAME+r')\s+(.+)',text,re.I|re.S);assert head
    pattern=re.compile(r"\s*(low|[+-]?[0-9]+)(?:\s*(<)?\s*-\s*(<)?\s*(high|[+-]?[0-9]+))?\s*=\s*('(?:[^']|'')*')\s*(\(\s*noedit\s*\))?",re.I|re.S)
    remain=head[2];ranges=[];previous=MINIMUM-1
    while remain.strip():
        item=pattern.match(remain)
        if not item:raise ValueError('numeric picture range')
        if item[1].lower()=='low' and (item[2] or item[4] is None) or item[4] and item[4].lower()=='high' and item[3]:raise ValueError('closed symbolic bounds only')
        lo=MINIMUM if item[1].lower()=='low' else int(item[1]);hi=lo if item[4] is None else MAXIMUM if item[4].lower()=='high' else int(item[4])
        lo+=int(item[2] is not None);hi-=int(item[3] is not None)
        label=item[5][1:-1].replace("''","'");noedit=item[6] is not None;valid_template(label,noedit)
        if not MINIMUM<=lo<=hi<=MAXIMUM or lo!=previous+1:raise ValueError('complete contiguous numeric ranges required')
        ranges.append((lo,hi,label,noedit));previous=hi;remain=remain[item.end():]
    if previous!=MAXIMUM:raise ValueError('numeric picture complete tail required')
    return head[1].lower(),ranges


def edited(value,label,noedit):
    if noedit or not any(c.isdigit() for c in label):return label
    match=re.fullmatch(r'([0-9]+)(.*)',label);selectors,suffix=match[1],match[2]
    digits=str(abs(int(value))).zfill(len(selectors))[-len(selectors):];kept=False;result=[]
    for selector,digit in zip(selectors,digits,strict=True):
        if kept or selector!='0' or digit!='0':kept=True;result.append(digit)
        else:result.append(' ')
    return ''.join(result).lstrip(' ')+suffix


def display(value,ranges):
    for lo,hi,label,noedit in ranges:
        if lo<=value<=hi:return edited(value,label,noedit)
    raise ValueError('uncovered numeric value')


def build(source):
    bom=source.startswith('\ufeff');body=source[1:] if bom else source
    if not body.isascii():raise ValueError('one prefix BOM and ASCII remainder only')
    statements,events=scan(body);texts=[s['text'] for s in statements];payloads=iter(e for e in events if e['kind']=='opaque_data')
    tables={};formats={};reports={};trace=[f'numeric_picture_prefix|{"utf8-bom" if bom else "none"}|{3 if bom else 0}'];title=None
    i=0;steps=0;inputs=0;producers=0;titles=0
    while i<len(texts):
        text=texts[i];norm=' '.join(text.lower().split())
        if norm.startswith('data '):
            name=re.fullmatch(r'data\s+('+NAME+r')',text,re.I)[1].lower()
            assert texts[i+1].lower()=='infile datalines' and texts[i+3].lower()=='datalines' and texts[i+4].lower()=='run'
            declaration=re.fullmatch(r'input\s+('+NAME+r')\s+('+NAME+r')\s+\$([1-8])\.',texts[i+2],re.I)
            assert declaration;number,character=declaration[1].lower(),declaration[2].lower();width=int(declaration[3])
            schema={number:{'type':'number','length':8},character:{'type':'character','length':width}};rows=[]
            payload=next(payloads)
            for index,record in enumerate(payload['records'],1):
                item=re.fullmatch(r'([+-]?[0-9]{1,10}) ([A-Za-z]{'+str(width)+r'})( *)',record)
                if not item or len(record)>80 or not MINIMUM<=int(item[1])<=MAXIMUM:raise ValueError('fixed numeric/character record required')
                rows.append({number:float(int(item[1])),character:item[2]});trace.extend([f'number_input|{name}|{index}|1',f'number_output|{name}|{index}'])
            trace.append(f'number_input|{name}|{len(rows)+1}|0');tables[name]={'schema':schema,'rows':rows};inputs+=len(rows);producers+=1;steps+=1;i+=5
        elif norm=='proc format':
            i+=1
            while texts[i].lower().startswith('picture '):
                name,ranges=definition(texts[i]);formats[name]=ranges;trace.append(f'number_picture|{name}|{len(ranges)}');steps+=1;i+=1
            assert texts[i].lower()=='run';i+=1
        elif norm.startswith('proc report '):
            name=re.fullmatch(r'proc\s+report\s+data\s*=\s*('+NAME+r')\s+nowd',text,re.I)[1].lower();i+=1
            columns=report_column(texts[i]);definitions={};i+=1
            while texts[i].lower().startswith('define '):alias,spec=report_definition(texts[i]);definitions[alias]=spec;i+=1
            if texts[i].lower().startswith('title'):
                title=None if texts[i].lower()=='title' else re.fullmatch(r"title\s+'((?:[^']|'')*)'",texts[i],re.I)[1].replace("''","'");titles+=1
                trace.append('number_title|reset' if title is None else 'number_title|set|'+title.encode().hex());i+=1
            assert texts[i].lower()=='run';i+=1
            lines=[] if title is None else ['TITLE: '+title]
            header=' '.join(json.dumps(definitions.get(c['alias'],{}).get('label') or c['alias']) for c in columns);lines.append(header)
            ordinal=len(reports)+1;trace.extend([f'number_report|{name}|{ordinal}|{len(tables[name]["rows"])}','number_header|'+header.encode().hex()])
            for index,row in enumerate(tables[name]['rows'],1):
                cells=[]
                for col in columns:
                    value=row[col['source']];fmt=definitions.get(col['alias'],{}).get('format')
                    if fmt=='comma12':token=json.dumps(format(int(value),','))
                    elif fmt:token=json.dumps(display(value,formats[fmt]))
                    elif tables[name]['schema'][col['source']]['type']=='character':token=json.dumps(value.rstrip(' '))
                    else:token=str(int(value))
                    cells.append(token)
                line=' '.join(cells);lines.append(line);trace.append(f'number_report_row|{ordinal}|{index}|'+line.encode().hex())
            key=f'report_{ordinal:02}.txt';reports[key]='\n'.join(lines)+'\n';trace.append('number_artifact|'+key+'|'+str(len(reports[key])));steps+=1
        elif norm=='title' or norm.startswith('title '):
            title=None if norm=='title' else re.fullmatch(r"title\s+'((?:[^']|'')*)'",text,re.I)[1].replace("''","'");titles+=1;steps+=1;i+=1
            trace.append('number_title|reset' if title is None else 'number_title|set|'+title.encode().hex())
        else:raise ValueError('unconsumed numeric picture source')
    result={'datasets':deepcopy(tables),'log':[]}
    if reports:result['reports']=reports
    accounting={'language_statements':len(statements),'opaque_payloads':producers,'steps':steps,'input_records':inputs,'input_attempts':inputs+producers,
                'picture_definitions':len(formats),'title_sets':titles,'reports':len(reports),'source_prefix_bytes':3 if bom else 0,'statement_lines':[s['line'] for s in statements]}
    return result,accounting,trace
