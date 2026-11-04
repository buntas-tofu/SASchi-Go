"""Separate canonical DATE9 input and valid-width nested-date logical reports."""
from copy import deepcopy
import json
import re

from sas_semantics import SAS_CALENDAR_MIN_DAY as MIN_DAY, SAS_CALENDAR_MAX_DAY as MAX_DAY
from .character_input import STEP_KEYS, SOURCE_NAME, ordinary
from .date_foundations import sas_input_date9, sas_date_field
from .formatted_program import _blocks
from .mixed_reports import parse_title, execute_title, validate_step as validate_title

PROFILE = 'date-format-fields-v1'
REPORT_CONTRACT = 'ascii-date-fields-v1'
MARKERS = frozenset(('date_data', 'date_format', 'date_print'))
KINDS = MARKERS | {'report_title'}


def _containers(value):
    pending, active, done, selected = [(value, False)], set(), set(), False
    while pending:
        item, leaving = pending.pop()
        if type(item) not in (dict, list, tuple):
            continue
        identity = id(item)
        if leaving:
            active.remove(identity); done.add(identity); continue
        if identity in active:
            raise ValueError('date program refuses cyclic containers')
        if identity in done:
            continue
        active.add(identity); pending.append((item, True))
        if type(item) is dict:
            kind = item.get('kind')
            selected |= type(kind) is str and kind in MARKERS or item.get('profile') == PROFILE
            children = item.values()
        else:
            children = item
        pending.extend((child, False) for child in children if type(child) in (dict, list, tuple))
    if selected and len(done)>100000:
        raise ValueError('date program container bound exceeded')
    return selected


def _line(value):
    return type(value) is int and value > 0


def _text(value, maximum=128):
    if (type(value) is not str or not 1 <= len(value) <= maximum or value != value.strip(' ')
            or any(not 32 <= ord(c) <= 126 for c in value) or '%' in value or '&' in value):
        raise ValueError('date format literal requires bounded nonmacro printable ASCII without edge blanks')
    return value


def _format_name(value):
    return ordinary(value) and not value[-1].isdigit() and (value in ('cohort', 'benefit') or value.startswith('usr_'))


def _step(step):
    if (type(step) is not dict or set(step) != STEP_KEYS or type(step.get('kind')) is not str
            or step['kind'] not in MARKERS or not ordinary(step.get('name')) or not _line(step.get('line'))
            or type(step.get('inputs')) is not list or type(step.get('by')) is not list or step['by']
            or step.get('nodupkey') is not False or step.get('where') is not None
            or any(type(step.get(k)) is not dict or step[k] for k in ('retained','lengths','display_names'))
            or type(step.get('operations')) is not list or len(step['operations']) != 1):
        raise ValueError('date program requires exact Step defaults')
    op = step['operations'][0]
    if (type(op) is not dict or set(op) != {'kind','line','args'} or op.get('kind') != step['kind']
            or op.get('line') != step['line'] or not _line(op.get('line')) or type(op.get('args')) is not dict
            or op['args'].get('profile') != PROFILE):
        raise ValueError('date program requires one same-kind header-line operation')
    if step['inputs'] != ([step['name']] if step['kind'] == 'date_print' else []):
        raise ValueError('date program Step input shape differs')
    return op['args']


def _columns(columns):
    if type(columns) is not list or not 1 <= len(columns) <= 32:
        raise ValueError('DATE9 INPUT requires1..32 columns')
    schema, date_columns = {}, []
    for col in columns:
        if (type(col) is not dict or set(col) != {'name','read','length'} or not ordinary(col.get('name'))
                or col['name'] in schema or type(col.get('read')) is not str
                or col['read'] not in ('integer','character','date9') or type(col.get('length')) is not int
                or not (1 <= col['length'] <= 64 if col['read'] == 'character' else col['length'] == 8)):
            raise ValueError('DATE9 INPUT requires exact ordered typed declarations')
        schema[col['name']] = {'type':'character' if col['read']=='character' else 'number','length':col['length']}
        if col['read'] == 'date9': date_columns.append(col['name'])
    if not date_columns:
        raise ValueError('date DATA requires a genuine DATE9 column')
    return schema, date_columns


def _data(args, step):
    if set(args) != {'profile','columns','records','source_lines'}:
        raise ValueError('DATE9 DATA fields differ')
    schema, date_columns = _columns(args['columns'])
    records, lines = args['records'], args['source_lines']
    if (type(records) is not list or len(records)>1000 or type(lines) is not list or len(lines)!=6
            or not all(_line(n) for n in lines) or lines!=sorted(lines) or lines[0]!=step['line']
            or lines[4]!=lines[3]+len(records)+1 or lines[5]<=lines[4]):
        raise ValueError('DATE9 DATA requires bounded records and complete line provenance')
    rows = []
    for record in records:
        if (type(record) is not str or len(record)>80 or any(not 32<=ord(c)<=126 for c in record)
                or any(c in record for c in "'\";")):
            raise ValueError('DATE9 records require unquoted printable ASCII up to80 bytes')
        tokens = record.split()
        if len(tokens)!=len(schema):
            raise ValueError('DATE9 records require exactly one complete field set; FLOWOVER deferred')
        row = {}
        for col, token in zip(args['columns'],tokens,strict=True):
            if col['read']=='date9':
                value = sas_input_date9(token)
                value = None if value is None else float(value)
            elif col['read']=='character':
                if token=='.' or len(token)>col['length']:
                    raise ValueError('DATE9 character read refuses period or overwidth tokens')
                value = token.ljust(col['length'])
            else:
                if token=='.': value=None
                elif re.fullmatch(r'[+-]?[0-9]{1,10}',token,re.ASCII) and abs(int(token))<=2147483647:
                    value=float(int(token))
                else: raise ValueError('DATE9 numeric read requires a canonical bounded integer')
            row[col['name']] = value
        rows.append(row)
    return {'schema':schema,'rows':rows,'date_columns':date_columns}


def _ranges(args, step):
    if (set(args) != {'profile','ranges','source_lines'} or not _format_name(step['name'])
            or type(args['ranges']) is not list or not 1<=len(args['ranges'])<=32):
        raise ValueError('date VALUE requires a bounded local format definition')
    previous = MIN_DAY-1
    for item in args['ranges']:
        if (type(item) is not dict or set(item) != {'lower','upper','render'}
                or type(item.get('lower')) is not int or type(item.get('upper')) is not int
                or not MIN_DAY<=item['lower']<=item['upper']<=MAX_DAY or item['lower']!=previous+1
                or type(item.get('render')) is not dict):
            raise ValueError('date VALUE requires contiguous ordered inclusive calendar ranges')
        render=item['render']
        if render.get('kind')=='builtin' and set(render)=={'kind','name','width'}:
            sas_date_field(None,render['name'],render['width'])
        elif render.get('kind')=='literal' and set(render)=={'kind','text'}: _text(render['text'])
        else: raise ValueError('date VALUE requires a valid builtin or literal render')
        previous=item['upper']
    if previous!=MAX_DAY: raise ValueError('date VALUE ranges must cover the qualified calendar')
    _source_lines(args['source_lines'],step,3)
    return deepcopy(args['ranges'])


def _source_lines(lines, step, count):
    if (type(lines) is not list or len(lines)!=count or not all(_line(n) for n in lines)
            or lines!=sorted(lines) or lines[0]!=step['line']):
        raise ValueError('date program requires ordered complete source lines')


def validate_program(plan, catalog=None):
    selected=_containers(plan)
    if not selected: return None
    if (type(plan) is not dict or set(plan)!={'version','steps','tickets','matched'}
            or type(plan.get('version')) is not int or plan['version']!=2
            or type(plan.get('tickets')) is not list or plan['tickets']
            or type(plan.get('matched')) is not list or type(plan.get('steps')) is not list
            or not 1<=len(plan['steps'])<=64 or catalog is not None and (type(catalog) is not dict or catalog)):
        raise ValueError('date program requires complete version2 and an empty initial catalog')
    route_ids={'date-input':'DS-080','nested-date-format':'DS-081','date-print':'ST-025','logical-title':'ST-020'}
    for item in plan['matched']:
        if (type(item) not in (list,tuple) or len(item)!=3 or type(item[0]) is not str
                or item[0] not in route_ids or item[1]!=route_ids[item[0]] or not _line(item[2])):
            raise ValueError('date program matched routes require exact known triples')
    tables, formats, contexts = {}, {}, []
    counts={kind:0 for kind in KINDS}
    for step in plan['steps']:
        if type(step) is not dict or type(step.get('kind')) is not str or step['kind'] not in KINDS:
            raise ValueError('date family cannot mix unqualified Step families or hidden markers')
        kind=step['kind'];counts[kind]+=1
        if kind=='report_title': context=validate_title(step)
        else:
            args=_step(step)
            if kind=='date_data':
                if step['name'] in tables: raise ValueError('date DATA requires a fresh destination')
                context=_data(args,step);tables[step['name']]=context
            elif kind=='date_format':
                if step['name'] in formats: raise ValueError('date format cannot replace a definition')
                context=_ranges(args,step);formats[step['name']]=context
            else:
                if (set(args)!={'profile','format','columns','source_lines'} or step['name'] not in tables
                        or type(args['format']) is not str or args['format'] not in formats
                        or type(args['columns']) is not list or not 1<=len(args['columns'])<=32
                        or any(not ordinary(c) for c in args['columns'])
                        or len(set(args['columns']))!=len(args['columns'])
                        or any(c not in tables[step['name']]['date_columns'] for c in args['columns'])
                        or 'obs' in tables[step['name']]['schema']):
                    raise ValueError('date PRINT requires prior source, format and unique DATE9 bindings')
                _source_lines(args['source_lines'],step,3);context=deepcopy(args)
        contexts.append(context)
    if (not 1<=counts['date_data']<=8 or counts['date_format']>8 or counts['date_print']>2
            or counts['report_title']>32): raise ValueError('date program component bounds exceeded')
    return contexts


def _formatted(value, ranges):
    if value is None: return '.'
    for item in ranges:
        if item['lower']<=value<=item['upper']:
            render=item['render']
            return (sas_date_field(value,render['name'],render['width']).lstrip(' ')
                    if render['kind']=='builtin' else render['text'])
    raise ValueError('date VALUE dispatch outside validated calendar')


def validate_reports(reports):
    if (type(reports) is not dict or not 1<=len(reports)<=2
            or list(reports)!=['print_0'+str(i)+'.txt' for i in range(1,len(reports)+1)]):
        raise ValueError('date reports require one or two ordered print artifacts')
    for text in reports.values():
        if (type(text) is not str or not text.isascii() or not text.endswith('\n') or len(text)>417056
                or any(c!='\n' and not 32<=ord(c)<=126 for c in text)):
            raise ValueError('date report byte or text limits exceeded')
        lines=text[:-1].split('\n');offset=int(lines[0].startswith('TITLE: '))
        if (offset and not 7<=len(lines[0])<=135
                or not 1<=len(lines)-offset<=1001 or not lines[offset] or len(lines[offset])>1055
                or any(not row or len(row)>415 for row in lines[offset+1:])):
            raise ValueError('date report exceeds header,row or observation limits')
    return reports


def run_program(plan, catalog=None, *, trace=None):
    contexts=validate_program(plan,catalog)
    if contexts is None: raise ValueError('date executor requires its explicit family')
    tables,formats,reports,title={}, {}, {}, None
    for step,context in zip(plan['steps'],contexts,strict=True):
        kind=step['kind']
        if kind=='date_data':
            tables[step['name']]={key:deepcopy(context[key]) for key in ('schema','rows')}
            if trace is not None:
                for index in range(len(context['rows'])+1):
                    trace.append({'kind':'date_input','line':step['line'],'attempt':index+1,'complete':index<len(context['rows'])})
                    if index<len(context['rows']): trace.append({'kind':'date_output','observation':index+1})
        elif kind=='date_format': formats[step['name']]=context
        elif kind=='report_title': title=execute_title(step,trace=trace)
        else:
            table=tables[step['name']];lines=[] if title is None else ['TITLE: '+title]
            lines.append('obs '+' '.join(table['schema']))
            for index,row in enumerate(table['rows'],1):
                values=[]
                for name,spec in table['schema'].items():
                    value=row[name]
                    if name in context['columns']: text=json.dumps(_formatted(value,formats[context['format']]))
                    elif spec['type']=='character': text=json.dumps(value.rstrip(' '))
                    else: text='.' if value is None else str(int(value))
                    values.append(text)
                lines.append(str(index)+' '+' '.join(values))
            name='print_0'+str(len(reports)+1)+'.txt';reports[name]='\n'.join(lines)+'\n'
            validate_reports(reports)
            if trace is not None: trace.append({'kind':'date_report','name':name,'rows':len(table['rows'])})
    result={'datasets':deepcopy(tables),'log':[]}
    if reports: result['reports']=reports
    return result


def _literal(text):
    if len(text)<2 or text[0] not in "'\"" or text[-1]!=text[0]: raise ValueError('quoted literal required')
    quote=text[0];inner=text[1:-1]
    if quote in inner.replace(quote*2,''): raise ValueError('invalid literal quoting')
    return inner.replace(quote*2,quote)


def _date(text):
    if text.lower()=='low': return MIN_DAY
    if text.lower()=='high': return MAX_DAY
    match=re.fullmatch(r"('[0-9]{2}[A-Za-z]{3}[0-9]{4}'|\"[0-9]{2}[A-Za-z]{3}[0-9]{4}\")\s*[dD]",text,re.ASCII)
    if not match: raise ValueError('date literal requires four-digit canonical year; YEARCUTOFF deferred')
    return sas_input_date9(_literal(match[1]))


def _parse_data(block, source):
    from .parser import Kind
    from .plan import Step,Operation
    if len(block)!=6: raise ValueError('date DATA requires header,INFILE,INPUT,CARDS,payload,RUN only')
    header,infile,input_stmt,cards,payload,run=block
    name=re.fullmatch(r'data\s+('+SOURCE_NAME+r')',header.text,re.I|re.ASCII)
    if (name is None or infile.text.lower()!='infile cards' or cards.text.lower()!='cards' or run.text.lower()!='run'
            or not all(st.terminated for st in block) or len(payload.tokens)!=1 or payload.tokens[0].kind is not Kind.DATA):
        raise ValueError('date DATA requires explicit INFILE CARDS and complete physical payload')
    match=re.fullmatch(r'input\s+(.+)',input_stmt.text,re.I|re.S|re.ASCII)
    if match is None: raise ValueError('date DATA requires INPUT')
    pattern=re.compile(r'\s*('+SOURCE_NAME+r')(?:\s*:\s*(?:\$\s*([0-9]{1,2})\s*\.|(date9)\.))?(?=\s|$)',re.I|re.ASCII)
    position,columns=0,[];rest=match[1]
    while position<len(rest) and rest[position:].strip():
        item=pattern.match(rest,position)
        if item is None: raise ValueError('date INPUT permits bare integer,colon:$w.,colon:DATE9 only')
        columns.append({'name':item[1].lower(),'read':'character' if item[2] else 'date9' if item[3] else 'integer','length':int(item[2]) if item[2] else 8});position=item.end()
    raw=payload.tokens[0].text.replace('\r\n','\n');parts=raw.split('\n')
    if not parts or parts[0].strip(' ') or parts[-1]!='': raise ValueError('date records start on a new physical line')
    records=parts[1:-1];terminator=cards.line+raw.count('\n');physical=source.splitlines()
    if terminator>len(physical) or physical[terminator-1]!=';': raise ValueError('CARDS requires an unindented standalone semicolon')
    lines=[header.line,infile.line,input_stmt.line,cards.line,terminator,run.line]
    return Step('date_data',name[1].lower(),header.line,operations=[Operation('date_data',header.line,{'profile':PROFILE,'columns':columns,'records':records,'source_lines':lines})])


def _parse_format(block):
    from .plan import Step,Operation
    if len(block)!=3 or block[0].text.lower()!='proc format' or block[-1].text.lower()!='run':
        raise ValueError('date FORMAT requires one VALUE and explicit RUN')
    match=re.fullmatch(r'value\s+('+SOURCE_NAME+r')\s+(.+)',block[1].text,re.I|re.S|re.ASCII)
    if match is None: raise ValueError('date FORMAT requires one named VALUE')
    for builtin in re.finditer(r'\[(weekdate|worddate)([0-9]+)\.\]',match[2],re.I|re.ASCII):
        sas_date_field(None,builtin[1],int(builtin[2]))
    bound=r'(?:low|high|\x27[0-9]{2}[A-Za-z]{3}[0-9]{4}\x27\s*[dD]|"[0-9]{2}[A-Za-z]{3}[0-9]{4}"\s*[dD])'
    value=r'(?:\[(?:weekdate|worddate)[0-9]+\.\]|\x27(?:[^\x27]|\x27\x27)*\x27|"(?:[^"]|"")*")'
    pattern=re.compile(r'\s*('+bound+r')\s*-\s*('+bound+r')\s*=\s*('+value+r')(?=\s|$)',re.I|re.ASCII)
    position,ranges=0,[];rest=match[2]
    while position<len(rest) and rest[position:].strip():
        item=pattern.match(rest,position)
        if item is None: raise ValueError('date VALUE requires canonical inclusive ranges and valid nested/literal output')
        if item[1].lower()=='high' or item[2].lower()=='low':
            raise ValueError('date VALUE permits LOW only below and HIGH only above')
        builtin=re.fullmatch(r'\[(weekdate|worddate)([0-9]+)\.\]',item[3],re.I|re.ASCII)
        render={'kind':'builtin','name':builtin[1].lower(),'width':int(builtin[2])} if builtin else {'kind':'literal','text':_literal(item[3])}
        ranges.append({'lower':_date(item[1]),'upper':_date(item[2]),'render':render});position=item.end()
    return Step('date_format',match[1].lower(),block[0].line,operations=[Operation('date_format',block[0].line,{'profile':PROFILE,'ranges':ranges,'source_lines':[st.line for st in block]})])


def _parse_print(block):
    from .plan import Step,Operation
    if len(block)!=3 or block[-1].text.lower()!='run': raise ValueError('date PRINT requires DATA,FORMAT,RUN')
    header=re.fullmatch(r'proc\s+print\s+data\s*=\s*('+SOURCE_NAME+r')',block[0].text,re.I|re.ASCII)
    binding=re.fullmatch(r'format\s+(.+)\s+('+SOURCE_NAME+r')\.',block[1].text,re.I|re.ASCII)
    if header is None or binding is None: raise ValueError('date PRINT requires default listing and one FORMAT binding')
    name=header[1].lower();args={'profile':PROFILE,'format':binding[2].lower(),'columns':binding[1].lower().split(),'source_lines':[st.line for st in block]}
    return Step('date_print',name,block[0].line,inputs=[name],operations=[Operation('date_print',block[0].line,args)])


def source_steps(source, statements):
    blocks=list(_blocks(statements))
    selected=any(re.match(r'^data\s',block[0].text,re.I|re.ASCII) and any(
        re.match(r'^input\s',st.text,re.I|re.ASCII) and re.search(r':\s*date9\.',st.text,re.I|re.ASCII) for st in block) for _,_,block in blocks)
    if not selected: return [],[],{},False
    steps,failures,routes=[],[],{}
    from .parser import Kind
    for start,end,block in blocks:
        try:
            if not all(st.terminated for st in block): raise ValueError('date source requires explicit terminators')
            text=block[0].text
            if not text.isascii(): raise ValueError('date source declarations require ASCII')
            if re.match(r'^data\s',text,re.I|re.ASCII): step,route=_parse_data(block,source),('date-input','DS-080')
            elif re.match(r'^proc\s+format\b',text,re.I|re.ASCII): step,route=_parse_format(block),('nested-date-format','DS-081')
            elif re.match(r'^proc\s+print\b',text,re.I|re.ASCII): step,route=_parse_print(block),('date-print','ST-025')
            elif len(block)==1 and re.match(r'^title(?:\s|$)',text,re.I|re.ASCII): step,route=parse_title(block[0]),('logical-title','ST-020')
            else: raise ValueError('date family permits only its DATA,FORMAT,PRINT and literal TITLE')
            steps.append(step)
            for index in range(start,end):
                if not any(token.kind is Kind.DATA for token in statements[index].tokens): routes[index]=route
        except (ValueError,TypeError,KeyError,RecursionError) as error:
            failures.append((block[0].line,block[0].text,str(error)))
    return steps,failures,routes,True


def compile_program(source, legacy):
    from .parser import split_statements,ParseError
    from .plan import Plan,Ticket
    try: statements=split_statements(source)
    except ParseError: return legacy(source)
    steps,failures,routes,selected=source_steps(source,statements)
    if not selected: return legacy(source)
    plan=Plan(steps=steps)
    plan.tickets.extend(Ticket(line,text,'date-program',reason) for line,text,reason in failures)
    plan.matched.extend((construct,rule,statements[index].line) for index,(construct,rule) in routes.items())
    if not plan.tickets:
        try: validate_program(plan.to_dict())
        except (ValueError,TypeError,KeyError,RecursionError) as error: plan.tickets.append(Ticket(1,'date program','date-program',str(error)))
    return plan
