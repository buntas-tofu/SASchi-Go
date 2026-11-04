"""Finite job-local FCMP week functions, callback formats and ordered reports."""
from copy import deepcopy
import json
import re

from sas_semantics import SAS_CALENDAR_MIN_DAY as MIN_DAY,SAS_CALENDAR_MAX_DAY as MAX_DAY
from . import format_core as core,format_report as reports
from .character_input import ordinary,SOURCE_NAME
from .date_foundations import sas_date_field
from .date_program import _parse_data,_literal
from .mixed_reports import parse_title,validate_step as validate_title,execute_title,_title

PROFILE='week-callback-report-v1'
REPORT_CONTRACT='ascii-week-callback-report-v1'
KINDS=frozenset(('week_library','week_cmplib','week_format','week_data','week_report'))
ROUTES={'week-library':'DS-089','week-cmplib':'DS-089','week-format':'DS-090','week-input':'DS-091','week-report':'ST-029','logical-title':'ST-020'}


def _name(name):return ordinary(name) and not name[-1].isdigit() and (name in ('start','end') or name.startswith('usr_'))


def shifted_day(value,body):
    if value is None:return None
    return int(value)-((int(value)+5-(body['anchor']-1))%7)+7*body['offset']+body['adjust']


def validate_library(step,args):
    if set(args)!={'profile','package','functions','source_lines'} or step['name']!='functions' or not ordinary(args.get('package')) or type(args.get('functions')) is not list or not 1<=len(args['functions'])<=8:raise ValueError('week FCMP requires one bounded work.functions package')
    names=set()
    for body in args['functions']:
        if (type(body) is not dict or set(body)!={'name','argument','local','anchor','offset','adjust','return_width'} or not _name(body.get('name')) or body['name'] in names
                or not ordinary(body.get('argument')) or not ordinary(body.get('local')) or body['argument']==body['local']
                or any(type(body.get(k)) is not int for k in ('anchor','offset','adjust','return_width')) or body['return_width']!=9
                or (body['anchor'],body['offset'],body['adjust']) not in ((2,0,0),(7,1,-1))):raise ValueError('week FCMP requires unique typed functions and exact qualified INTNX/DATE9 bodies')
        names.add(body['name'])
    core.source_lines(args['source_lines'],step,2+4*len(names));return deepcopy(args)


def validate_report(step,args,tables,formats,functions):
    if (set(args)!={'profile','columns','definitions','title_change','source_lines'} or step['name'] not in tables or type(args['columns']) is not list or not 2<=len(args['columns'])<=32
            or type(args['definitions']) is not dict or type(args['title_change']) is not list or len(args['title_change'])>1):raise ValueError('week REPORT requires bounded columns,definitions and title change')
    table=tables[step['name']];aliases={};spans=[]
    for col in args['columns']:
        if type(col) is not dict or set(col)!={'source','alias','span'} or not ordinary(col.get('source')) or not ordinary(col.get('alias')) or col['alias'] in aliases or col['source'] not in table['schema']:raise ValueError('week REPORT requires prior source columns and unique aliases')
        if col['span'] is not None:
            _title(col['span'])
            if col['alias']==col['source']:raise ValueError('week REPORT spanning heading requires explicit aliases')
            spans.append(col['span'])
        elif spans:raise ValueError('week REPORT requires one trailing spanning group')
        aliases[col['alias']]=col['source']
    if not spans or len(set(spans))!=1 or set(args['definitions'])!=set(aliases):raise ValueError('week REPORT requires one span and one DEFINE for every column')
    order=[];displays=0
    for alias,spec in args['definitions'].items():
        if type(spec) is not dict or set(spec)!={'display','order','format','label'} or type(spec.get('display')) is not bool or type(spec.get('order')) is not bool or spec['format'] is not None and type(spec['format']) is not str:raise ValueError('week REPORT DEFINE requires exact typed fields')
        if spec['label'] is not None:_title(spec['label'])
        source=aliases[alias];fmt=spec['format'];schema=table['schema'][source];displays+=spec['display']
        if spec['order']:
            if spec['display'] or fmt is not None:raise ValueError('week ORDER cannot also DISPLAY or bind a format')
            order.append(alias)
        elif fmt=='weekdate' or fmt is not None and fmt.endswith('12') and fmt[:-2] in formats:
            if source not in table['date_columns']:raise ValueError('week date/callback format requires genuine DATE9 storage')
            if fmt!='weekdate':
                body=functions[formats[fmt[:-2]]]
                for row in table['rows']:
                    value=shifted_day(row[source],body)
                    if value is not None and not MIN_DAY<=value<=MAX_DAY:raise ValueError('week callback result exceeds the qualified calendar')
        elif fmt=='10':
            if schema['type']!='number' or source in table['date_columns']:raise ValueError('week numeric10 requires non-date numeric storage')
            if any(row[source] is not None and not 0<=row[source]<=9999999999 for row in table['rows']):raise ValueError('week numeric10 value exceeds whole-number field')
        elif fmt is not None:raise ValueError('week REPORT references an unavailable format or unqualified callback width')
        elif not spec['order'] and schema['type']=='number':raise ValueError('week non-ORDER numeric columns require an explicit qualified format')
    first=args['columns'][0]
    if order!=[first['alias']] or first['alias']!=first['source'] or first['span'] is not None or not displays:raise ValueError('week REPORT requires one first unaliased ORDER and an explicit DISPLAY')
    key=first['source']
    if table['schema'][key]['type']!='number' or key in table['date_columns']:raise ValueError('week ORDER requires non-date numeric storage')
    previous=10
    for row in table['rows']:
        value=row[key]
        if value is None or not 10<=value<=99 or value<previous:raise ValueError('week ORDER requires ascending nonmissing two-digit integers')
        previous=value
    if args['title_change']:_title(args['title_change'][0])
    core.source_lines(args['source_lines'],step,3+len(args['definitions'])+len(args['title_change']));return deepcopy(args)


def validate_program(plan,catalog=None):
    if not core.program(plan,catalog,KINDS,PROFILE,ROUTES):return None
    tables={};functions={};formats={};contexts=[];library=None;active=False;counts={k:0 for k in KINDS};titles=0
    for step in plan['steps']:
        if type(step) is not dict or type(step.get('kind')) is not str:raise ValueError('week callback Step kind required')
        kind=step['kind']
        if kind=='report_title':context=validate_title(step);titles+=1
        else:
            args=core.step_args(step,KINDS,PROFILE);counts[kind]+=1
            if kind=='week_library':
                if library is not None:raise ValueError('week functions require one local library block')
                context=validate_library(step,args);library='work.functions';functions={body['name']:body for body in context['functions']}
            elif kind=='week_cmplib':
                if set(args)!={'profile','library','source_lines'} or args.get('library')!=library or library is None or active or step['name']!='functions':raise ValueError('week CMPLIB requires one preceding local library activation')
                core.source_lines(args['source_lines'],step,1);context=deepcopy(args);active=True
            elif kind=='week_format':
                if set(args)!={'profile','function','source_lines'} or not active or not _name(step['name']) or step['name'] in formats or type(args.get('function')) is not str or args['function'] not in functions:raise ValueError('week VALUE callback requires activated preceding function and a unique format')
                core.source_lines(args['source_lines'],step,3);context=deepcopy(args);formats[step['name']]=args['function']
            elif kind=='week_data':
                if step['name'] in tables:raise ValueError('week callback DATA requires fresh producers')
                context=core.date_data(step,args);tables[step['name']]=context
            else:context=validate_report(step,args,tables,formats,functions);titles+=len(args['title_change'])
        contexts.append(context)
    if counts['week_library']!=1 or counts['week_cmplib']!=1 or not 1<=counts['week_format']<=8 or not 1<=counts['week_data']<=8 or counts['week_report']>2 or titles>32:raise ValueError('week callback composition bounds exceeded')
    return contexts


def callback(value,body):
    day=shifted_day(value,body)
    if day is None:return '.'
    from .groupformat import report_cell
    return json.loads(report_cell(day,{'type':'number','length':8},'date9',{}))


def render(table,args,title,functions,formats,add,ordinal):
    header=' '.join(json.dumps((col['span']+'/' if col['span'] else '')+(args['definitions'][col['alias']]['label'] or col['alias'])) for col in args['columns'])
    lines=[] if title is None else ['TITLE: '+title];lines.append(header);previous=None
    for index,row in enumerate(table['rows'],1):
        cells=[]
        for col in args['columns']:
            value=row[col['source']];spec=args['definitions'][col['alias']];fmt=spec['format']
            if spec['order']:token=json.dumps('' if value==previous else str(int(value)));previous=value
            elif fmt=='weekdate':token=json.dumps(sas_date_field(value,'weekdate',29).strip(' '))
            elif fmt is not None and fmt.endswith('12'):
                fn=formats[fmt[:-2]];label=callback(value,functions[fn]);token=json.dumps(label);add(f'week_callback|{fn}|{"." if value is None else int(value)}|'+label.encode('ascii').hex())
            elif fmt=='10':token=json.dumps('.' if value is None else str(int(value)))
            else:token=json.dumps(value.rstrip(' '))
            cells.append(token)
        line=' '.join(cells);lines.append(line);add(f'week_report_row|{ordinal}|{index}|'+line.encode('ascii').hex())
    return lines


def run_program(plan,catalog=None,*,trace=None):
    contexts=validate_program(plan,catalog)
    if contexts is None:raise ValueError('week callback executor requires its explicit family')
    tables={};functions={};formats={};artifacts={};title=None
    def add(value):
        if trace is not None:trace.append(value)
    for step,context in zip(plan['steps'],contexts,strict=True):
        kind=step['kind'];name=step['name']
        if kind=='week_library':
            for body in context['functions']:
                functions[body['name']]=body;add(f'week_function|{body["name"]}|{body["anchor"]}|{body["offset"]}|{body["adjust"]}')
            add(f'week_library|work.functions|{context["package"]}|{len(functions)}')
        elif kind=='week_cmplib':add('week_cmplib|'+context['library'])
        elif kind=='week_format':formats[name]=context['function'];add(f'week_format|{name}|{formats[name]}')
        elif kind=='week_data':
            tables[name]={k:deepcopy(context[k]) for k in ('schema','rows')}
            for index in range(len(context['rows'])):add(f'week_input|{name}|{index+1}|1');add(f'week_output|{name}|{index+1}')
            add(f'week_input|{name}|{len(context["rows"])+1}|0')
        elif kind=='report_title':
            title=execute_title(step);add('week_title|reset' if title is None else 'week_title|set|'+title.encode('ascii').hex())
        else:
            if context['title_change']:
                title=context['title_change'][0];add('week_title|reset' if title is None else 'week_title|set|'+title.encode('ascii').hex())
            table=tables[name];ordinal=len(artifacts)+1
            add(f'week_report|{name}|{ordinal}|{len(table["rows"])}')
            # Header precedes callback events in the qualified execution trace.
            header=' '.join(json.dumps((c['span']+'/' if c['span'] else '')+(context['definitions'][c['alias']]['label'] or c['alias'])) for c in context['columns'])
            add('week_header|'+header.encode('ascii').hex())
            lines=render(table,context,title,functions,formats,add,ordinal)
            key=f'report_{ordinal:02}.txt';artifacts[key]='\n'.join(lines)+'\n';reports.validate_reports(artifacts);add('week_artifact|'+key+'|'+str(len(artifacts[key])))
    result={'datasets':deepcopy(tables),'log':[]}
    if artifacts:result['reports']=artifacts
    return result


def blocks(statements):
    """Own the FCMP QUIT boundary without changing older RUN-based families."""
    from .parser import Kind
    pos=0
    while pos<len(statements):
        start=pos;text=statements[pos].text;pos+=1
        if re.match(r'^(?:data|proc)\s',text,re.I|re.ASCII):
            terminator='quit' if re.match(r'^proc\s+fcmp\b',text,re.I|re.ASCII) else 'run'
            while pos<len(statements):
                st=statements[pos];opaque=any(t.kind is Kind.DATA for t in st.tokens)
                if not opaque and st.text.lower()==terminator:pos+=1;break
                if not opaque and re.match(r'^(?:data|proc)\s',st.text,re.I|re.ASCII):break
                pos+=1
        yield start,pos,statements[start:pos]


def parse_library(block):
    from .plan import Step,Operation
    head=re.fullmatch(r'proc\s+fcmp\s+outlib\s*=\s*work\.functions\.('+SOURCE_NAME+r')',block[0].text,re.I|re.ASCII)
    if head is None or block[-1].text.lower()!='quit' or not 6<=len(block)<=34 or (len(block)-2)%4:raise ValueError('week FCMP requires exact work.functions package and QUIT')
    functions=[]
    for i in range(1,len(block)-1,4):
        f=re.fullmatch(r'function\s+('+SOURCE_NAME+r')\s*\(\s*('+SOURCE_NAME+r')\s*\)\s*\$\s*9',block[i].text,re.I|re.ASCII)
        if f is None:raise ValueError('week FUNCTION requires one numeric argument and character9 return')
        d=re.fullmatch(r'('+SOURCE_NAME+r')\s*=\s*intnx\s*\(\s*([\x27\x22])week\.([27])\2\s*,\s*'+re.escape(f[2])+r'\s*,\s*([01])\s*\)\s*(?:-\s*(1))?',block[i+1].text,re.I|re.ASCII)
        if d is None or re.fullmatch(r'return\s*\(\s*put\s*\(\s*'+re.escape(d[1])+r'\s*,\s*date9\.\s*\)\s*\)',block[i+2].text,re.I|re.ASCII) is None or block[i+3].text.lower()!='endsub':raise ValueError('week FUNCTION body must be qualified INTNX and RETURN(PUT(local,DATE9.))')
        functions.append({'name':f[1].lower(),'argument':f[2].lower(),'local':d[1].lower(),'anchor':int(d[3]),'offset':int(d[4]),'adjust':-int(d[5] or 0),'return_width':9})
    args={'profile':PROFILE,'package':head[1].lower(),'functions':functions,'source_lines':[s.line for s in block]}
    return Step('week_library','functions',block[0].line,operations=[Operation('week_library',block[0].line,args)])


def parse_columns(text):
    m=re.fullmatch(r'columns?\s+(.+?)\s*\(\s*(\x27(?:[^\x27]|\x27\x27)*\x27|"(?:[^"]|"")*")\s+(.+)\)',text,re.I|re.S|re.ASCII)
    if m is None:raise ValueError('week REPORT requires simple columns and one literal trailing span')
    result=[]
    for section,span in ((m[1],None),(m[3],_literal(m[2]))):
        result.extend({**col,'span':span} for col in reports.parse_columns('columns '+section))
    return result


def parse_definition(text):
    m=re.fullmatch(r'define\s+('+SOURCE_NAME+r')\s*/\s*(.+)',text,re.I|re.S|re.ASCII)
    if m is None:raise ValueError('week DEFINE declaration differs')
    rest=m[2];spec={'display':False,'order':False,'format':None,'label':None}
    pattern=re.compile(r'\s*(display\b|order\b|format\s*=\s*(10|weekdate|'+SOURCE_NAME+r'12)\.|(\x27(?:[^\x27]|\x27\x27)*\x27|"(?:[^"]|"")*"))(?=\s|$)',re.I|re.S|re.ASCII)
    while rest.strip():
        item=pattern.match(rest)
        if item is None:raise ValueError('week DEFINE permits ORDER,DISPLAY,qualified FORMAT and literal label')
        key=item[1].lower()
        if key in ('order','display'):
            if spec[key]:raise ValueError('duplicate week usage')
            spec[key]=True
        elif item[2] is not None:
            if spec['format'] is not None:raise ValueError('duplicate week FORMAT')
            spec['format']=item[2].lower()
        else:
            if spec['label'] is not None:raise ValueError('duplicate week label')
            spec['label']=_literal(item[3])
        rest=rest[item.end():]
    return m[1].lower(),spec


def parse_report(block):
    from .plan import Step,Operation
    head=re.fullmatch(r'proc\s+report\s+data\s*=\s*('+SOURCE_NAME+r')\s+nowd',block[0].text,re.I|re.ASCII)
    if head is None or len(block)<4 or block[-1].text.lower()!='run':raise ValueError('week REPORT requires DATA=name NOWD and RUN')
    columns=parse_columns(block[1].text);definitions={};i=2
    while i<len(block)-1 and re.match(r'^define\s',block[i].text,re.I|re.ASCII):
        alias,spec=parse_definition(block[i].text)
        if alias in definitions:raise ValueError('duplicate week DEFINE')
        definitions[alias]=spec;i+=1
    changes=[]
    if i<len(block)-1:changes=[parse_title(block[i]).operations[0].args['text']];i+=1
    if i!=len(block)-1:raise ValueError('week REPORT contains an unqualified statement')
    name=head[1].lower();args={'profile':PROFILE,'columns':columns,'definitions':definitions,'title_change':changes,'source_lines':[s.line for s in block]}
    return Step('week_report',name,block[0].line,inputs=[name],operations=[Operation('week_report',block[0].line,args)])


def source_steps(source,statements):
    from .parser import Kind
    from .plan import Step,Operation
    if not any(re.match(r'^proc\s+fcmp\b',s.text,re.I|re.ASCII) for s in statements):return [],[],{},False
    steps=[];failures=[];routes={}
    for start,end,block in blocks(statements):
        text=block[0].text
        try:
            if not all(s.terminated and s.text.isascii() for s in block):raise ValueError('week callback requires complete ASCII statements')
            if re.match(r'^proc\s+fcmp\b',text,re.I|re.ASCII):new=[parse_library(block)];route='week-library'
            elif re.match(r'^options\s',text,re.I|re.ASCII):
                if len(block)!=1 or re.fullmatch(r'options\s+cmplib\s*=\s*work\.functions',text,re.I|re.ASCII) is None:raise ValueError('week CMPLIB requires exactly work.functions')
                new=[Step('week_cmplib','functions',block[0].line,operations=[Operation('week_cmplib',block[0].line,{'profile':PROFILE,'library':'work.functions','source_lines':[block[0].line]})])];route='week-cmplib'
            elif text.lower()=='proc format':
                if not 3<=len(block)<=10 or block[-1].text.lower()!='run':raise ValueError('week FORMAT requires1..8VALUE callbacks and RUN')
                new=[]
                for statement in block[1:-1]:
                    m=re.fullmatch(r'value\s+('+SOURCE_NAME+r')\s+other\s*=\s*\[\s*('+SOURCE_NAME+r')\s*\(\s*\)\s*\]',statement.text,re.I|re.ASCII)
                    if m is None:raise ValueError('week VALUE requires OTHER=[function()]')
                    new.append(Step('week_format',m[1].lower(),block[0].line,operations=[Operation('week_format',block[0].line,{'profile':PROFILE,'function':m[2].lower(),'source_lines':[block[0].line,statement.line,block[-1].line]})]))
                route='week-format'
            elif re.match(r'^data\s',text,re.I|re.ASCII):new=[core.retag(_parse_data(block,source),'week_data',PROFILE)];route='week-input'
            elif re.match(r'^proc\s+report\b',text,re.I|re.ASCII):new=[parse_report(block)];route='week-report'
            elif len(block)==1 and re.match(r'^title(?:\s|$)',text,re.I|re.ASCII):new=[parse_title(block[0])];route='logical-title'
            else:raise ValueError('week family contains an unqualified statement')
            steps.extend(new)
            for index in range(start,end):
                if not any(t.kind is Kind.DATA for t in statements[index].tokens):routes[index]=(route,ROUTES[route])
        except (ValueError,TypeError,KeyError,RecursionError) as error:failures.append((block[0].line,text,str(error)))
    return steps,failures,routes,True


def compile_program(source,legacy):
    from .parser import split_statements,ParseError
    from .plan import Plan,Ticket
    try:statements=split_statements(source)
    except ParseError:return legacy(source)
    steps,failures,routes,selected=source_steps(source,statements)
    if not selected:return legacy(source)
    plan=Plan(steps=steps);plan.tickets.extend(Ticket(line,text,'week-callback',reason) for line,text,reason in failures)
    plan.matched.extend((construct,rule,statements[index].line) for index,(construct,rule) in routes.items())
    if not plan.tickets:
        try:validate_program(plan.to_dict())
        except (ValueError,TypeError,KeyError,RecursionError) as error:plan.tickets.append(Ticket(1,'week callback program','week-callback',str(error)))
    return plan
