"""Bounded integer PICTURE composition with an explicit source-prefix policy."""
from copy import deepcopy
import json
import re

from . import format_core as core,format_report as reports
from .character_input import ordinary,SOURCE_NAME
from .date_program import _literal
from .formatted_program import _blocks
from .mixed_reports import parse_title,validate_step as validate_title,execute_title

PROFILE='numeric-picture-fields-v1'
REPORT_CONTRACT='ascii-number-picture-report-v1'
KINDS=frozenset(('number_data','number_picture','number_report'))
ROUTES={'number-picture-input':'DS-088','number-picture':'DS-087','number-picture-report':'ST-028','logical-title':'ST-020'}
MINIMUM=-2147483647
MAXIMUM=2147483647


def accounting_frame(source):
    """Admit one prefix only when the ASCII body selects this source family."""
    from .parser import split_statements,ParseError
    body=source[1:] if source.startswith('\ufeff') else source
    if not body.isascii():return source,0
    try:statements=split_statements(body)
    except ParseError:return source,0
    if not _selected(statements):return source,0
    return body,3 if source.startswith('\ufeff') else 0


def _selected(statements):
    def _mask_strings(text):
        text=re.sub(r'"(?:[^"]|"")*"', ' ', text)
        return re.sub(r"'(?:[^']|'')*'", ' ', text)
    return any(re.match(r'^picture\s+',s.text,re.I|re.ASCII) and not re.search(r'\bdatatype\s*=',_mask_strings(s.text),re.I|re.ASCII) for s in statements)


def _name(name):return ordinary(name) and not name[-1].isdigit() and (name in ('delgrp','delgx','delgy') or name.startswith('usr_'))


def template(text,noedit):
    core.text(text,40)
    if type(noedit) is not bool or not text.strip(' ') or '%' in text:raise ValueError('numeric PICTURE requires nonblank nonmacro text and exact NOEDIT flag')
    if noedit or not re.search(r'[0-9]',text,re.ASCII):return
    item=re.fullmatch(r'([0-9]{1,16})[A-Za-z ]*',text,re.ASCII)
    if item is None or not any(c!='0' for c in item[1]):raise ValueError('numeric PICTURE selectors must begin the template and include a nonzero selector')


def validate_picture(step,args):
    if set(args)!={'profile','ranges','source_lines'} or not _name(step['name']) or type(args['ranges']) is not list or not 1<=len(args['ranges'])<=32:raise ValueError('numeric PICTURE requires a bounded local definition')
    previous=MINIMUM-1
    for item in args['ranges']:
        if (type(item) is not dict or set(item)!={'lower','upper','text','noedit'} or type(item.get('lower')) is not int or type(item.get('upper')) is not int
                or not MINIMUM<=item['lower']<=item['upper']<=MAXIMUM or item['lower']!=previous+1):raise ValueError('numeric PICTURE requires complete ordered contiguous integer coverage')
        template(item['text'],item['noedit']);previous=item['upper']
    if previous!=MAXIMUM:raise ValueError('numeric PICTURE requires complete tail coverage')
    core.source_lines(args['source_lines'],step,3)
    return deepcopy(args)


def validate_data(step,args):
    if (set(args)!={'profile','number','character','width','records','source_lines'} or not ordinary(args.get('number')) or not ordinary(args.get('character'))
            or args['number']==args['character'] or type(args.get('width')) is not int or not 1<=args['width']<=8
            or type(args.get('records')) is not list or len(args['records'])>1000):raise ValueError('numeric PICTURE DATA requires one integer and one fixed character read')
    core.source_lines(args['source_lines'],step,6);lines=args['source_lines'];records=args['records']
    if lines[4]!=lines[3]+len(records)+1 or lines[5]<=lines[4]:raise ValueError('numeric PICTURE DATA record provenance differs')
    schema={args['number']:{'type':'number','length':8},args['character']:{'type':'character','length':args['width']}};rows=[]
    for record in records:
        if type(record) is not str or len(record)>80:raise ValueError('numeric PICTURE record exceeds qualified width')
        item=re.fullmatch(r'([+-]?[0-9]{1,10}) ([A-Za-z]{'+str(args['width'])+r'})( *)',record,re.ASCII)
        if item is None or not MINIMUM<=int(item[1])<=MAXIMUM:raise ValueError('numeric PICTURE record requires one integer,one blank and exact-width ASCII letters')
        rows.append({args['number']:float(int(item[1])),args['character']:item[2]})
    return {'schema':schema,'rows':rows,'date_columns':[]}


def validate_program(plan,catalog=None):
    if not core.program(plan,catalog,KINDS,PROFILE,ROUTES):return None
    tables={};formats={};contexts=[];prefixes=set();counts={k:0 for k in KINDS};titles=0
    for step in plan['steps']:
        if type(step) is not dict or type(step.get('kind')) is not str:raise ValueError('numeric PICTURE Step kind required')
        kind=step['kind']
        if kind=='report_title':context=validate_title(step);titles+=1
        else:
            args=deepcopy(core.step_args(step,KINDS,PROFILE));prefix=args.pop('source_prefix',None)
            if type(prefix) is not str or prefix not in ('none','utf8-bom'):raise ValueError('numeric PICTURE requires explicit source-prefix identity')
            prefixes.add(prefix);counts[kind]+=1
            if kind=='number_data':
                if step['name'] in tables:raise ValueError('numeric PICTURE requires fresh producers')
                context=validate_data(step,args);tables[step['name']]=context
            elif kind=='number_picture':
                if step['name'] in formats:raise ValueError('numeric PICTURE cannot replace a definition')
                context=validate_picture(step,args);formats[step['name']]=context
            else:
                context=reports.validate_report(step,args,tables,formats,numeric_builtins={'comma12':(-999999999,999999999)},date_builtins=());titles+=len(args['title_change'])
        contexts.append(context)
    if not 1<=counts['number_data']<=8 or not 1<=counts['number_picture']<=8 or counts['number_report']>2 or titles>32 or len(prefixes)!=1:raise ValueError('numeric PICTURE composition or source-prefix consistency bounds exceeded')
    return contexts


def field(value,definition):
    for item in definition['ranges']:
        if item['lower']<=value<=item['upper']:
            text=item['text']
            if item['noedit'] or not re.search(r'[0-9]',text,re.ASCII):return text
            m=re.match(r'([0-9]+)(.*)',text,re.ASCII);selectors=m[1];digits=str(abs(int(value))).zfill(len(selectors))[-len(selectors):];started=False;out=[]
            for selector,digit in zip(selectors,digits,strict=True):
                started=started or selector!='0' or digit!='0';out.append(digit if started else ' ')
            return ''.join(out).lstrip(' ')+m[2]
    raise ValueError('numeric PICTURE value outside validated domain')


def cell(value,spec,fmt,formats):
    if fmt=='comma12':return json.dumps(format(int(value),','))
    if fmt is not None:return json.dumps(field(value,formats[fmt]))
    return json.dumps(value.rstrip(' ')) if spec['type']=='character' else str(int(value))


def run_program(plan,catalog=None,*,trace=None):
    contexts=validate_program(plan,catalog)
    if contexts is None:raise ValueError('numeric PICTURE executor requires its explicit family')
    tables={};formats={};artifacts={};title=None
    def add(text):
        if trace is not None:trace.append(text)
    prefix=next(step['operations'][0]['args']['source_prefix'] for step in plan['steps'] if step['kind'] in KINDS)
    add(f'numeric_picture_prefix|{prefix}|{3 if prefix=="utf8-bom" else 0}')
    for step,context in zip(plan['steps'],contexts,strict=True):
        kind=step['kind'];name=step['name']
        if kind=='number_data':
            tables[name]={key:deepcopy(context[key]) for key in ('schema','rows')}
            for index in range(len(context['rows'])):add(f'number_input|{name}|{index+1}|1');add(f'number_output|{name}|{index+1}')
            add(f'number_input|{name}|{len(context["rows"])+1}|0')
        elif kind=='number_picture':formats[name]=context;add(f'number_picture|{name}|{len(context["ranges"])}')
        elif kind=='report_title':
            title=execute_title(step);add('number_title|reset' if title is None else 'number_title|set|'+title.encode('ascii').hex())
        else:
            if context['title_change']:
                title=context['title_change'][0];add('number_title|reset' if title is None else 'number_title|set|'+title.encode('ascii').hex())
            table=tables[name];ordinal=len(artifacts)+1;lines=reports.render(table,context,title,lambda v,s,f:cell(v,s,f,formats))
            add(f'number_report|{name}|{ordinal}|{len(table["rows"])}');add('number_header|'+lines[int(title is not None)].encode('ascii').hex())
            for index,line in enumerate(lines[1+int(title is not None):],1):add(f'number_report_row|{ordinal}|{index}|'+line.encode('ascii').hex())
            key=f'report_{ordinal:02}.txt';artifacts[key]='\n'.join(lines)+'\n';reports.validate_reports(artifacts);add('number_artifact|'+key+'|'+str(len(artifacts[key])))
    result={'datasets':deepcopy(tables),'log':[]}
    if artifacts:result['reports']=artifacts
    return result


def parse_data(block,source):
    from .parser import Kind
    from .plan import Step,Operation
    if len(block)!=6 or block[1].text.lower()!='infile datalines' or block[3].text.lower()!='datalines' or block[-1].text.lower()!='run' or not any(t.kind is Kind.DATA for t in block[4].tokens):raise ValueError('numeric PICTURE DATA requires INFILE DATALINES,INPUT,payload and RUN')
    header=re.fullmatch(r'data\s+('+SOURCE_NAME+r')',block[0].text,re.I|re.ASCII)
    decl=re.fullmatch(r'input\s+('+SOURCE_NAME+r')\s+('+SOURCE_NAME+r')\s+\$([1-8])\.',block[2].text,re.I|re.ASCII)
    if header is None or decl is None:raise ValueError('numeric PICTURE fixed-input declaration differs')
    raw=block[4].tokens[0].text.replace('\r\n','\n');parts=raw.split('\n')
    if not parts or parts[0].strip(' ') or parts[-1]!='':raise ValueError('numeric PICTURE payload starts on a new physical line')
    records=parts[1:-1];terminator=block[3].line+raw.count('\n')
    if source.splitlines()[terminator-1]!=';':raise ValueError('numeric PICTURE payload requires a standalone terminator')
    args={'profile':PROFILE,'number':decl[1].lower(),'character':decl[2].lower(),'width':int(decl[3]),'records':records,'source_lines':[block[0].line,block[1].line,block[2].line,block[3].line,terminator,block[-1].line]}
    return Step('number_data',header[1].lower(),block[0].line,operations=[Operation('number_data',block[0].line,args)])


def parse_picture(header,statement,run):
    from .plan import Step,Operation
    head=re.fullmatch(r'picture\s+('+SOURCE_NAME+r')\s+(.+)',statement.text,re.I|re.S|re.ASCII)
    if head is None:raise ValueError('numeric PICTURE declaration differs')
    pattern=re.compile(r"\s*(low|[+-]?[0-9]{1,10})(?:\s*(<)?\s*-\s*(<)?\s*(high|[+-]?[0-9]{1,10}))?\s*=\s*('(?:[^']|'')*'|\"(?:[^\"]|\"\")*\")\s*(\(\s*noedit\s*\))?(?=\s|$)",re.I|re.S|re.ASCII)
    rest=head[2];ranges=[]
    while rest.strip():
        item=pattern.match(rest)
        if item is None:raise ValueError('numeric PICTURE requires bounded integer ranges,literal text and optional NOEDIT')
        if item[1].lower()=='low' and (item[2] or item[4] is None) or item[4] and item[4].lower()=='high' and item[3]:raise ValueError('numeric PICTURE symbolic bounds must be closed and role-correct')
        lo=MINIMUM if item[1].lower()=='low' else int(item[1]);hi=lo if item[4] is None else MAXIMUM if item[4].lower()=='high' else int(item[4])
        ranges.append({'lower':lo+int(item[2] is not None),'upper':hi-int(item[3] is not None),'text':_literal(item[5]),'noedit':item[6] is not None});rest=rest[item.end():]
    args={'profile':PROFILE,'ranges':ranges,'source_lines':[header.line,statement.line,run.line]}
    return Step('number_picture',head[1].lower(),header.line,operations=[Operation('number_picture',header.line,args)])


def source_steps(source,statements):
    from .parser import Kind
    body,prefix=accounting_frame(source)
    if not _selected(statements):return [],[],{},False
    steps=[];failures=[];routes={}
    for start,end,block in _blocks(statements):
        text=block[0].text
        try:
            if not body.isascii() or not all(s.terminated and s.text.isascii() for s in block):raise ValueError('numeric PICTURE requires one optional prefix BOM and complete ASCII body')
            if re.match(r'^data\s',text,re.I|re.ASCII):new=[parse_data(block,body)];route='number-picture-input'
            elif text.lower()=='proc format':
                if not 3<=len(block)<=10 or block[-1].text.lower()!='run':raise ValueError('numeric PICTURE FORMAT requires1..8 definitions and RUN')
                new=[parse_picture(block[0],s,block[-1]) for s in block[1:-1]];route='number-picture'
            elif re.match(r'^proc\s+report\b',text,re.I|re.ASCII):new=[reports.parse_report(block,'number_report',PROFILE)];route='number-picture-report'
            elif len(block)==1 and re.match(r'^title(?:\s|$)',text,re.I|re.ASCII):new=[parse_title(block[0])];route='logical-title'
            else:raise ValueError('numeric PICTURE family contains an unqualified statement')
            for step in new:
                if step.kind in KINDS:step.operations[0].args['source_prefix']='utf8-bom' if prefix else 'none'
                steps.append(step)
            for index in range(start,end):
                if not any(t.kind is Kind.DATA for t in statements[index].tokens):routes[index]=(route,ROUTES[route])
        except (ValueError,TypeError,KeyError,RecursionError) as error:failures.append((block[0].line,text,str(error)))
    return steps,failures,routes,True


def compile_program(source,legacy):
    from .parser import split_statements,ParseError
    from .plan import Plan,Ticket
    body,_=accounting_frame(source)
    try:statements=split_statements(body)
    except ParseError:return legacy(source)
    steps,failures,routes,selected=source_steps(source,statements)
    if not selected:return legacy(source)
    plan=Plan(steps=steps);plan.tickets.extend(Ticket(line,text,'numeric-picture',reason) for line,text,reason in failures)
    plan.matched.extend((construct,rule,statements[index].line) for index,(construct,rule) in routes.items())
    if not plan.tickets:
        try:validate_program(plan.to_dict())
        except (ValueError,TypeError,KeyError,RecursionError) as error:plan.tickets.append(Ticket(1,'numeric PICTURE program','numeric-picture',str(error)))
    return plan
