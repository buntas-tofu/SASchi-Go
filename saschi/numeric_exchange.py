"""DS-062/063 separately marked exact numeric lists and pure CSV export buffers."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import re

from sas_semantics import (sas_numeric_array_value, sas_numeric_array_add,
                           sas_numeric_array_sum, sas_multiply, sas_divide,
                           sas_sum_statement, sas_put_numeric_list, sas_put_literals,
                           sas_numeric_order)
from .parser import split_statements, Kind, ParseError
from .input_numeric import parse_infile, parse_terms as input_terms, decode
from .input_list import source_records
from .projection import dataset, declaration, selected_names, project_table, _validate_step

PROFILE = 'bounded-numeric-exchange-v1'
EXPORT_CONTRACT = 'ascii-lf-integer-csv-v1'
COMPARISON_CONTRACT = 'exact-basename-set-utf8-bytes-v1'
STEP_FIELDS = {'kind','name','line','inputs','by','operations','nodupkey','where','retained','lengths','display_names'}
NEW_KINDS = {'exchange_profile','exchange_input','file_select','put_named_list','sum_named_list'}
NAME = r'[a-z_][a-z0-9_]{0,31}'
RESERVED = {'_n_','_error_','_all_','_numeric_','_character_','_temporary_','_infile_','_file_','_ods_','_page_','_blankpage_','_null_'}
COMPARISONS = {'truth','=','eq','ne','^=','~=','<>','<','lt','<=','le','>','gt','>=','ge'}
LIST_FIELDS = {'terms','names'}
INPUT_FIELDS = {'terms','names','delimiter','firstobs','infile_line','records','data_line'}
DEVICE_NAMES = {'con','prn','aux','nul'} | {p+str(i) for p in ('com','lpt') for i in range(1,10)}
MAX_EVENTS = 1000000
MAX_RECORDS = 10000


def ordinary(name):
    return type(name) is str and name.isascii() and re.fullmatch(NAME,name,re.ASCII) is not None and name not in RESERVED


def destination(name):
    if (type(name) is not str or not name.isascii() or not 5<=len(name)<=64
            or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*\.csv',name,re.ASCII|re.I) is None
            or name[:-4].lower() in DEVICE_NAMES):
        raise ValueError('CSV destination requires one ordinary literal basename ending in .csv, without paths or devices')
    return name


def expand_terms(terms):
    if type(terms) is not list or not 1<=len(terms)<=64:
        raise ValueError('numeric lists require1..64 canonical terms')
    result=[]
    for term in terms:
        if type(term) is not str or re.fullmatch(NAME+r'(?:-'+NAME+r')?',term,re.ASCII) is None:
            raise ValueError('numeric lists require lowercase ordinary names or numbered ranges')
        if '-' not in term:
            expanded=[term]
        else:
            first,last=term.split('-');a=re.fullmatch(r'([a-z_][a-z0-9_]*?)([0-9]+)',first,re.ASCII);b=re.fullmatch(r'([a-z_][a-z0-9_]*?)([0-9]+)',last,re.ASCII)
            if (not a or not b or a[1]!=b[1] or len(a[2])>2 or len(b[2])>2
                    or a[2].startswith('0') or b[2].startswith('0')
                    or not 1<=int(a[2])<=int(b[2])<=64):
                raise ValueError('numeric ranges require matching complete prefixes and unpadded ascending suffixes1..64')
            if len(result)+int(b[2])-int(a[2])+1>64:
                raise ValueError('numeric list expansion exceeds64 names')
            expanded=[a[1]+str(i) for i in range(int(a[2]),int(b[2])+1)]
        if len(result)+len(expanded)>64 or any(not ordinary(n) or n in result for n in expanded):
            raise ValueError('numeric list expansion requires unique ordinary names without overlap')
        result.extend(expanded)
    return result


def parse_terms(text):
    if type(text) is not str or not text.isascii():
        raise ValueError('numeric list source requires ASCII before normalization')
    rest=text.strip().lower();terms=[]
    while rest:
        match=re.match('('+NAME+r')(?:\s*-\s*('+NAME+r'))?(?=\s|$)',rest,re.ASCII)
        if not match:raise ValueError('numeric list source must be consumed completely')
        terms.append(match[1]+('-'+match[2] if match[2] else ''))
        if len(terms)>64:raise ValueError('numeric list source exceeds64 terms')
        rest=rest[match.end():].strip()
    return terms,expand_terms(terms)


def structure(value):
    pending=[(value,0,frozenset())];count=0
    while pending:
        node,depth,ancestors=pending.pop();count+=1
        if count>20000 or depth>256:raise ValueError('numeric exchange portable structure exceeds bounded size/depth')
        if isinstance(node,(dict,list)):
            if id(node) in ancestors:raise ValueError('numeric exchange portable structure is cyclic')
            ancestry=ancestors|{id(node)}
            if isinstance(node,dict):
                if any(type(k) is not str for k in node):raise ValueError('numeric exchange keys must be strings')
                children=node.values()
            else:children=node
            pending.extend((child,depth+1,ancestry) for child in children)
        elif type(node) not in (str,int,float,bool,type(None)):
            raise ValueError('numeric exchange requires JSON scalar/container values')


def refuse_legacy(operations):
    pending=[operations];seen=set()
    while pending:
        node=pending.pop()
        if not isinstance(node,(dict,list)):continue
        if id(node) in seen:continue
        seen.add(id(node))
        if isinstance(node,dict):
            if type(node.get('kind')) is str and node['kind'] in NEW_KINDS:
                raise ValueError('numeric exchange operations require their separate exchange_data profile')
            pending.extend(node.values())
        else:pending.extend(node)


def render(values,comma=False):
    if comma:
        record=','.join(sas_put_numeric_list([v]).rstrip(' ') for v in values)
        if len(record)>64:raise ValueError('CSV output beyond64 bytes requires a separate record-width contract')
        return record
    return sas_put_numeric_list(values)


def export_manifest(exports):
    validate_exports(exports)
    return {name:{'sha256':hashlib.sha256(text.encode('ascii')).hexdigest(),
                  'bytes':len(text.encode('ascii')),'records':text.count('\n')}
            for name,text in exports.items()}


def validate_exports(exports):
    if type(exports) is not dict or not 1<=len(exports)<=1:
        raise ValueError('CSV exports require exactly one named artifact')
    for name,text in exports.items():
        destination(name)
        if (type(text) is not str or not text.isascii() or '\r' in text or '\0' in text
                or text and not text.endswith('\n') or text.count('\n')>MAX_RECORDS
                or any(c!='\n' and not 32<=ord(c)<=126 for c in text)
                or any(len(line)>64 for line in text.split('\n'))):
            raise ValueError('CSV exports require bounded printable ASCII LF records with a final newline')
    return exports


def read_expected_exports(path):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('expected exports contain a duplicate artifact name')
            result[key]=value
        return result
    raw=path.read_bytes()
    if len(raw)>1048576:raise ValueError('expected export manifest exceeds one MiB')
    try:value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('invalid expected export JSON constant')))
    except (UnicodeError,json.JSONDecodeError) as exc:raise ValueError('expected exports require valid JSON text') from exc
    if type(value) is not dict or len(value)!=1:raise ValueError('expected exports require one complete basename-to-text map')
    for name,text in value.items():
        destination(name)
        if type(text) is not str:raise ValueError('expected export contents must be text')
        try:text.encode('utf-8')
        except UnicodeError as exc:raise ValueError('expected export contents require valid UTF8 text') from exc
    return value,hashlib.sha256(raw).hexdigest()


def exports_equal(actual,expected):
    return (type(actual) is dict and type(expected) is dict and set(actual)==set(expected)
            and all(type(actual[n]) is str and type(expected[n]) is str and
                    actual[n].encode('utf-8')==expected[n].encode('utf-8') for n in actual))


def validate_step(step,version=2):
    structure(step)
    if (type(version) is not int or version!=2 or type(step) is not dict or set(step)!=STEP_FIELDS
            or step['kind']!='exchange_data' or not (ordinary(step['name']) or step['name']=='_null_')
            or type(step['line']) is not int or step['line']<1 or type(step['operations']) is not list
            or step['inputs']!=[] or type(step['inputs']) is not list or step['by']!=[]
            or type(step['by']) is not list or step['nodupkey'] is not False or step['where'] is not None
            or type(step['retained']) is not dict or step['lengths']!={} or type(step['lengths']) is not dict
            or step['display_names']!={} or type(step['display_names']) is not dict):
        raise ValueError('numeric exchange requires its exact version2 exchange_data Step shape')
    roots=step['operations']
    if (not roots or roots[0]!={'kind':'exchange_profile','line':step['line'],'args':{'name':PROFILE}}
            or type(roots[0]['line']) is not int):
        raise ValueError('numeric exchange requires its first explicit DATA-line marker')
    schema={};input_op=None;file_op=None;puts=[];selection=None;count=0;nodes=0;has_range=False;explicit_output=False
    for name,value in step['retained'].items():
        if not ordinary(name) or type(value) is not dict or set(value)!={'kind','value'} or value['kind'] not in ('number','missing'):
            raise ValueError('numeric exchange RETAIN needs ordinary literal numeric initializers')
        if (value['kind']=='missing') != (value['value'] is None):raise ValueError('invalid numeric/missing initializer encoding')
        sas_numeric_array_value(value['value'])
    def declared(name):
        if not ordinary(name):raise ValueError('numeric exchange requires normalized ordinary numeric names')
        schema.setdefault(name,'number')
        if len(schema)>64:raise ValueError('numeric exchange exceeds64 PDV columns')
    def list_args(args):
        nonlocal has_range
        if type(args) is not dict or set(args)!=LIST_FIELDS or args['names']!=expand_terms(args['terms']):
            raise ValueError('numeric exchange list names must equal independently expanded canonical terms')
        if any(name not in schema for name in args['names']):raise ValueError('numeric list names require preceding numeric descriptors')
        has_range |= any('-' in term for term in args['terms'])
    def expr(value,depth=1,allow_list=False):
        nonlocal nodes
        nodes+=1
        if nodes>128 or depth>32 or type(value) is not dict:raise ValueError('numeric exchange expressions exceed128 nodes or32 levels')
        kind=value.get('kind')
        if kind in ('number','missing','variable','automatic'):
            if set(value)!={'kind','value'}:raise ValueError('numeric exchange scalar shape is invalid')
            if kind=='missing':
                if value['value'] is not None:raise ValueError('ordinary missing requires None')
            elif kind=='number':
                if value['value'] is None:raise ValueError('numeric literal requires a value')
                sas_numeric_array_value(value['value'])
            elif kind=='automatic':
                if value['value']!='_n_':raise ValueError('numeric exchange supports only automatic _N_')
            elif not ordinary(value['value']) or value['value'] not in schema:
                raise ValueError('numeric exchange references require preceding numeric descriptors')
            return (True,sas_numeric_array_value(value['value'])) if kind in ('number','missing') else (False,None)
        elif kind=='sum_named_list':
            if not allow_list or depth!=1:raise ValueError('SUM OF numeric lists require a complete assignment value')
            list_args({k:v for k,v in value.items() if k!='kind'})
            return False,None
        elif kind=='arithmetic':
            if set(value)!={'kind','op','left','right'} or value['op'] not in ('+','-','*','/'):
                raise ValueError('numeric exchange requires exact ordinary arithmetic')
            left=expr(value['left'],depth+1);right=expr(value['right'],depth+1)
            if value['op']=='/' and right[0] and right[1]==0:
                raise ValueError('numeric exchange static division by zero')
            if left[0] and right[0]:
                return True,evaluate(value,{})
            return False,None
        else:raise ValueError('expression is outside numeric exchange scope')
    def test(value):
        if type(value) is not dict or type(value.get('op')) is not str or value.get('op') not in COMPARISONS or set(value)!=({'left','op'} if value.get('op')=='truth' else {'left','op','right'}):
            raise ValueError('numeric exchange predicate shape is invalid')
        expr(value['left'])
        if value['op']!='truth':expr(value['right'])
    def operation(op,depth=0):
        nonlocal input_op,file_op,count,explicit_output
        count+=1
        if count>1024 or depth>32 or type(op) is not dict or set(op)!={'kind','line','args'} or type(op.get('line')) is not int or op['line']<step['line'] or type(op['args']) is not dict:
            raise ValueError('numeric exchange requires bounded exact operations with source lines')
        kind,args=op['kind'],op['args']
        if kind=='declare':
            if set(args)!={'name','spec'} or args['spec']!='number' or depth:raise ValueError('numeric exchange declarations must be top-level numeric descriptors')
            declared(args['name'])
        elif kind=='file_select':
            if depth or file_op is not None or input_op is not None or puts or set(args)!={'name','delimiter'} or args['delimiter']!=',':
                raise ValueError('CSV FILE must be one top-level prefix before INPUT and PUT')
            destination(args['name']);file_op=op
        elif kind=='exchange_input':
            if depth or input_op is not None or puts or set(args)!=INPUT_FIELDS or args['names']!=expand_terms(args['terms']) or not 1<=len(args['names'])<=32:
                raise ValueError('numeric exchange INPUT requires one top-level bounded source before PUT')
            if type(args['data_line']) is not int or args['data_line']<=op['line']:
                raise ValueError('numeric exchange inline data must follow INPUT')
            if args['delimiter']==',':
                if type(args['infile_line']) is not int or not step['line']<=args['infile_line']<=op['line']:raise ValueError('comma INPUT requires preceding INFILE metadata')
            elif args['delimiter']!=' ' or args['firstobs']!=1 or args['infile_line'] is not None:
                raise ValueError('space INPUT excludes INFILE metadata')
            for name in args['names']:declared(name)
            input_op=op
        elif kind in ('assign','sum_statement'):
            if set(args)!={'name','value'}:raise ValueError('numeric exchange assignment has unexpected fields')
            declared(args['name']);expr(args['value'],allow_list=kind=='assign')
            if kind=='sum_statement' and args['name'] not in step['retained']:raise ValueError('sum target needs explicit retained metadata')
        elif kind=='put_named_list':
            list_args(args);render([None]*len(args['names']),file_op is not None);puts.append(op)
        elif kind=='put_literal':
            if set(args)!={'literals'}:raise ValueError('numeric exchange literal PUT has unexpected fields')
            sas_put_literals(args['literals']);puts.append(op)
        elif kind=='if':
            if set(args) not in ({'condition','operation'},{'condition','operation','otherwise'}):raise ValueError('numeric exchange IF has unexpected fields')
            test(args['condition']);operation(args['operation'],depth+1)
            if 'otherwise' in args:operation(args['otherwise'],depth+1)
        elif kind=='subset':
            if depth or set(args)!={'condition'}:raise ValueError('numeric exchange subsetting IF must be top-level')
            test(args['condition'])
        elif kind=='output':
            if set(args)!={'target'} or args['target'] not in (None,step['name']) or step['name']=='_null_':raise ValueError('numeric exchange OUTPUT requires its named DATA destination')
            explicit_output=True
        elif kind=='projection':
            if depth:raise ValueError('numeric exchange projection must be top-level')
        else:raise ValueError('operation is outside numeric exchange scope')
    for op in roots[1:]:operation(op)
    if not file_op and not has_range:raise ValueError('numeric exchange marker requires actual FILE or numbered SUM/PUT range syntax')
    if file_op:
        file_position=next(i for i,op in enumerate(roots) if op is file_op)
        if any(op['kind'] not in ('declare','projection') for op in roots[1:file_position]):
            raise ValueError('CSV FILE must precede every executable action')
    if input_op:
        position=next(i for i,op in enumerate(roots) if op is input_op)
        if any(op['kind'] not in ('declare','file_select','projection') for op in roots[1:position]):raise ValueError('numeric exchange INPUT must precede calculations and conditions')
        if any(op['line']>=input_op['args']['data_line'] for op in _walk(roots)):raise ValueError('numeric exchange code must precede opaque inline records')
        a=input_op['args'];rows=decode(a['records'],len(a['names']),a['delimiter'],a['firstobs'])
        for row in rows:
            for value in row:sas_numeric_array_value(value)
    else:rows=[[]]
    if set(step['retained'])-set(schema):raise ValueError('numeric exchange retained metadata requires a declared target')
    shadow=deepcopy(step);shadow['kind']='data'
    incoming,selection=_validate_step(shadow,version,prefix=1)
    if incoming:raise ValueError('numeric exchange does not admit input selection without SET')
    selected_names(schema,selection)
    return {'schema':schema,'rows':rows,'input':input_op,'file':file_op,'selection':selection,'explicit_output':explicit_output,'has_range':has_range}


def _walk(ops):
    for op in ops:
        yield op
        if op['kind']=='if':
            yield from _walk([op['args']['operation']])
            if 'otherwise' in op['args']:yield from _walk([op['args']['otherwise']])


def evaluate(expr,row):
    kind=expr['kind']
    if kind in ('number','missing'):return sas_numeric_array_value(expr['value'])
    if kind in ('variable','automatic'):return sas_numeric_array_value(row.get(expr['value']))
    if kind=='sum_named_list':return sas_numeric_array_sum([row[n] for n in expr['names']])
    left,right=evaluate(expr['left'],row),evaluate(expr['right'],row)
    if expr['op'] in ('+','-'):return sas_numeric_array_add(left,right,expr['op']=='-')
    return sas_numeric_array_value(sas_multiply(left,right) if expr['op']=='*' else sas_divide(left,right))


def condition(test,row):
    left=evaluate(test['left'],row);op=test['op']
    if op=='truth':return left is not None and left!=0
    right=evaluate(test['right'],row);a,b=sas_numeric_order(left),sas_numeric_order(right)
    if op in ('=','eq'):return a==b
    if op in ('ne','^=','~=','<>'):return a!=b
    if op in ('<','lt'):return a<b
    if op in ('>','gt'):return a>b
    if op in ('<=','le'):return a<=b
    return a>=b


def execute_step(step,version=2,trace=None):
    info=validate_step(step,version);schema=info['schema'];snapshots=[];logs=[];records=[];events=0
    retained={n:sas_numeric_array_value(v['value']) for n,v in step['retained'].items()}
    exported=info['file']['args']['name'] if info['file'] else None
    def action(op,row):
        nonlocal events
        events+=1
        if events>MAX_EVENTS:raise ValueError('numeric exchange exceeds1000000 step events')
        kind,args=op['kind'],op['args']
        if trace is not None:
            trace.append({'kind':kind,'line':op['line'],'iteration':int(row['_n_'])})
        if kind in ('declare','file_select','exchange_input','projection'):return True
        if kind=='assign':row[args['name']]=evaluate(args['value'],row)
        elif kind=='sum_statement':row[args['name']]=sas_numeric_array_value(sas_sum_statement(row[args['name']],evaluate(args['value'],row)))
        elif kind=='if':
            child=args['operation'] if condition(args['condition'],row) else args.get('otherwise')
            if child:return action(child,row)
        elif kind=='subset':return condition(args['condition'],row)
        elif kind=='output':
            if len(snapshots)>=MAX_RECORDS:raise ValueError('numeric exchange exceeds10000 output observations')
            snapshots.append({n:row[n] for n in schema})
        elif kind in ('put_named_list','put_literal'):
            text=render([row[n] for n in args['names']],exported is not None) if kind=='put_named_list' else sas_put_literals(args['literals'])
            target=records if exported is not None else logs
            if len(target)>=MAX_RECORDS:raise ValueError('numeric exchange exceeds10000 emitted records')
            target.append(text)
        return True
    roots=step['operations'][1:]
    source_position=next((i for i,op in enumerate(roots) if op is info['input']),None)
    attempts=len(info['rows'])+1 if info['input'] else 1
    for offset in range(attempts):
        row={n:None for n in schema};row.update(retained);row['_n_']=float(offset+1)
        if info['input']:
            for op in roots[:source_position]:
                action(op,row)
            action(info['input'],row)
            complete=offset<len(info['rows'])
            if trace is not None:
                trace[-1]['complete']=complete
            if not complete:
                break
            row.update(zip(info['input']['args']['names'],info['rows'][offset]))
            actions=roots[source_position+1:]
        else:
            actions=roots
        kept=True
        for op in actions:
            if not action(op,row):kept=False;break
        for n in retained:retained[n]=row[n]
        if kept and not info['explicit_output'] and step['name']!='_null_':
            if len(snapshots)>=MAX_RECORDS:raise ValueError('numeric exchange exceeds10000 output observations')
            snapshots.append({n:row[n] for n in schema})
    table=None if step['name']=='_null_' else project_table({'schema':schema,'rows':snapshots},info['selection'])
    exports=None if exported is None else {exported:''.join(record+'\n' for record in records)}
    if exports is not None:validate_exports(exports)
    return table,logs,exports


def _trigger(statement):
    if any(t.kind is Kind.DATA for t in statement.tokens):return False
    text=re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"",' ',statement.text)
    return bool(re.match(r'^file\b(?!\s*=)',text,re.I|re.ASCII) or
                re.search(r'\bsum\s*\(\s*of\s+[^;()]*[a-z_][a-z0-9_]*\s*-\s*[a-z_]',text,re.I|re.ASCII) or
                re.search(r'\bput\s+[^;]*[a-z_][a-z0-9_]*\s*-\s*[a-z_]',text,re.I|re.ASCII))


def parse_block(statements):
    from .plan import Step,Operation,expression,predicate,atom
    if not statements or statements[-1].text.lower()!='run' or not statements[-1].terminated:raise ValueError('numeric exchange requires explicit final RUN')
    for st in statements:
        if not st.terminated:raise ValueError('numeric exchange statements require terminators')
        if any(t.kind is Kind.DATA for t in st.tokens):continue
        if len(st.text)>4096 or any(t.kind is not Kind.STRING and not t.text.isascii() for t in st.tokens):raise ValueError('numeric exchange source requires bounded ASCII code')
        unquoted=re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"",' ',st.text);depth=0
        if len(re.findall(r'[+*/-]|[A-Za-z_][A-Za-z0-9_]*\s*\(',unquoted,re.ASCII))>128:raise ValueError('numeric exchange source exceeds128 arithmetic/call markers')
        for char in unquoted:
            depth+=(char=='(')-(char==')')
            if depth>32:raise ValueError('numeric exchange source exceeds32 parenthesis levels')
    name,selector=dataset(statements[0].text,'data');step=Step('exchange_data',name,statements[0].line)
    ops=[{'kind':'exchange_profile','line':step.line,'args':{'name':PROFILE}}]
    if selector:ops.append({'kind':'projection','line':step.line,'args':selector})
    infile=None;input_op=None;data_marker=False;data_seen=False;position=1;seen_action=False
    def make(kind,line,args):return {'kind':kind,'line':line,'args':args}
    def value(text):
        match=re.fullmatch(r'sum\s*\(\s*of\s+(.+)\)',text,re.I|re.ASCII)
        if match:
            terms,names=parse_terms(match[1]);return {'kind':'sum_named_list','terms':terms,'names':names}
        parsed=expression(text)
        if parsed is None:raise ValueError('unsupported numeric exchange expression')
        return parsed
    def one(text,line,branch=False,depth=0):
        nonlocal position,seen_action,input_op,infile
        if depth>32:raise ValueError('numeric exchange source exceeds32 IF levels')
        conditional=re.fullmatch(r'if\s+(.+?)\s+then\s+(.+)',text,re.I|re.ASCII)
        if conditional:
            seen_action=True;test=predicate(conditional[1])
            if test is None:raise ValueError('unsupported numeric exchange IF predicate')
            args={'condition':test,'operation':one(conditional[2],line,True,depth+1)}
            if position<len(statements)-1:
                match=re.fullmatch(r'else\s+(.+)',statements[position].text,re.I|re.ASCII)
                if match:
                    other=statements[position];position+=1;args['otherwise']=one(match[1],other.line,True,depth+1)
            return make('if',line,args)
        if re.match(r'^file\s+',text,re.I|re.ASCII):
            if branch:raise ValueError('numeric exchange FILE must be unconditional')
            match=re.fullmatch(r'''file\s+(['"])([^'"]+)\1\s+dlm\s*=\s*(['"]),\3''',text,re.I|re.ASCII)
            if not match:raise ValueError('CSV FILE requires one literal basename and comma DLM only')
            return make('file_select',line,{'name':destination(match[2]),'delimiter':','})
        if re.match(r'^input\s+',text,re.I|re.ASCII):
            if branch or seen_action or input_op is not None:raise ValueError('numeric exchange INPUT must be the first calculation source')
            terms,names=input_terms(text.split(None,1)[1]);config=infile or {'delimiter':' ','firstobs':1,'infile_line':None}
            input_op=make('exchange_input',line,{'terms':terms,'names':names,**config});return input_op
        retain=re.fullmatch(r'retain\s+('+NAME+r')\s+(.+)',text,re.I|re.ASCII)
        if retain:
            if branch or seen_action:raise ValueError('numeric exchange RETAIN must be a top-level prefix')
            target=retain[1].lower();initial=atom(retain[2])
            if target in step.retained or initial is None or initial['kind'] not in ('number','missing'):raise ValueError('numeric exchange RETAIN requires a unique literal initializer')
            step.retained[target]=initial;return make('declare',line,{'name':target,'spec':'number'})
        if re.match(r'^(?:keep|drop)\s+',text,re.I|re.ASCII):
            if branch:raise ValueError('numeric exchange projection must be top-level')
            return make('projection',line,declaration(text))
        seen_action=True
        if re.match(r'^put\s',text,re.I|re.ASCII):
            tokens=split_statements(text+';')[0].tokens[1:]
            if tokens and all(t.kind is Kind.STRING for t in tokens):return make('put_literal',line,{'literals':[t.text for t in tokens]})
            terms,names=parse_terms(text.split(None,1)[1]);return make('put_named_list',line,{'terms':terms,'names':names})
        if text.lower()=='output' or re.fullmatch(r'output\s+'+NAME,text,re.I|re.ASCII):return make('output',line,{'target':None if text.lower()=='output' else text.split()[1].lower()})
        subset=re.fullmatch(r'if\s+(.+)',text,re.I|re.ASCII)
        if subset:
            if branch:raise ValueError('numeric exchange subset IF must be top-level')
            test=predicate(subset[1])
            if test is None:raise ValueError('unsupported numeric exchange subset predicate')
            return make('subset',line,{'condition':test})
        assign=re.fullmatch('('+NAME+r')\s*=\s*(.+)',text,re.I|re.ASCII);summation=re.fullmatch('('+NAME+r')\s*\+\s*(.+)',text,re.I|re.ASCII)
        if assign or summation:
            match=assign or summation;target=match[1].lower()
            if summation:step.retained.setdefault(target,{'kind':'number','value':0.0})
            return make('assign' if assign else 'sum_statement',line,{'name':target,'value':value(match[2])})
        raise ValueError('statement is outside bounded numeric exchange: '+text)
    while position<len(statements)-1:
        st=statements[position];position+=1
        if any(t.kind is Kind.DATA for t in st.tokens):
            if not data_marker or data_seen or input_op is None:raise ValueError('numeric exchange inline data requires one preceding INPUT and marker')
            raw,=[t for t in st.tokens if t.kind is Kind.DATA];input_op['args'].update(records=source_records(raw.text),data_line=raw.line+1);data_seen=True;continue
        if data_seen:raise ValueError('numeric exchange code cannot follow opaque data before RUN')
        if st.text.lower() in ('datalines','cards'):
            if input_op is None or data_marker:raise ValueError('numeric exchange inline marker requires one INPUT')
            data_marker=True;continue
        if data_marker:raise ValueError('numeric exchange marker must be followed by opaque data')
        if re.match(r'^infile\s+',st.text,re.I|re.ASCII):
            if infile or input_op or seen_action:raise ValueError('numeric exchange INFILE must be a unique prefix before INPUT')
            infile={**parse_infile(st.text),'infile_line':st.line};continue
        ops.append(one(st.text,st.line))
    if input_op is not None and not data_seen or infile and input_op is None:raise ValueError('numeric exchange INPUT requires one complete inline source')
    step.operations=[Operation(**op) for op in ops];validate_step(asdict(step));return step


def compile_program(source,legacy):
    from .plan import Plan,Ticket
    try:statements=split_statements(source)
    except ParseError:return None
    blocks=[];position=0
    while position<len(statements):
        st=statements[position]
        if not re.match(r'^data\s',st.text,re.I|re.ASCII):position+=1;continue
        end=position+1
        while end<len(statements) and statements[end].text.lower()!='run':
            if re.match(r'^(?:data|proc)\s',statements[end].text,re.I|re.ASCII):break
            end+=1
        limit=end+1 if end<len(statements) and statements[end].text.lower()=='run' else end
        block=statements[position:limit]
        if any(_trigger(s) for s in block[1:]):
            start=st.tokens[0].start;stop=statements[limit].tokens[0].start if limit<len(statements) else len(source)
            if start is None or stop is None:return None
            blocks.append((start,stop,block))
        position=max(position+1,limit)
    if not blocks:return None
    combined=Plan();cursor=0
    def prior(start,stop):
        if not source[start:stop].strip():return
        result=legacy('\n'*source[:start].count('\n')+source[start:stop]);combined.steps.extend(result.steps);combined.tickets.extend(result.tickets);combined.matched.extend(result.matched)
    for start,stop,block in blocks:
        prior(cursor,start)
        try:
            step=parse_block(block);combined.steps.append(step);info=validate_step(asdict(step))
            if info['has_range']:combined.matched.append(('numeric-ranges','DS-062',step.line))
            if info['file']:combined.matched.append(('csv-export','DS-063',info['file']['line']))
        except (ValueError,RecursionError,KeyError,TypeError) as exc:combined.tickets.append(Ticket(block[0].line,block[0].text,'numeric-exchange',str(exc)))
        cursor=stop
    prior(cursor,len(source))
    files=[op for step in combined.steps if step.kind=='exchange_data' for op in _walk([asdict(o) for o in step.operations]) if op['kind']=='file_select']
    if len(files)>1:combined.tickets.append(Ticket(files[1]['line'],'FILE','csv-export','one export destination per program is the bounded profile'))
    return combined
