"""Separate bounded numeric GROUPFORMAT and detail REPORT source family."""
from copy import deepcopy
from datetime import timedelta
import json
import re

from sas_semantics import SAS_EPOCH
from . import format_core as core
from . import format_report as reports
from .character_input import ordinary,SOURCE_NAME
from .date_foundations import SAS_DATE_MONTH_NAMES
from .date_program import _parse_data,_literal
from .formatted_program import _blocks
from .mixed_reports import parse_title,validate_step as validate_title,execute_title

PROFILE='numeric-groupformat-v1'
REPORT_CONTRACT='ascii-groupformat-report-v1'
KINDS=frozenset(('group_data','numeric_value','formatted_groups','group_report'))
ROUTES={'groupformat-input':'DS-086','numeric-value':'DS-084','formatted-groups':'DS-085','group-detail-report':'ST-027','logical-title':'ST-020'}
MINIMUM=-2147483647
MAXIMUM=2147483647


def _name(name):return ordinary(name) and not name[-1].isdigit() and (name=='salgrp' or name.startswith('usr_'))


def validate_value(step,args):
    if (set(args)!={'profile','ranges','source_lines'} or not _name(step['name'])
            or type(args['ranges']) is not list or not 1<=len(args['ranges'])<=32):
        raise ValueError('numeric VALUE requires a bounded local definition')
    previous=MINIMUM-1
    for item in args['ranges']:
        if (type(item) is not dict or set(item)!={'lower','upper','text'} or type(item.get('lower')) is not int
                or type(item.get('upper')) is not int or not MINIMUM<=item['lower']<=item['upper']<=MAXIMUM
                or item['lower']!=previous+1):raise ValueError('numeric VALUE requires ordered contiguous integer ranges')
        label=core.text(item['text'],128)
        if label!=label.strip(' ') or '%' in label:raise ValueError('numeric VALUE requires edge-blank-free nonmacro labels')
        previous=item['upper']
    if previous!=MAXIMUM:raise ValueError('numeric VALUE requires complete qualified integer coverage')
    core.source_lines(args['source_lines'],step,3)
    return deepcopy(args)


def value_field(value,definition):
    if value is None:return '.'
    for item in definition['ranges']:
        if item['lower']<=value<=item['upper']:return item['text']
    raise ValueError('numeric VALUE dispatch outside validated range')


def validate_groups(step,args,tables,producers,formats):
    if (set(args)!={'profile','source','key','format','source_lines'} or not ordinary(args.get('source'))
            or args['source'] not in producers or step['name'] in tables or not ordinary(args.get('key'))
            or type(args.get('format')) is not str or args['format'] not in formats):
        raise ValueError('GROUPFORMAT requires a fresh output,prior genuine producer and prior format')
    table=tables[args['source']];key=args['key']
    if (key not in table['schema'] or table['schema'][key]['type']!='number'
            or key in table['date_columns'] or len(table['rows'])>500):
        raise ValueError('GROUPFORMAT requires a non-date numeric key and at most500 source rows')
    previous=None
    for row in table['rows']:
        value=row[key]
        if value is None or previous is not None and value<previous:raise ValueError('GROUPFORMAT requires nonmissing raw-key ascending order')
        previous=value
    core.source_lines(args['source_lines'],step,7)
    return deepcopy(args)


def validate_program(plan,catalog=None):
    if not core.program(plan,catalog,KINDS,PROFILE,ROUTES):return None
    tables={};formats={};producers=set();contexts=[];counts={k:0 for k in KINDS};titles=0
    for step in plan['steps']:
        if type(step) is not dict or type(step.get('kind')) is not str:raise ValueError('GROUPFORMAT Step kind required')
        kind=step['kind']
        if kind=='report_title':context=validate_title(step);titles+=1
        else:
            args=core.step_args(step,KINDS,PROFILE,input_arg='source' if kind=='formatted_groups' else None);counts[kind]+=1
            if kind=='group_data':
                if step['name'] in tables:raise ValueError('GROUPFORMAT requires fresh producer names')
                context=core.date_data(step,args);tables[step['name']]=context;producers.add(step['name'])
            elif kind=='numeric_value':
                if step['name'] in formats:raise ValueError('numeric VALUE cannot replace a local definition')
                context=validate_value(step,args);formats[step['name']]=context
            elif kind=='formatted_groups':
                context=validate_groups(step,args,tables,producers,formats)
                # Conservative forwarding validates every source value, without
                # executing formatted grouping or materializing its output.
                tables[step['name']]=deepcopy(tables[context['source']])
                tables[step['name']]['group_format_key']=context['key']
            else:context=reports.validate_report(step,args,tables,formats);titles+=len(args['title_change'])
        contexts.append(context)
    if (not 1<=counts['group_data']<=8 or not 1<=counts['numeric_value']<=8
            or counts['formatted_groups']!=1 or counts['group_report']>2 or titles>32):
        raise ValueError('GROUPFORMAT composition bounds exceeded')
    return contexts


def execute_groups(table,args,definition,*,trace=None,name):
    rows=table['rows'];labels=[value_field(row[args['key']],definition) for row in rows];result=[]
    def add(value):
        if trace is not None:trace.append(value)
    add(f'groupformat_begin|{name}|{args["source"]}|{args["key"]}|{args["format"]}')
    for index,row in enumerate(rows):
        first=index==0 or labels[index]!=labels[index-1];last=index==len(rows)-1 or labels[index]!=labels[index+1]
        add(f'groupformat_row|{index+1}|{int(first)}|{int(last)}|'+labels[index].encode('ascii').hex())
        if first:result.append(deepcopy(row));add(f'groupformat_output|first|{index+1}')
        if last:result.append(deepcopy(row));add(f'groupformat_output|last|{index+1}')
    add(f'groupformat_end|{name}|{len(result)}')
    return {'schema':deepcopy(table['schema']),'rows':result}


def report_cell(value,spec,fmt,formats):
    if fmt=='date9':
        if value is None:text='.'
        else:
            day=SAS_EPOCH+timedelta(days=int(value));text=f'{day.day:02}{SAS_DATE_MONTH_NAMES[day.month-1][:3].upper()}{day.year:04}'
        return json.dumps(text)
    if fmt=='dollar12':return json.dumps('.' if value is None else '$'+format(int(value),','))
    if fmt is not None:return json.dumps(value_field(value,formats[fmt]))
    if spec['type']=='character':return json.dumps(value.rstrip(' '))
    return '.' if value is None else str(int(value))


def run_program(plan,catalog=None,*,trace=None):
    contexts=validate_program(plan,catalog)
    if contexts is None:raise ValueError('GROUPFORMAT executor requires its explicit family')
    tables={};formats={};artifacts={};title=None
    def add(value):
        if trace is not None:trace.append(value)
    for step,context in zip(plan['steps'],contexts,strict=True):
        kind=step['kind'];name=step['name']
        if kind=='group_data':
            tables[name]={k:deepcopy(context[k]) for k in ('schema','rows')}
            for index in range(len(context['rows'])):add(f'group_input|{name}|{index+1}|1');add(f'group_output|{name}|{index+1}')
            add(f'group_input|{name}|{len(context["rows"])+1}|0')
        elif kind=='numeric_value':formats[name]=context;add(f'numeric_value|{name}|{len(context["ranges"])}')
        elif kind=='formatted_groups':tables[name]=execute_groups(tables[context['source']],context,formats[context['format']],trace=trace,name=name)
        elif kind=='report_title':
            title=execute_title(step);add('group_title|reset' if title is None else 'group_title|set|'+title.encode('ascii').hex())
        else:
            if context['title_change']:
                title=context['title_change'][0];add('group_title|reset' if title is None else 'group_title|set|'+title.encode('ascii').hex())
            table=tables[name];ordinal=len(artifacts)+1
            lines=reports.render(table,context,title,lambda value,spec,fmt:report_cell(value,spec,fmt,formats))
            add(f'group_report|{name}|{ordinal}|{len(table["rows"])}');add('group_header|'+lines[int(title is not None)].encode('ascii').hex())
            for index,line in enumerate(lines[1+int(title is not None):],1):add(f'group_report_row|{ordinal}|{index}|'+line.encode('ascii').hex())
            key=f'report_{ordinal:02}.txt';artifacts[key]='\n'.join(lines)+'\n';reports.validate_reports(artifacts);add('group_artifact|'+key+'|'+str(len(artifacts[key])))
    result={'datasets':deepcopy(tables),'log':[]}
    if artifacts:result['reports']=artifacts
    return result


def parse_value(block):
    from .plan import Step,Operation
    if len(block)!=3 or block[0].text.lower()!='proc format' or block[-1].text.lower()!='run':raise ValueError('numeric VALUE requires one definition and RUN')
    head=re.fullmatch(r'value\s+('+SOURCE_NAME+r')\s+(.+)',block[1].text,re.I|re.S|re.ASCII)
    if head is None:raise ValueError('numeric VALUE declaration differs')
    pattern=re.compile(r"\s*(low|[+-]?[0-9]{1,10})\s*-\s*(<)?\s*(high|[+-]?[0-9]{1,10})\s*=\s*('(?:[^']|'')*'|\"(?:[^\"]|\"\")*\")(?=\s|$)",re.I|re.S|re.ASCII)
    rest=head[2];ranges=[]
    while rest.strip():
        item=pattern.match(rest)
        if item is None:raise ValueError('numeric VALUE requires integer ranges and literal outputs')
        if item[2] is not None and item[3].lower()=='high':
            raise ValueError('numeric VALUE permits exclusion only on a numeric upper endpoint')
        lower=MINIMUM if item[1].lower()=='low' else int(item[1]);upper=MAXIMUM if item[3].lower()=='high' else int(item[3])
        ranges.append({'lower':lower,'upper':upper-int(item[2] is not None),'text':_literal(item[4])});rest=rest[item.end():]
    return Step('numeric_value',head[1].lower(),block[0].line,operations=[Operation('numeric_value',block[0].line,{'profile':PROFILE,'ranges':ranges,'source_lines':[s.line for s in block]})])


def parse_groups(block):
    from .plan import Step,Operation
    if len(block)!=7 or block[-1].text.lower()!='run':raise ValueError('GROUPFORMAT DATA requires SET,BY,FORMAT,two OUTPUT predicates and RUN')
    header=re.fullmatch(r'data\s+('+SOURCE_NAME+r')',block[0].text,re.I|re.ASCII)
    source=re.fullmatch(r'set\s+('+SOURCE_NAME+r')',block[1].text,re.I|re.ASCII)
    by=re.fullmatch(r'by\s+groupformat\s+('+SOURCE_NAME+r')',block[2].text,re.I|re.ASCII)
    binding=re.fullmatch(r'format\s+('+SOURCE_NAME+r')\s+('+SOURCE_NAME+r')\.',block[3].text,re.I|re.ASCII)
    if header is None or source is None or by is None or binding is None or by[1].lower()!=binding[1].lower():raise ValueError('GROUPFORMAT declaration/binding differs')
    key=by[1].lower()
    for statement,flag in zip(block[4:6],('first','last'),strict=True):
        if re.fullmatch(r'if\s+'+flag+r'\.'+re.escape(key)+r'\s+then\s+output',statement.text,re.I|re.ASCII) is None:raise ValueError('GROUPFORMAT requires separate FIRST then LAST OUTPUT predicates')
    args={'profile':PROFILE,'source':source[1].lower(),'key':key,'format':binding[2].lower(),'source_lines':[s.line for s in block]}
    return Step('formatted_groups',header[1].lower(),block[0].line,inputs=[source[1].lower()],operations=[Operation('formatted_groups',block[0].line,args)])


def source_steps(source,statements):
    from .parser import Kind
    blocks=list(_blocks(statements));selected=any(re.match(r'^by\s+groupformat\s',s.text,re.I|re.ASCII) for _,_,block in blocks for s in block)
    if not selected:return [],[],{},False
    steps=[];failures=[];routes={}
    for start,end,block in blocks:
        text=block[0].text
        try:
            if not all(s.terminated and s.text.isascii() for s in block):raise ValueError('GROUPFORMAT requires complete ASCII statements')
            if re.match(r'^data\s',text,re.I|re.ASCII):
                if len(block)>1 and re.match(r'^set\s',block[1].text,re.I|re.ASCII):step=parse_groups(block);route='formatted-groups'
                else:step=core.retag(_parse_data(block,source),'group_data',PROFILE);route='groupformat-input'
            elif text.lower()=='proc format':step=parse_value(block);route='numeric-value'
            elif re.match(r'^proc\s+report\b',text,re.I|re.ASCII):step=reports.parse_report(block,'group_report',PROFILE);route='group-detail-report'
            elif len(block)==1 and re.match(r'^title(?:\s|$)',text,re.I|re.ASCII):step=parse_title(block[0]);route='logical-title'
            else:raise ValueError('GROUPFORMAT family contains an unqualified statement')
            steps.append(step)
            for index in range(start,end):
                if not any(token.kind is Kind.DATA for token in statements[index].tokens):routes[index]=(route,ROUTES[route])
        except (ValueError,TypeError,KeyError,RecursionError) as error:failures.append((block[0].line,text,str(error)))
    return steps,failures,routes,True


def compile_program(source,legacy):
    from .parser import split_statements,ParseError
    from .plan import Plan,Ticket
    try:statements=split_statements(source)
    except ParseError:return legacy(source)
    steps,failures,routes,selected=source_steps(source,statements)
    if not selected:return legacy(source)
    plan=Plan(steps=steps);plan.tickets.extend(Ticket(line,text,'groupformat',reason) for line,text,reason in failures)
    plan.matched.extend((construct,rule,statements[index].line) for index,(construct,rule) in routes.items())
    if not plan.tickets:
        try:validate_program(plan.to_dict())
        except (ValueError,TypeError,KeyError,RecursionError) as error:plan.tickets.append(Ticket(1,'groupformat program','groupformat',str(error)))
    return plan
