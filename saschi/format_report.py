"""Bounded detail REPORT scaffolding; each caller fixes its allowed formats."""
from copy import deepcopy
import json
import re

from . import format_core as core
from .character_input import SOURCE_NAME,ordinary
from .date_program import _literal
from .mixed_reports import parse_title,_title


def parse_columns(text):
    head=re.fullmatch(r'columns?\s+(.+)',text,re.I|re.S|re.ASCII)
    if head is None:raise ValueError('detail REPORT requires one COLUMN list')
    rest=head[1];columns=[]
    pattern=re.compile(r'\s*('+SOURCE_NAME+r')(?:\s*=\s*('+SOURCE_NAME+r'))?(?=\s|$)',re.ASCII)
    while rest.strip():
        item=pattern.match(rest)
        if item is None:raise ValueError('detail REPORT permits source names and simple aliases')
        columns.append({'source':item[1].lower(),'alias':(item[2] or item[1]).lower()});rest=rest[item.end():]
    return columns


def parse_definition(text):
    head=re.fullmatch(r'define\s+('+SOURCE_NAME+r')\s*/\s*(.+)',text,re.I|re.S|re.ASCII)
    if head is None:raise ValueError('detail REPORT requires DEFINE alias / options')
    rest=head[2];display=False;fmt=None;label=None
    pattern=re.compile(r"\s*(display\b|format\s*=\s*("+SOURCE_NAME+r")\.|('(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"))(?=\s|$)",re.I|re.S|re.ASCII)
    while rest.strip():
        item=pattern.match(rest)
        if item is None:raise ValueError('detail REPORT DEFINE permits DISPLAY,FORMAT and a literal label')
        if item[1].lower()=='display':
            if display:raise ValueError('duplicate REPORT DISPLAY')
            display=True
        elif item[2] is not None:
            if fmt is not None:raise ValueError('duplicate REPORT FORMAT')
            fmt=item[2].lower()
        else:
            if label is not None:raise ValueError('duplicate REPORT label')
            label=_literal(item[3])
        rest=rest[item.end():]
    return head[1].lower(),{'display':display,'format':fmt,'label':label}


def parse_report(block,kind,profile):
    from .plan import Step,Operation
    if len(block)<3 or block[-1].text.lower()!='run':raise ValueError('detail REPORT requires COLUMN,definitions and RUN')
    header=re.fullmatch(r'proc\s+report\s+data\s*=\s*('+SOURCE_NAME+r')\s+nowd',block[0].text,re.I|re.ASCII)
    if header is None:raise ValueError('detail REPORT requires DATA=name NOWD')
    columns=parse_columns(block[1].text);definitions={};position=2
    while position<len(block)-1 and re.match(r'^define\s',block[position].text,re.I|re.ASCII):
        alias,spec=parse_definition(block[position].text)
        if alias in definitions:raise ValueError('duplicate REPORT DEFINE alias')
        definitions[alias]=spec;position+=1
    changes=[]
    if position<len(block)-1:
        changes=[parse_title(block[position]).operations[0].args['text']];position+=1
    if position!=len(block)-1:raise ValueError('detail REPORT contains an unqualified statement')
    name=header[1].lower();args={'profile':profile,'columns':columns,'definitions':definitions,'title_change':changes,'source_lines':[s.line for s in block]}
    return Step(kind,name,block[0].line,inputs=[name],operations=[Operation(kind,block[0].line,args)])


def validate_report(step,args,tables,formats,*,numeric_builtins=None,date_builtins=('date9',)):
    numeric_builtins={'dollar12':(0,999999999)} if numeric_builtins is None else numeric_builtins
    if (set(args)!={'profile','columns','definitions','title_change','source_lines'} or step['name'] not in tables
            or type(args['columns']) is not list or not 1<=len(args['columns'])<=32
            or type(args['definitions']) is not dict or not 1<=len(args['definitions'])<=32
            or type(args['title_change']) is not list or len(args['title_change'])>1):
        raise ValueError('detail REPORT requires bounded columns,definitions and title change')
    table=tables[step['name']];aliases={}
    for item in args['columns']:
        if (type(item) is not dict or set(item)!={'source','alias'} or not ordinary(item.get('source'))
                or not ordinary(item.get('alias')) or item['alias'] in aliases or item['source'] not in table['schema']):
            raise ValueError('detail REPORT requires unique aliases and prior source columns')
        aliases[item['alias']]=item['source']
    for alias,spec in args['definitions'].items():
        if (not ordinary(alias) or alias not in aliases or type(spec) is not dict or set(spec)!={'display','format','label'}
                or type(spec.get('display')) is not bool or spec['format'] is not None and type(spec['format']) is not str):
            raise ValueError('detail REPORT DEFINE shape or alias differs')
        if spec['label'] is not None:_title(spec['label'])
        fmt=spec['format'];source=aliases[alias]
        if fmt is None:continue
        if fmt in date_builtins:
            if source not in table['date_columns']:raise ValueError('DATE9 report output requires a genuine date column')
        elif fmt in numeric_builtins or fmt in formats:
            if table['schema'][source]['type']!='number':raise ValueError('numeric REPORT format requires numeric storage')
            lower,upper=numeric_builtins.get(fmt,(-2147483647,2147483647))
            for row in table['rows']:
                value=row[source]
                if value is not None and (type(value) not in (int,float) or value!=int(value) or not lower<=value<=upper):
                    raise ValueError('REPORT format numeric domain or width exceeded')
        else:raise ValueError('detail REPORT references an unqualified or unavailable format')
    if 'group_format_key' in table:
        for alias,source in aliases.items():
            if source==table['group_format_key'] and args['definitions'].get(alias,{}).get('format') is None:
                raise ValueError('grouped REPORT key aliases require explicit FORMAT; inherited display is outside this profile')
    if not any(spec['display'] for spec in args['definitions'].values()):
        raise ValueError('detail REPORT requires an explicit DISPLAY; aggregation is not inferred')
    if args['title_change']:_title(args['title_change'][0])
    core.source_lines(args['source_lines'],step,3+len(args['definitions'])+len(args['title_change']))
    return deepcopy(args)


def validate_reports(reports):
    if (type(reports) is not dict or not 1<=len(reports)<=2
            or list(reports)!=[f'report_{i:02}.txt' for i in range(1,len(reports)+1)]):
        raise ValueError('detail reports require one or two ordered report artifacts')
    for text in reports.values():
        if (type(text) is not str or not text.isascii() or not text.endswith('\n') or len(text)>417056
                or any(c!='\n' and not 32<=ord(c)<=126 for c in text)):
            raise ValueError('detail REPORT ASCII/text limits exceeded')
        lines=text[:-1].split('\n');offset=int(lines[0].startswith('TITLE: '))
        if (offset and not 7<=len(lines[0])<=135 or not 1<=len(lines)-offset<=1001
                or not lines[offset] or len(lines[offset])>1055
                or any(not line or len(line)>415 for line in lines[offset+1:])):
            raise ValueError('detail REPORT header,row or observation limits exceeded')
    return reports


def render(table,args,title,cell):
    lines=[] if title is None else ['TITLE: '+title]
    header=' '.join(json.dumps(args['definitions'].get(c['alias'],{}).get('label') or c['alias']) for c in args['columns'])
    lines.append(header)
    for row in table['rows']:
        lines.append(' '.join(cell(row[c['source']],table['schema'][c['source']],args['definitions'].get(c['alias'],{}).get('format')) for c in args['columns']))
    return lines
