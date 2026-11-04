"""Bounded character formats, country FCMP, quoted input and computed REPORT."""
from copy import deepcopy
import json
import re

from . import format_core as core,postal_reference as reference
from .character_input import ordinary,SOURCE_NAME
from .date_program import _literal
from .mixed_reports import parse_title,validate_step as validate_title,execute_title,_title
from .week_callbacks import blocks

PROFILE='postal-function-report-v1'
REPORT_CONTRACT='ascii-postal-function-report-v1'
KINDS=frozenset(('postal_format','postal_library','postal_cmplib','postal_data','postal_sort','postal_report'))
ROUTES={'postal-format':'DS-092','postal-library':'DS-093','postal-cmplib':'DS-093','postal-input':'DS-094','postal-sort':'DS-095','postal-report':'ST-030','logical-title':'ST-020'}
QUOTED=r'(\x27(?:[^\x27]|\x27\x27)*\x27|"(?:[^"]|"")*")'


def _name(name,special):return ordinary(name) and not name[-1].isdigit() and (name==special or name.startswith('usr_'))


def validate_format(step,args):
    if set(args)!={'profile','ranges','source_lines'} or not _name(step['name'],'postabb') or type(args['ranges']) is not list or not 1<=len(args['ranges'])<=32:raise ValueError('postal character VALUE requires a bounded local definition')
    for item in args['ranges']:
        if (type(item) is not dict or set(item)!={'lower','upper','text'} or any(type(item.get(k)) is not str for k in ('lower','upper','text'))
                or re.fullmatch('[0-9]{4}',item['lower'],re.ASCII) is None or re.fullmatch('[0-9]{4}',item['upper'],re.ASCII) is None or item['lower']>item['upper']
                or re.fullmatch('[A-Z]{1,3}',item['text'],re.ASCII) is None):raise ValueError('postal character ranges require four-digit inclusive bounds and literal alphabetic labels')
    previous=''
    for item in sorted(args['ranges'],key=lambda item:item['lower']):
        if item['lower']<=previous:raise ValueError('postal character ranges overlap')
        previous=item['upper']
    core.source_lines(args['source_lines'],step,3);return deepcopy(args)


def validate_library(step,args,formats):
    if set(args)!={'profile','package','function','source_lines'} or step['name']!='functions' or not ordinary(args.get('package')) or type(args.get('function')) is not dict:raise ValueError('postal FCMP requires a local work.functions package')
    fn=args['function']
    if (set(fn)!={'name','country','code','local','format','return_width'} or not _name(fn.get('name'),'stateprov')
            or any(not ordinary(fn.get(k)) for k in ('country','code','local')) or len({fn['country'],fn['code'],fn['local']})!=3
            or type(fn.get('format')) is not str or fn['format'] not in formats or type(fn.get('return_width')) is not int or fn['return_width']!=5):raise ValueError('postal function requires two distinct character arguments,a fresh local,prior format and character5 return')
    core.source_lines(args['source_lines'],step,8);return deepcopy(args)


def csv_fields(record):
    if type(record) is not str or not 1<=len(record)<=256 or any(not 32<=ord(c)<=126 for c in record) or '%' in record or '&' in record:raise ValueError('postal CSV requires1..256 nonmacro printable ASCII bytes')
    fields=[];i=0
    while True:
        out=[]
        if i<len(record) and record[i]=='"':
            i+=1;closed=False
            while i<len(record):
                c=record[i];i+=1
                if c=='"':
                    if i<len(record) and record[i]=='"':out.append('"');i+=1
                    else:closed=True;break
                else:out.append(c)
            if not closed or i<len(record) and record[i]!=',':raise ValueError('postal CSV quote is unclosed or followed by junk')
        else:
            while i<len(record) and record[i]!=',':
                if record[i]=='"':raise ValueError('postal CSV refuses quotes in an unquoted field')
                out.append(record[i]);i+=1
        value=''.join(out)
        if not value or value!=value.strip(' ') or value=='.':raise ValueError('postal CSV refuses blank,edge-blank and period-only fields')
        fields.append(value)
        if i==len(record):break
        i+=1
    return fields


def validate_data(step,args):
    if set(args)!={'profile','columns','records','source_lines'} or type(args['columns']) is not list or not 1<=len(args['columns'])<=8 or type(args['records']) is not list or len(args['records'])>1000:raise ValueError('postal DATA requires bounded character declarations and records')
    schema={}
    for col in args['columns']:
        if type(col) is not dict or set(col)!={'name','width'} or not ordinary(col.get('name')) or col['name'] in schema or type(col.get('width')) is not int or not 1<=col['width']<=64:raise ValueError('postal DATA requires unique character1..64 declarations')
        schema[col['name']]={'type':'character','length':col['width']}
    core.source_lines(args['source_lines'],step,6);lines=args['source_lines']
    if lines[4]!=lines[3]+len(args['records'])+1 or lines[5]<=lines[4]:raise ValueError('postal CSV record provenance differs')
    rows=[]
    for record in args['records']:
        fields=csv_fields(record)
        if len(fields)!=len(schema):raise ValueError('postal CSV requires one complete field set per record')
        row={}
        for (name,spec),value in zip(schema.items(),fields,strict=True):
            if len(value)>spec['length']:raise ValueError('postal CSV refuses overwidth fields')
            row[name]=value.ljust(spec['length'])
        rows.append(row)
    return {'schema':schema,'rows':rows}


def validate_dispatch_domain(country,code,definition,mapping):
    if type(country) is not str or type(code) is not str:raise ValueError('postal callback arguments require character storage')
    country=country.rstrip(' ').upper();code=code.rstrip(' ')
    if country=='US':
        if re.fullmatch('[0-9]{5}',code,re.ASCII) is None or code not in reference.DOMAIN or code not in mapping:raise ValueError('ZIPSTATE requires an approved five-digit character ZIP; unverified ZIPs refuse')
    elif country=='AU':
        if re.fullmatch('[0-9]{4}',code,re.ASCII) is None or not any(item['lower']<=code<=item['upper'] for item in definition['ranges']):raise ValueError('postal AU code requires four digits covered by the declared character ranges')


def dispatch_domain(country,code,definition,mapping):
    validate_dispatch_domain(country,code,definition,mapping)
    country=country.rstrip(' ').upper();code=code.rstrip(' ')
    if country=='US':return reference.zip_state(code,mapping)
    if country=='AU':
        for item in definition['ranges']:
            if item['lower']<=code<=item['upper']:return item['text']
    return ''


def validate_report(step,args,tables,sorted_tables,functions,formats,mapping):
    if (set(args)!={'profile','columns','by','computed','label','function','country','code','title_change','source_lines'} or step['name'] not in sorted_tables
            or type(args['columns']) is not list or not 3<=len(args['columns'])<=9 or any(not ordinary(c) for c in args['columns']) or len(set(args['columns']))!=len(args['columns'])
            or not ordinary(args.get('computed')) or args['computed'] not in args['columns'] or type(args.get('function')) is not str or args['function'] not in functions
            or not ordinary(args.get('country')) or not ordinary(args.get('code')) or args['country']==args['code'] or args.get('by')!=sorted_tables[step['name']]
            or type(args['title_change']) is not list or len(args['title_change'])>1):raise ValueError('postal REPORT requires a prior owned country sort and exact computed-column references')
    table=tables[step['name']];schema=table['schema'];computed=args['computed'];position=args['columns'].index(computed)
    if computed in schema or args['country'] not in args['columns'][:position] or args['code'] not in args['columns'][:position] or args['by']!=args['country']:raise ValueError('postal computed field must be fresh and follow both arguments')
    for col in args['columns']:
        if col!=computed and col not in schema:raise ValueError('postal REPORT references an absent character column')
    if (schema[args['country']]!={'type':'character','length':2} or schema[args['code']]!={'type':'character','length':5}):raise ValueError('postal callback requires character2country and character5code storage')
    _title(args['label'])
    if args['label'] is None:raise ValueError('postal computed column requires a literal label')
    if args['title_change']:_title(args['title_change'][0])
    core.source_lines(args['source_lines'],step,8+len(args['title_change']))
    definition=formats[functions[args['function']]]
    for row in table['rows']:validate_dispatch_domain(row[args['country']],row[args['code']],definition,mapping)
    return deepcopy(args)


def validate_program(plan,catalog=None):
    if not core.program(plan,catalog,KINDS,PROFILE,ROUTES):return None
    formats={};functions={};tables={};sorted_tables={};contexts=[];library=False;active=False;counts={k:0 for k in KINDS};titles=0;mapping=None
    for step in plan['steps']:
        if type(step) is not dict or type(step.get('kind')) is not str:raise ValueError('postal Step kind required')
        kind=step['kind']
        if kind=='report_title':context=validate_title(step);titles+=1
        else:
            args=core.step_args(step,KINDS,PROFILE);counts[kind]+=1
            if kind=='postal_format':
                if formats:raise ValueError('postal family requires one character VALUE definition')
                context=validate_format(step,args);formats[step['name']]=context
            elif kind=='postal_library':
                if library:raise ValueError('postal FCMP requires one local function block')
                context=validate_library(step,args,formats);fn=context['function'];functions[fn['name']]=fn['format'];library=True
            elif kind=='postal_cmplib':
                if set(args)!={'profile','library','source_lines'} or args.get('library')!='work.functions' or not library or active or step['name']!='functions':raise ValueError('postal CMPLIB requires one prior local library activation')
                core.source_lines(args['source_lines'],step,1);context=deepcopy(args);active=True
            elif kind=='postal_data':
                if step['name'] in tables:raise ValueError('postal DATA requires fresh producer names')
                context=validate_data(step,args);tables[step['name']]=context
            elif kind=='postal_sort':
                if set(args)!={'profile','key','source_lines'} or step['name'] not in tables or not ordinary(args.get('key')) or tables[step['name']]['schema'].get(args['key'])!={'type':'character','length':2} or sorted_tables:raise ValueError('postal SORT requires one owned character2 country replacement')
                core.source_lines(args['source_lines'],step,3);context=deepcopy(args);sorted_tables[step['name']]=args['key']
            else:
                if not active:raise ValueError('postal REPORT requires active local CMPLIB')
                if mapping is None:mapping=reference.load_reference()
                context=validate_report(step,args,tables,sorted_tables,functions,formats,mapping);titles+=len(args['title_change'])
        contexts.append(context)
    if counts['postal_format']!=1 or counts['postal_library']!=1 or counts['postal_cmplib']!=1 or not 1<=counts['postal_data']<=8 or counts['postal_sort']!=1 or not 1<=counts['postal_report']<=2 or titles>32:raise ValueError('postal composition bounds exceeded')
    return contexts


def execute_sort(table,key,add,name):
    order=sorted(range(len(table['rows'])),key=lambda i:table['rows'][i][key]);add(f'postal_sort|{name}|{key}|{len(order)}')
    for i,j in enumerate(order,1):add(f'postal_sort_row|{i}|{j+1}')
    return {'schema':deepcopy(table['schema']),'rows':[deepcopy(table['rows'][i]) for i in order]}


def callback(country,code,definition,mapping):return dispatch_domain(country,code,definition,mapping).ljust(5)


def validate_reports(artifacts):
    if type(artifacts) is not dict or not 1<=len(artifacts)<=2 or list(artifacts)!=[f'report_{i:02}.txt' for i in range(1,len(artifacts)+1)]:raise ValueError('postal reports require one or two ordered artifacts')
    for text in artifacts.values():
        if type(text) is not str or not text.isascii() or not text.endswith('\n') or len(text)>417056 or any(c!='\n' and not 32<=ord(c)<=126 for c in text):raise ValueError('postal report text/byte limits exceeded')
        lines=text[:-1].split('\n');offset=int(lines[0].startswith('TITLE: '))
        if offset and not 7<=len(lines[0])<=135 or not 1<=len(lines)-offset<=2001 or not lines[offset] or len(lines[offset])>1055:raise ValueError('postal report title/header/line limits exceeded')
        rows=0;groups=0
        for line in lines[offset+1:]:
            if not line or len(line)>415:raise ValueError('postal report row limit exceeded')
            if line.startswith('BY '):
                by=re.fullmatch(r'BY ('+SOURCE_NAME+r')=(.+)',line,re.ASCII)
                if by is None:raise ValueError('postal report BY line differs')
                try:value=json.loads(by[2])
                except json.JSONDecodeError as error:raise ValueError('postal BY value must be JSON text') from error
                if type(value) is not str or not 1<=len(value)<=2:raise ValueError('postal BY value exceeds country width')
                groups+=1
            else:rows+=1
        if rows>1000 or groups>rows:raise ValueError('postal report observation/BY limits exceeded')
    return artifacts


def render(table,args,title,definition,mapping,add,ordinal):
    header=' '.join(json.dumps(args['label'] if col==args['computed'] else col) for col in args['columns']);lines=[] if title is None else ['TITLE: '+title];lines.append(header);previous=None
    for index,row in enumerate(table['rows'],1):
        if row[args['by']]!=previous:
            previous=row[args['by']];line='BY '+args['by']+'='+json.dumps(previous.rstrip(' '));lines.append(line);add('postal_by|'+line.encode('ascii').hex())
        value=callback(row[args['country']],row[args['code']],definition,mapping)
        add('postal_callback|'+args['function']+'|'+row[args['country']].encode('ascii').hex()+'|'+row[args['code']].encode('ascii').hex()+'|'+value.encode('ascii').hex())
        line=' '.join(json.dumps((value if col==args['computed'] else row[col]).rstrip(' ')) for col in args['columns']);lines.append(line);add(f'postal_report_row|{ordinal}|{index}|'+line.encode('ascii').hex())
    return lines


def run_program(plan,catalog=None,*,trace=None):
    contexts=validate_program(plan,catalog)
    if contexts is None:raise ValueError('postal executor requires its explicit family')
    tables={};formats={};functions={};artifacts={};title=None;mapping=reference.load_reference()
    def add(value):
        if trace is not None:trace.append(value)
    for step,context in zip(plan['steps'],contexts,strict=True):
        kind=step['kind'];name=step['name']
        if kind=='postal_format':formats[name]=context;add(f'postal_format|{name}|{len(context["ranges"])}')
        elif kind=='postal_library':
            fn=context['function'];functions[fn['name']]=fn['format'];add(f'postal_function|{fn["name"]}|{fn["format"]}');add('postal_library|work.functions|'+context['package'])
        elif kind=='postal_cmplib':add('postal_cmplib|work.functions')
        elif kind=='postal_data':
            tables[name]=deepcopy(context)
            for index in range(len(context['rows'])):add(f'postal_input|{name}|{index+1}|1');add(f'postal_output|{name}|{index+1}')
            add(f'postal_input|{name}|{len(context["rows"])+1}|0')
        elif kind=='postal_sort':tables[name]=execute_sort(tables[name],context['key'],add,name)
        elif kind=='report_title':
            title=execute_title(step);add('postal_title|reset' if title is None else 'postal_title|set|'+title.encode('ascii').hex())
        else:
            if context['title_change']:
                title=context['title_change'][0];add('postal_title|reset' if title is None else 'postal_title|set|'+title.encode('ascii').hex())
            ordinal=len(artifacts)+1;table=tables[name];add(f'postal_report|{name}|{ordinal}|{len(table["rows"])}')
            header=' '.join(json.dumps(context['label'] if col==context['computed'] else col) for col in context['columns']);add('postal_header|'+header.encode('ascii').hex())
            lines=render(table,context,title,formats[functions[context['function']]],mapping,add,ordinal);key=f'report_{ordinal:02}.txt';artifacts[key]='\n'.join(lines)+'\n';validate_reports(artifacts);add('postal_artifact|'+key+'|'+str(len(artifacts[key])))
    return {'datasets':deepcopy(tables),'log':[],'reports':artifacts}


def parse_format(block):
    from .plan import Step,Operation
    if len(block)!=3 or block[-1].text.lower()!='run':raise ValueError('postal FORMAT requires one character VALUE and RUN')
    m=re.fullmatch(r'value\s+\$('+SOURCE_NAME+r')\s+(.+)',block[1].text,re.I|re.S|re.ASCII)
    if m is None:raise ValueError('postal character VALUE declaration differs')
    rest=m[2];pending=[];ranges=[]
    while rest.strip():
        part=re.match(r'\s*'+QUOTED+r'\s*(?:-\s*'+QUOTED+r')?\s*([,=])\s*',rest,re.ASCII)
        if part is None:raise ValueError('postal character VALUE requires literal ranges or shared-label groups')
        lo=_literal(part[1]);hi=_literal(part[2]) if part[2] else lo;pending.append((lo,hi));rest=rest[part.end():]
        if part[3]=='=':
            label=re.match(QUOTED,rest,re.ASCII)
            if label is None:raise ValueError('postal character VALUE requires a literal label')
            ranges.extend({'lower':lo,'upper':hi,'text':_literal(label[1])} for lo,hi in pending);pending=[];rest=rest[label.end():]
    if pending:raise ValueError('postal character range group is incomplete')
    return Step('postal_format',m[1].lower(),block[0].line,operations=[Operation('postal_format',block[0].line,{'profile':PROFILE,'ranges':ranges,'source_lines':[s.line for s in block]})])


def parse_library(block):
    from .plan import Step,Operation
    h=re.fullmatch(r'proc\s+fcmp\s+outlib\s*=\s*work\.functions\.('+SOURCE_NAME+r')',block[0].text,re.I|re.ASCII)
    if h is None or len(block)!=8 or block[-1].text.lower()!='quit':raise ValueError('postal FCMP requires one qualified function and QUIT')
    f=re.fullmatch(r'function\s+('+SOURCE_NAME+r')\s*\(\s*('+SOURCE_NAME+r')\s*\$\s*,\s*('+SOURCE_NAME+r')\s*\$\s*\)\s*\$\s*5',block[1].text,re.I|re.ASCII)
    if f is None:raise ValueError('postal function requires two character arguments and character5 return')
    a=re.fullmatch(r'if\s+upcase\s*\(\s*'+re.escape(f[2])+r'\s*\)\s*=\s*'+QUOTED+r'\s+then\s+('+SOURCE_NAME+r')\s*=\s*put\s*\(\s*'+re.escape(f[3])+r'\s*,\s*\$('+SOURCE_NAME+r')\.\s*\)',block[2].text,re.I|re.ASCII)
    if a is None or _literal(a[1])!='AU':raise ValueError('postal AU branch requires the exact case-sensitive AU literal and prior character format')
    b=re.fullmatch(r'else\s+if\s+upcase\s*\(\s*'+re.escape(f[2])+r'\s*\)\s*=\s*'+QUOTED+r'\s+then\s+'+re.escape(a[2])+r'\s*=\s*zipstate\s*\(\s*'+re.escape(f[3])+r'\s*\)',block[3].text,re.I|re.ASCII)
    if b is None or _literal(b[1])!='US':raise ValueError('postal US branch requires the exact case-sensitive US literal and ZIPSTATE argument')
    c=re.fullmatch(r'else\s+'+re.escape(a[2])+r'\s*=\s*'+QUOTED,block[4].text,re.I|re.ASCII)
    if c is None or _literal(c[1])!=' ' or re.fullmatch(r'return\s*\(\s*'+re.escape(a[2])+r'\s*\)',block[5].text,re.I|re.ASCII) is None or block[6].text.lower()!='endsub':raise ValueError('postal function requires blank fallback,RETURN(local) and ENDSUB')
    args={'profile':PROFILE,'package':h[1].lower(),'function':{'name':f[1].lower(),'country':f[2].lower(),'code':f[3].lower(),'local':a[2].lower(),'format':a[3].lower(),'return_width':5},'source_lines':[s.line for s in block]}
    return Step('postal_library','functions',block[0].line,operations=[Operation('postal_library',block[0].line,args)])


def parse_data(block,source):
    from .parser import Kind
    from .plan import Step,Operation
    if len(block)!=6 or re.fullmatch(r"infile\s+cards\s+dlm\s*=\s*','\s+dsd",block[1].text,re.I|re.ASCII) is None or block[3].text.lower()!='cards' or block[-1].text.lower()!='run' or len(block[4].tokens)!=1 or block[4].tokens[0].kind is not Kind.DATA:raise ValueError('postal DATA requires INFILE CARDS DLM comma DSD and one physical payload')
    h=re.fullmatch(r'data\s+('+SOURCE_NAME+r')',block[0].text,re.I|re.ASCII);decl=re.fullmatch(r'input\s+(.+)',block[2].text,re.I|re.S|re.ASCII)
    if h is None or decl is None:raise ValueError('postal DATA declaration differs')
    rest=decl[1];columns=[]
    while rest.strip():
        m=re.match(r'\s*('+SOURCE_NAME+r')\s*:\s*\$\s*([0-9]{1,2})\.(?=\s|$)',rest,re.I|re.ASCII)
        if m is None:raise ValueError('postal INPUT requires colon-modified character declarations')
        columns.append({'name':m[1].lower(),'width':int(m[2])});rest=rest[m.end():]
    raw=block[4].tokens[0].text.replace('\r\n','\n');parts=raw.split('\n')
    if not parts or parts[0].strip(' ') or parts[-1]!='':raise ValueError('postal CSV starts on a new physical line')
    records=parts[1:-1];terminator=block[3].line+raw.count('\n')
    if source.splitlines()[terminator-1]!=';':raise ValueError('postal CSV requires a standalone unindented terminator')
    args={'profile':PROFILE,'columns':columns,'records':records,'source_lines':[block[0].line,block[1].line,block[2].line,block[3].line,terminator,block[-1].line]}
    return Step('postal_data',h[1].lower(),block[0].line,operations=[Operation('postal_data',block[0].line,args)])


def parse_report(block):
    from .plan import Step,Operation
    h=re.fullmatch(r'proc\s+report\s+data\s*=\s*('+SOURCE_NAME+r')\s+nowd',block[0].text,re.I|re.ASCII)
    if h is None or not 8<=len(block)<=9 or block[-1].text.lower()!='run':raise ValueError('postal REPORT requires the qualified computed block and RUN')
    cols=re.fullmatch(r'columns?\s+(.+)',block[1].text,re.I|re.ASCII);by=re.fullmatch(r'by\s+('+SOURCE_NAME+r')',block[2].text,re.I|re.ASCII)
    d=re.fullmatch(r'define\s+('+SOURCE_NAME+r')\s*/\s*computed\s+'+QUOTED,block[3].text,re.I|re.ASCII)
    if cols is None or by is None or d is None:raise ValueError('postal REPORT COLUMN,BY or COMPUTED declaration differs')
    computed=d[1].lower()
    if re.fullmatch(r'compute\s+'+computed+r'\s*/\s*char\s+length\s*=\s*5',block[4].text,re.I|re.ASCII) is None or block[6].text.lower()!='endcomp':raise ValueError('postal COMPUTE requires CHAR LENGTH=5 and ENDCOMP')
    c=re.fullmatch(computed+r'\s*=\s*('+SOURCE_NAME+r')\s*\(\s*('+SOURCE_NAME+r')\s*,\s*('+SOURCE_NAME+r')\s*\)',block[5].text,re.I|re.ASCII)
    if c is None:raise ValueError('postal COMPUTE requires one registered two-argument call')
    name=h[1].lower();changes=[parse_title(block[7]).operations[0].args['text']] if len(block)==9 else []
    args={'profile':PROFILE,'columns':cols[1].lower().split(),'by':by[1].lower(),'computed':computed,'label':_literal(d[2]),'function':c[1].lower(),'country':c[2].lower(),'code':c[3].lower(),'title_change':changes,'source_lines':[s.line for s in block]}
    return Step('postal_report',name,block[0].line,inputs=[name],operations=[Operation('postal_report',block[0].line,args)])


def source_steps(source,statements):
    from .parser import Kind
    from .plan import Step,Operation
    def code_text(text):
        text=re.sub(r'"(?:[^"]|"")*"',' ',text)
        return re.sub(r"'(?:[^']|'')*'",' ',text)
    if not any(re.search(r'\bzipstate\s*\(',code_text(s.text),re.I|re.ASCII) for s in statements if not any(t.kind is Kind.DATA for t in s.tokens)):return [],[],{},False
    steps=[];failures=[];routes={}
    for start,end,block in blocks(statements):
        text=block[0].text
        try:
            if not all(s.terminated and s.text.isascii() for s in block):raise ValueError('postal source requires complete ASCII statements')
            if text.lower()=='proc format':step=parse_format(block);route='postal-format'
            elif re.match(r'^proc\s+fcmp\b',text,re.I|re.ASCII):step=parse_library(block);route='postal-library'
            elif re.match(r'^options\s',text,re.I|re.ASCII):
                if len(block)!=1 or re.fullmatch(r'options\s+cmplib\s*=\s*work\.functions',text,re.I|re.ASCII) is None:raise ValueError('postal CMPLIB requires exactly work.functions')
                step=Step('postal_cmplib','functions',block[0].line,operations=[Operation('postal_cmplib',block[0].line,{'profile':PROFILE,'library':'work.functions','source_lines':[block[0].line]})]);route='postal-cmplib'
            elif re.match(r'^data\s',text,re.I|re.ASCII):step=parse_data(block,source);route='postal-input'
            elif re.match(r'^proc\s+sort\b',text,re.I|re.ASCII):
                h=re.fullmatch(r'proc\s+sort\s+data\s*=\s*('+SOURCE_NAME+r')',text,re.I|re.ASCII);b=re.fullmatch(r'by\s+('+SOURCE_NAME+r')',block[1].text,re.I|re.ASCII) if len(block)==3 else None
                if h is None or b is None or block[-1].text.lower()!='run':raise ValueError('postal SORT requires one owned DATA and one BY key')
                step=Step('postal_sort',h[1].lower(),block[0].line,operations=[Operation('postal_sort',block[0].line,{'profile':PROFILE,'key':b[1].lower(),'source_lines':[s.line for s in block]})]);route='postal-sort'
            elif re.match(r'^proc\s+report\b',text,re.I|re.ASCII):step=parse_report(block);route='postal-report'
            elif len(block)==1 and re.match(r'^title(?:\s|$)',text,re.I|re.ASCII):step=parse_title(block[0]);route='logical-title'
            else:raise ValueError('postal family contains an unqualified statement')
            steps.append(step)
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
    plan=Plan(steps=steps);plan.tickets.extend(Ticket(line,text,'postal-function',reason) for line,text,reason in failures)
    plan.matched.extend((construct,rule,statements[index].line) for index,(construct,rule) in routes.items())
    if not plan.tickets:
        try:validate_program(plan.to_dict())
        except (ValueError,TypeError,KeyError,RecursionError) as error:plan.tickets.append(Ticket(1,'postal function program','postal-function',str(error)))
    return plan
