"""Separate source/portable composition for bounded date PICTURE and PRINT."""
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
import json
import re

from sas_semantics import SAS_EPOCH,SAS_CALENDAR_MIN_DAY as MIN_DAY,SAS_CALENDAR_MAX_DAY as MAX_DAY
from . import format_core as core
from .character_input import ordinary,SOURCE_NAME
from .date_foundations import SAS_DATE_MONTH_NAMES
from .date_program import _parse_data,_date,_literal,validate_reports
from .formatted_program import _blocks
from .mixed_reports import parse_title,validate_step as validate_title,execute_title

PROFILE='picture-date-fields-v1'
REPORT_CONTRACT='ascii-picture-date-v1'
KINDS=frozenset(('picture_data','date_picture','picture_print'))
ROUTES={'picture-date-input':'DS-083','date-picture':'DS-082','picture-date-print':'ST-026','logical-title':'ST-020'}


def _name(name):
    return ordinary(name) and not name[-1].isdigit() and (name in ('hirefmt','mrg') or name.startswith('usr_'))


def _render_shape(render):
    if (type(render) is not dict or set(render)!={'template','datatype'} or type(render.get('datatype')) is not bool):
        raise ValueError('date PICTURE render requires exact template and datatype flag')
    template=core.text(render['template'],40)
    if render['datatype']:
        cursor=0;maximum=0
        for item in re.finditer(r'%0d|%[dbBY%]',template,re.ASCII):
            literal=template[cursor:item.start()]
            if '%' in literal:raise ValueError('date PICTURE directive is outside the qualified vocabulary')
            maximum+=len(literal)+{'%0d':2,'%d':2,'%b':3,'%B':9,'%Y':4,'%%':1}[item[0]];cursor=item.end()
        if '%' in template[cursor:]:raise ValueError('unqualified date PICTURE directive')
        maximum+=len(template)-cursor
        if maximum>128:raise ValueError('date PICTURE maximal expansion exceeds128 bytes')
    elif any(c.isdigit() for c in template) or '%' in template:
        raise ValueError('literal date PICTURE alternatives cannot contain digit selectors or directives')
    return deepcopy(render)


def _definition(step,args):
    if (set(args)!={'profile','ranges','other','source_lines'} or not _name(step['name'])
            or type(args['ranges']) is not list or not 1<=len(args['ranges'])<=32):
        raise ValueError('date PICTURE requires a bounded local definition')
    previous=MIN_DAY-1
    for item in args['ranges']:
        if (type(item) is not dict or set(item)!={'lower','upper','render'}
                or type(item.get('lower')) is not int or type(item.get('upper')) is not int
                or not MIN_DAY<=item['lower']<=item['upper']<=MAX_DAY or item['lower']<=previous):
            raise ValueError('date PICTURE requires ordered nonoverlapping integral calendar ranges')
        if args['other'] is None and item['lower']!=previous+1:raise ValueError('date PICTURE gaps require OTHER')
        _render_shape(item['render']);previous=item['upper']
    if args['other'] is None:
        if previous!=MAX_DAY:raise ValueError('date PICTURE uncovered tail requires OTHER')
    else:_render_shape(args['other'])
    core.source_lines(args['source_lines'],step,3)
    return deepcopy(args)


def _print(step,args,tables,formats):
    if (set(args)!={'profile','columns','bound','format','obs','title_change','source_lines'}
            or step['name'] not in tables or type(args.get('format')) is not str or args['format'] not in formats
            or type(args.get('columns')) is not list or not 1<=len(args['columns'])<=32
            or any(not ordinary(c) for c in args['columns']) or len(set(args['columns']))!=len(args['columns'])
            or any(c not in tables[step['name']]['schema'] for c in args['columns']) or 'obs' in args['columns']
            or type(args.get('bound')) is not list or not 1<=len(args['bound'])<=32
            or any(not ordinary(c) for c in args['bound']) or len(set(args['bound']))!=len(args['bound'])
            or any(c not in args['columns'] or c not in tables[step['name']]['date_columns'] for c in args['bound'])
            or args['obs'] is not None and (type(args['obs']) is not int or not 1<=args['obs']<=1000)
            or type(args['title_change']) is not list or len(args['title_change'])>1):
        raise ValueError('date PICTURE PRINT requires prior VAR/date bindings and bounded OBS/title shape')
    if args['title_change']:
        from .mixed_reports import _title
        _title(args['title_change'][0])
    core.source_lines(args['source_lines'],step,5 if args['title_change'] else 4)
    return deepcopy(args)


def validate_program(plan,catalog=None):
    if not core.program(plan,catalog,KINDS,PROFILE,ROUTES):return None
    tables={};formats={};contexts=[];counts={k:0 for k in KINDS};titles=0
    for step in plan['steps']:
        if type(step) is not dict or type(step.get('kind')) is not str:raise ValueError('date PICTURE Step kind required')
        kind=step['kind']
        if kind=='report_title':context=validate_title(step);titles+=1
        else:
            args=core.step_args(step,KINDS,PROFILE);counts[kind]+=1
            if kind=='picture_data':
                if step['name'] in tables:raise ValueError('date PICTURE requires fresh DATA names')
                context=core.date_data(step,args);tables[step['name']]=context
            elif kind=='date_picture':
                if step['name'] in formats:raise ValueError('date PICTURE cannot replace a local definition')
                context=_definition(step,args);formats[step['name']]=context
            else:context=_print(step,args,tables,formats);titles+=len(args['title_change'])
        contexts.append(context)
    if (not 1<=counts['picture_data']<=8 or not 1<=counts['date_picture']<=8
            or counts['picture_print']>2 or titles>32):raise ValueError('date PICTURE composition bounds exceeded')
    return contexts


def field(value,definition):
    render=definition['other']
    if value is not None:
        for item in definition['ranges']:
            if item['lower']<=value<=item['upper']:render=item['render'];break
    if render is None:return 'ERROR' if value is None else '.'
    text=render['template']
    if render['datatype']:
        if value is None:return 'ERROR'
        day=SAS_EPOCH+timedelta(days=int(value))
        mapping={'%d':str(day.day),'%0d':str(day.day).zfill(2),'%b':SAS_DATE_MONTH_NAMES[day.month-1][:3],
                 '%B':SAS_DATE_MONTH_NAMES[day.month-1],'%Y':str(day.year).zfill(4),'%%':'%'}
        text=re.sub(r'%0d|%[dbBY%]',lambda item:mapping[item[0]],text)
    return text.rstrip(' ')


def run_program(plan,catalog=None,*,trace=None):
    contexts=validate_program(plan,catalog)
    if contexts is None:raise ValueError('date PICTURE executor requires its separate family')
    tables={};formats={};reports={};title=None
    def add(value):
        if trace is not None:trace.append(value)
    for step,context in zip(plan['steps'],contexts,strict=True):
        kind=step['kind'];name=step['name']
        if kind=='picture_data':
            tables[name]={key:deepcopy(context[key]) for key in ('schema','rows')}
            for index in range(len(context['rows'])):
                add(f'picture_input|{name}|{index+1}|1');add(f'picture_output|{name}|{index+1}')
            add(f'picture_input|{name}|{len(context["rows"])+1}|0')
        elif kind=='date_picture':
            formats[name]=context;add(f'date_picture|{name}|{len(context["ranges"])}|{int(context["other"] is not None)}')
        elif kind=='report_title':
            title=execute_title(step);add('picture_title|reset' if title is None else 'picture_title|set|'+title.encode('ascii').hex())
        else:
            if context['title_change']:
                title=context['title_change'][0];add('picture_title|reset' if title is None else 'picture_title|set|'+title.encode('ascii').hex())
            table=tables[name];rows=table['rows'][:context['obs']];columns=context['columns'];ordinal=len(reports)+1
            lines=[] if title is None else ['TITLE: '+title];lines.append('obs '+' '.join(columns))
            add(f'picture_print|{name}|{ordinal}|{len(rows)}|'+','.join(columns))
            for index,row in enumerate(rows,1):
                cells=[]
                for col in columns:
                    value=row[col]
                    if col in context['bound']:token=json.dumps(field(value,formats[context['format']]))
                    elif table['schema'][col]['type']=='character':token=json.dumps(value.rstrip(' '))
                    else:token='.' if value is None else str(int(value))
                    cells.append(token)
                line=str(index)+' '+' '.join(cells);lines.append(line);add(f'picture_row|{ordinal}|{index}|'+line.encode('ascii').hex())
            key=f'print_{ordinal:02}.txt';reports[key]='\n'.join(lines)+'\n';validate_reports(reports)
            add('picture_artifact|'+key+'|'+str(len(reports[key])))
    result={'datasets':deepcopy(tables),'log':[]}
    if reports:result['reports']=reports
    return result


def _parse_definition(block):
    from .plan import Step,Operation
    if len(block)!=3 or block[0].text.lower()!='proc format' or block[-1].text.lower()!='run':raise ValueError('date PICTURE requires one definition and RUN')
    head=re.fullmatch(r'picture\s+('+SOURCE_NAME+r')\s+(.+)',block[1].text,re.I|re.S|re.ASCII)
    if head is None:raise ValueError('date PICTURE header differs')
    bound=r'(?:low|high|\x27[0-9]{2}[A-Za-z]{3}[0-9]{4}\x27\s*[dD]|"[0-9]{2}[A-Za-z]{3}[0-9]{4}"\s*[dD])'
    pattern=re.compile(r"\s*(other|("+bound+r")\s*-\s*(<)?\s*("+bound+r"))\s*=\s*('(?:[^']|'')*')\s*(\(\s*datatype\s*=\s*date\s*\))?(?=\s|$)",re.I|re.S|re.ASCII)
    rest=head[2];ranges=[];other=None;seen_other=False
    while rest.strip():
        item=pattern.match(rest)
        if item is None:raise ValueError('date PICTURE range/template is outside the qualified grammar')
        if item[1].lower()!='other' and (item[2].lower()=='high' or item[4].lower()=='low'
                or item[3] is not None and item[4].lower()=='high'):
            raise ValueError('date PICTURE requires closed outer symbolic bounds in their proper roles')
        render={'template':_literal(item[5]),'datatype':item[6] is not None}
        if item[1].lower()=='other':
            if seen_other:raise ValueError('date PICTURE permits one final OTHER')
            other=render;seen_other=True
        else:
            if seen_other:raise ValueError('date PICTURE OTHER must be last')
            ranges.append({'lower':_date(item[2]),'upper':_date(item[4])-int(item[3] is not None),'render':render})
        rest=rest[item.end():]
    return Step('date_picture',head[1].lower(),block[0].line,operations=[Operation('date_picture',block[0].line,{'profile':PROFILE,'ranges':ranges,'other':other,'source_lines':[s.line for s in block]})])


def _parse_print(block):
    from .plan import Step,Operation
    if len(block) not in (4,5) or block[-1].text.lower()!='run':raise ValueError('date PICTURE PRINT requires VAR,FORMAT,optional TITLE,RUN')
    header=re.fullmatch(r'proc\s+print\s+data\s*=\s*('+SOURCE_NAME+r')(?:\s*\(\s*obs\s*=\s*([0-9]{1,4})\s*\))?',block[0].text,re.I|re.ASCII)
    columns=re.fullmatch(r'var\s+(.+)',block[1].text,re.I|re.ASCII)
    binding=re.fullmatch(r'format\s+(.+)\s+('+SOURCE_NAME+r')\.',block[2].text,re.I|re.ASCII)
    if header is None or columns is None or binding is None:raise ValueError('date PICTURE PRINT declaration differs')
    changes=[] if len(block)==4 else [parse_title(block[3]).operations[0].args['text']]
    name=header[1].lower();args={'profile':PROFILE,'columns':columns[1].lower().split(),'bound':binding[1].lower().split(),'format':binding[2].lower(),
                              'obs':None if header[2] is None else int(header[2]),'title_change':changes,'source_lines':[s.line for s in block]}
    return Step('picture_print',name,block[0].line,inputs=[name],operations=[Operation('picture_print',block[0].line,args)])


def source_steps(source,statements):
    from .parser import Kind
    blocks=list(_blocks(statements))
    selected=any(block[0].text.lower()=='proc format' and any(re.match(r'^picture\s',s.text,re.I|re.ASCII) and re.search(r'\bdatatype\s*=\s*date\b',s.text,re.I|re.ASCII) for s in block) for _,_,block in blocks)
    if not selected:return [],[],{},False
    steps=[];failures=[];routes={}
    for start,end,block in blocks:
        text=block[0].text
        try:
            if not all(s.terminated and s.text.isascii() for s in block):raise ValueError('date PICTURE requires complete ASCII declarations')
            text=block[0].text
            if re.match(r'^data\s',text,re.I|re.ASCII):step=core.retag(_parse_data(block,source),'picture_data',PROFILE);route='picture-date-input'
            elif text.lower()=='proc format':step=_parse_definition(block);route='date-picture'
            elif re.match(r'^proc\s+print\b',text,re.I|re.ASCII):step=_parse_print(block);route='picture-date-print'
            elif len(block)==1 and re.match(r'^title(?:\s|$)',text,re.I|re.ASCII):step=parse_title(block[0]);route='logical-title'
            else:raise ValueError('date PICTURE family permits only its DATA,PICTURE,PRINT and TITLE')
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
    plan=Plan(steps=steps);plan.tickets.extend(Ticket(line,text,'date-picture',reason) for line,text,reason in failures)
    plan.matched.extend((construct,rule,statements[index].line) for index,(construct,rule) in routes.items())
    if not plan.tickets:
        try:validate_program(plan.to_dict())
        except (ValueError,TypeError,KeyError,RecursionError) as error:plan.tickets.append(Ticket(1,'date picture program','date-picture',str(error)))
    return plan
