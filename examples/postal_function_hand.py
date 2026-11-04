"""Independent whole-source country dispatch oracle; postal values stay external."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import re
from format_oracle_scan import scan

NAME=r'[A-Za-z_][A-Za-z0-9_]{0,31}'


def character_format(text):
    m=re.fullmatch(r'value\s+\$('+NAME+r')\s+(.+)',text,re.I|re.S);assert m
    remain=m[2];pending=[];ranges=[]
    while remain.strip():
        part=re.match(r"\s*'([0-9]{4})'\s*(?:-\s*'([0-9]{4})')?\s*([,=])\s*",remain);assert part
        pending.append((part[1],part[2] or part[1]));remain=remain[part.end():]
        if part[3]=='=':
            label=re.match(r"'([A-Z]{1,3})'",remain);assert label
            for lo,hi in pending:ranges.append((lo,hi,label[1]))
            pending=[];remain=remain[label.end():]
    assert not pending
    return m[1].lower(),ranges


def function(texts):
    m=re.fullmatch(r'function\s+('+NAME+r')\(\s*('+NAME+r')\s*\$\s*,\s*('+NAME+r')\s*\$\s*\)\s*\$\s*5',texts[0],re.I);assert m
    country,code=m[2],m[3]
    a=re.fullmatch(r"if\s+upcase\(\s*"+country+r"\s*\)\s*=\s*'AU'\s+then\s+("+NAME+r")\s*=\s*put\(\s*"+code+r"\s*,\s*\$("+NAME+r")\.\s*\)",texts[1],re.I);assert a
    assert re.fullmatch(r"else\s+if\s+upcase\(\s*"+country+r"\s*\)\s*=\s*'US'\s+then\s+"+a[1]+r"\s*=\s*zipstate\(\s*"+code+r"\s*\)",texts[2],re.I)
    assert re.fullmatch(r"else\s+"+a[1]+r"\s*=\s*' '",texts[3],re.I)
    assert re.fullmatch(r'return\s*\(\s*'+a[1]+r'\s*\)',texts[4],re.I) and texts[5].lower()=='endsub'
    return m[1].lower(),a[2].lower()


def call(country,code,ranges,reference):
    country=country.rstrip(' ').upper();code=code.rstrip(' ')
    if country=='US':
        if not re.fullmatch('[0-9]{5}',code) or code not in reference:raise ValueError('unqualified US ZIP identity')
        result=reference[code]
    elif country=='AU':
        if not re.fullmatch('[0-9]{4}',code):raise ValueError('qualified AU code requires four digits')
        result=None
        for lo,hi,label in ranges:
            if lo<=code<=hi:result=label;break
        if result is None:raise ValueError('uncovered AU code')
    else:result=''
    return result.ljust(5)


def build(source,reference_path):
    reference=json.loads(Path(reference_path).read_text());statements,events=scan(source);texts=[s['text'] for s in statements];payloads=iter(e for e in events if e['kind']=='opaque_data')
    formats={};functions={};tables={};reports={};trace=[];title=None;library=None;active=None;i=0;steps=0;inputs=0;producers=0;calls=0;titles=0;sorts=0;bygroups=0
    while i<len(texts):
        text=texts[i];norm=' '.join(text.lower().split())
        if norm=='proc format':
            name,ranges=character_format(texts[i+1]);assert texts[i+2].lower()=='run';formats[name]=ranges;trace.append(f'postal_format|{name}|{len(ranges)}');steps+=1;i+=3
        elif norm.startswith('proc fcmp '):
            head=re.fullmatch(r'proc\s+fcmp\s+outlib\s*=\s*(work\.functions)\.('+NAME+r')',text,re.I);assert head
            fn,fmt=function(texts[i+1:i+7]);assert fmt in formats and texts[i+7].lower()=='quit';functions[fn]=fmt;library=head[1].lower();steps+=1;i+=8
            trace.extend([f'postal_function|{fn}|{fmt}',f'postal_library|{library}|{head[2].lower()}'])
        elif norm.startswith('options '):
            m=re.fullmatch(r'options\s+cmplib\s*=\s*(work\.functions)',text,re.I);assert m and m[1].lower()==library;active=library;trace.append('postal_cmplib|'+active);steps+=1;i+=1
        elif norm.startswith('data '):
            name=re.fullmatch(r'data\s+('+NAME+r')',text,re.I)[1].lower();assert re.fullmatch(r"infile\s+cards\s+dlm\s*=\s*','\s+dsd",texts[i+1],re.I)
            remain=re.sub(r'^input\s+','',texts[i+2],flags=re.I);schema={}
            while remain.strip():
                m=re.match(r'\s*('+NAME+r')\s*:\s*\$\s*([0-9]+)\.',remain,re.I);assert m
                schema[m[1].lower()]={'type':'character','length':int(m[2])};remain=remain[m.end():]
            assert texts[i+3].lower()=='cards' and texts[i+4].lower()=='run';rows=[]
            for index,record in enumerate(next(payloads)['records'],1):
                fields=next(csv.reader([record],strict=True));assert len(fields)==len(schema);row={}
                for (col,spec),value in zip(schema.items(),fields,strict=True):assert value and len(value)<=spec['length'];row[col]=value.ljust(spec['length'])
                rows.append(row);trace.extend([f'postal_input|{name}|{index}|1',f'postal_output|{name}|{index}'])
            trace.append(f'postal_input|{name}|{len(rows)+1}|0');tables[name]={'schema':schema,'rows':rows};producers+=1;inputs+=len(rows);steps+=1;i+=5
        elif norm.startswith('proc sort '):
            name=re.fullmatch(r'proc\s+sort\s+data\s*=\s*('+NAME+r')',text,re.I)[1].lower();key=re.fullmatch(r'by\s+('+NAME+r')',texts[i+1],re.I)[1].lower();assert texts[i+2].lower()=='run'
            order=sorted(range(len(tables[name]['rows'])),key=lambda k:tables[name]['rows'][k][key]);tables[name]['rows']=[tables[name]['rows'][k] for k in order]
            trace.append(f'postal_sort|{name}|{key}|{len(order)}')
            trace.extend(f'postal_sort_row|{j+1}|{k+1}' for j,k in enumerate(order));sorts+=1;steps+=1;i+=3
        elif norm.startswith('proc report '):
            assert active==library;name=re.fullmatch(r'proc\s+report\s+data\s*=\s*('+NAME+r')\s+nowd',text,re.I)[1].lower();cols=re.sub(r'^columns?\s+','',texts[i+1],flags=re.I).lower().split();by=re.fullmatch(r'by\s+('+NAME+r')',texts[i+2],re.I)[1].lower()
            d=re.fullmatch(r"define\s+("+NAME+r")\s*/\s*computed\s+'((?:[^']|'')*)'",texts[i+3],re.I);assert d;computed=d[1].lower();label=d[2].replace("''","'")
            assert re.fullmatch(r'compute\s+'+computed+r'\s*/\s*char\s+length\s*=\s*5',texts[i+4],re.I)
            c=re.fullmatch(computed+r'\s*=\s*('+NAME+r')\(\s*('+NAME+r')\s*,\s*('+NAME+r')\s*\)',texts[i+5],re.I);assert c and texts[i+6].lower()=='endcomp';fn,ck,pc=(c[k].lower() for k in (1,2,3));i+=7
            if texts[i].lower().startswith('title'):
                title=None if texts[i].lower()=='title' else re.fullmatch(r"title\s+'((?:[^']|'')*)'",texts[i],re.I)[1].replace("''","'");titles+=1;i+=1
                trace.append('postal_title|reset' if title is None else 'postal_title|set|'+title.encode().hex())
            assert texts[i].lower()=='run';i+=1;steps+=1;ordinal=len(reports)+1
            header=' '.join(json.dumps(label if col==computed else col) for col in cols);lines=[] if title is None else ['TITLE: '+title];lines.append(header)
            trace.extend([f'postal_report|{name}|{ordinal}|{len(tables[name]["rows"])}','postal_header|'+header.encode().hex()]);previous=None
            for index,row in enumerate(tables[name]['rows'],1):
                if row[by]!=previous:
                    previous=row[by];line='BY '+by+'='+json.dumps(previous.rstrip(' '));lines.append(line);trace.append('postal_by|'+line.encode().hex());bygroups+=1
                value=call(row[ck],row[pc],formats[functions[fn]],reference);calls+=1
                trace.append(f'postal_callback|{fn}|'+row[ck].encode().hex()+'|'+row[pc].encode().hex()+'|'+value.encode().hex())
                line=' '.join(json.dumps((value if col==computed else row[col]).rstrip(' ')) for col in cols);lines.append(line);trace.append(f'postal_report_row|{ordinal}|{index}|'+line.encode().hex())
            key=f'report_{ordinal:02}.txt';reports[key]='\n'.join(lines)+'\n';trace.append('postal_artifact|'+key+'|'+str(len(reports[key])))
        elif norm=='title' or norm.startswith('title '):
            title=None if norm=='title' else re.fullmatch(r"title\s+'((?:[^']|'')*)'",text,re.I)[1].replace("''","'");titles+=1;steps+=1;i+=1;trace.append('postal_title|reset' if title is None else 'postal_title|set|'+title.encode().hex())
        else:raise ValueError('unconsumed independent postal source')
    result={'datasets':deepcopy(tables),'log':[]}
    if reports:result['reports']=reports
    accounting={'language_statements':len(statements),'opaque_payloads':producers,'steps':steps,'input_records':inputs,'input_attempts':inputs+producers,'formats':len(formats),'functions':len(functions),'callback_calls':calls,'sorts':sorts,'by_groups':bygroups,'title_sets':titles,'reports':len(reports),'statement_lines':[s['line'] for s in statements]}
    return result,accounting,trace
