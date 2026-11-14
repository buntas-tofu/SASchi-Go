"""Separately qualified typed DATA actions, retained state and sorted BY flags."""
from copy import deepcopy
from dataclasses import asdict
import re

import sas_semantics as sem
from . import function_expressions as ex
from .values import normalize_catalog,coerce,column_type,descriptor

PROFILE='stateful-expressions-v1'
STAGE=4
COHORT=frozenset(('upcase','compbl','strip','dequote','notalnum','lengthn','n','abs','max','ifc'))
STEP_FIELDS=ex.STEP_FIELDS
NAME=ex.NAME


def ordinary(name):
    ex.ordinary(name)
    if name=='_null_':raise ValueError('stateful expressions require a named destination')


def claimed(plan):
    """Find markers or unmarked state nodes without a recursive legacy walk."""
    pending=[plan];seen=set();novel=False
    while pending:
        node=pending.pop()
        if not isinstance(node,(dict,list,tuple)) or id(node) in seen:continue
        seen.add(id(node))
        if isinstance(node,dict):
            kind=node.get('kind')
            if kind=='stateful_profile':
                novel=True
                if type(node.get('args')) is dict and node['args'].get('profile')==PROFILE:return True
            if type(kind) is str and kind.startswith('state_'):novel=True
            pending.extend(node.values())
        else:pending.extend(node)
    if novel:raise ValueError('stateful operations require their own profile marker')
    return False


def walk_ops(operations):
    pending=list(reversed(operations))
    while pending:
        op=pending.pop();yield op
        if type(op) is dict and type(op.get('args')) is dict:
            args=op['args']
            if op.get('kind')=='if':
                if 'otherwise' in args:pending.append(args['otherwise'])
                if 'operation' in args:pending.append(args['operation'])
            elif op.get('kind')=='state_group' and type(args.get('body')) is list:
                pending.extend(reversed(args['body']))


def automatic_view(node,*,by=None,reserved=()):
    """Lower temporary flags to collision-free numeric proxies for old helpers."""
    pending=[node];used=set(reserved);automatics=[]
    while pending:
        value=pending.pop()
        if type(value) is dict:
            if value.get('kind')=='state_auto':
                if STAGE<4 or set(value)!={'kind','flag','key'} or type(value['flag']) is not str or value['flag'] not in ('first','last'):raise ValueError('stateful automatic fields are exact')
                ordinary(value['key'])
                if by is not None and by!=[value['key']]:raise ValueError('stateful automatic requires its declared BY key')
                automatics.append((value['flag'],value['key']))
            elif value.get('kind')=='variable':
                ex.ordinary(value.get('value'));used.add(value['value'])
            pending.extend(value.values())
        elif type(value) in (list,tuple):pending.extend(value)
    proxies={}
    for flag in automatics:
        if flag in proxies:continue
        index=0
        while '_sx'+str(index) in used:index+=1
        name='_sx'+str(index);used.add(name);proxies[flag]=name
    if not proxies:return node,{}
    def lower(value):
        if type(value) is dict:
            if value.get('kind')=='state_auto':return {'kind':'variable','value':proxies[(value['flag'],value['key'])]}
            return {key:lower(child) for key,child in value.items()}
        if type(value) is list:return [lower(child) for child in value]
        if type(value) is tuple:return tuple(lower(child) for child in value)
        return value
    return lower(node),proxies


def expression(node,schema=None,*,condition=False,by=None):
    ex.preflight(node)
    pending=[node]
    while pending:
        value=pending.pop()
        if type(value) is dict:
            if value.get('kind')=='call' and (type(value.get('name')) is not str or value['name'] not in COHORT):
                raise ValueError('function is outside the ten-name stateful cohort')
            pending.extend(value.values())
        elif type(value) in (list,tuple):pending.extend(value)
    lowered,proxies=automatic_view(node,by=by,reserved=schema or ())
    types=None if schema is None else {**schema,**{name:'number' for name in proxies.values()}}
    info=ex.describe(lowered,types,context='condition' if condition else 'value')
    if condition and info[0] not in (None,'number'):raise ValueError('stateful predicates require numeric truth')
    return info


class Parser(ex.Parser):
    """Recognize only FIRST/LAST ordinary keys while preserving inline tails."""
    def __init__(self,text):
        super().__init__(text);original=self.tokens;self.automatics={};self.tokens=[];index=0
        used={value.lower() for kind,value in original if kind==3}
        while index<len(original):
            kind,value=original[index]
            if STAGE>=4 and kind==3 and value.lower() in ('first','last') and index+2<len(original) and original[index+1][1]=='.' and original[index+2][0]==3:
                key=original[index+2][1].lower();ordinary(key);number=0
                while '_sx'+str(number) in used:number+=1
                proxy='_sx'+str(number);used.add(proxy);self.automatics[proxy]={'kind':'state_auto','flag':value.lower(),'key':key}
                self.tokens.append((3,proxy));index+=3
            else:self.tokens.append((kind,value));index+=1
    def expression(self,minimum=0,depth=0):
        node=super().expression(minimum,depth)
        pending=[node]
        while pending:
            value=pending.pop()
            if type(value) is dict:
                if value.get('kind')=='variable' and value['value'] in self.automatics:
                    automatic=deepcopy(self.automatics[value['value']]);value.clear();value.update(automatic)
                else:pending.extend(value.values())
            elif type(value) is list:pending.extend(value)
        return node
    def tail(self):
        return ' '.join(self.automatics[value]['flag']+'.'+self.automatics[value]['key'] if kind==3 and value in self.automatics else value for kind,value in self.tokens[self.index:])


def parse_expression(text):
    value=Parser(text).complete();expression(value);return value


def value_of(node,row,flags):
    lowered,proxies=automatic_view(node,reserved=row)
    return ex.value_of(lowered,row if not proxies else {**row,**{name:flags[flag] for flag,name in proxies.items()}})


def genuine(step):
    ops=list(walk_ops(step['operations']));calls=False;characters=False;automatic=False
    pending=[step['operations']]
    while pending:
        node=pending.pop()
        if type(node) is dict:
            calls=calls or node.get('kind')=='call'
            characters=characters or node.get('kind')=='character'
            automatic=automatic or node.get('kind')=='state_auto'
            pending.extend(node.values())
        elif type(node) in (list,tuple):pending.extend(node)
    return (any(op.get('kind')=='state_group' for op in ops) and (calls or characters or bool(step['lengths'])) or
            (any(op.get('kind')=='state_output' for op in ops) or bool(step['retained'])) and calls or
            bool(step['by']) and (calls or automatic))


def validate_step(step,*,source=False,max_stage=None):
    stage=STAGE if max_stage is None else max_stage
    if type(stage) is not int or not 1<=stage<=STAGE:raise ValueError('invalid stateful qualification stage')
    ex.preflight(step)
    if type(step) is not dict or set(step)!=STEP_FIELDS or step['kind']!='data':raise ValueError('stateful profile requires exact ordinary DATA step fields')
    ordinary(step['name'])
    if type(step['line']) is not int or step['line']<1:raise ValueError('stateful source line is invalid')
    if type(step['inputs']) is not list or len(step['inputs'])!=1:raise ValueError('stateful profile requires exactly one driving SET')
    for name in step['inputs']:ordinary(name)
    if type(step['by']) is not list or len(step['by'])>1 or stage<4 and step['by']:raise ValueError('BY requires its qualified one-key stage')
    for name in step['by']:ordinary(name)
    if type(step['retained']) is not dict or len(step['retained'])>16 or stage<2 and step['retained']:raise ValueError('numeric RETAIN exceeds its qualification stage or name budget')
    for name,value in step['retained'].items():
        ordinary(name)
        if not ex.primitive(value) or value['kind'] not in ('number','missing'):raise ValueError('numeric RETAIN requires an exact literal initializer')
        expression(value);sem.sas_stateful_expression_state(value['value'])
    if step['where'] is not None or step['nodupkey'] is not False:raise ValueError('stateful filtering/sorting requires separate composition')
    if type(step['lengths']) is not dict or type(step['display_names']) is not dict or type(step['operations']) is not list:raise ValueError('stateful descriptor/operation fields are exact')
    for name,width in step['lengths'].items():
        ordinary(name)
        if type(width) is not int or not 1<=width<=32767:raise ValueError('stateful character width is outside bounds')
    for name,value in step['display_names'].items():
        ordinary(name)
        if type(value) is not str or not re.fullmatch(NAME,value,re.ASCII) or value.lower()!=name:raise ValueError('stateful display names must match declarations')
    ops=list(walk_ops(step['operations']))
    if not 1<=len(ops)<=256:raise ValueError('stateful operation budget exceeded')
    pending=list(reversed([(op,0) for op in step['operations']]));markers=[];reads=0;declarations={};sums=set()
    while pending:
        op,depth=pending.pop()
        if type(op) is not dict or set(op)!={'kind','line','args'} or type(op['kind']) is not str or type(op['line']) is not int or op['line']<1 or type(op['args']) is not dict:raise ValueError('stateful operation fields are exact')
        kind,args=op['kind'],op['args']
        if kind=='stateful_profile':
            markers.append(op)
            if args!={'profile':PROFILE}:raise ValueError('stateful marker fields are exact')
        elif kind=='declare':
            if set(args)!={'name','spec'}:raise ValueError('stateful declaration fields are exact')
            name=args['name'];ordinary(name);descriptor(args['spec'])
            if name in declarations:raise ValueError('duplicate stateful declaration')
            if name in step['retained']:
                if args['spec']!='number' or name in step['lengths']:raise ValueError('numeric RETAIN declaration must match retained state')
            elif name not in step['lengths'] or args['spec']!={'type':'character','length':step['lengths'][name]}:raise ValueError('stateful LENGTH declaration must match its descriptor')
            declarations[name]=args['spec']
        elif kind=='read':
            reads+=1
            if set(args)!={'datasets'} or args['datasets']!=step['inputs']:raise ValueError('stateful read must match its driving input')
        elif kind=='assign':
            if set(args)!={'name','value'}:raise ValueError('stateful assignment fields are exact')
            ordinary(args['name']);info=expression(args['value'],by=step['by'])
            if info[0]=='character' and info[2] and args['name'] in step['lengths'] and len(info[3])>step['lengths'][args['name']]:raise ValueError('stateful destination buffer is too short')
            if args['name'] in step['retained']:
                if info[0] not in (None,'number'):raise ValueError('retained assignments require numeric expressions')
                if info[2]:sem.sas_stateful_expression_state(info[3])
        elif kind=='state_sum':
            if stage<3 or set(args)!={'name','value'}:raise ValueError('expression sum requires its qualification stage and exact fields')
            ordinary(args['name']);sums.add(args['name']);info=expression(args['value'],by=step['by'])
            if info[0] not in (None,'number'):raise ValueError('expression sum requires a numeric contribution')
            if info[2]:sem.sas_stateful_expression_state(info[3])
        elif kind=='if':
            if set(args) not in ({'condition','operation'},{'condition','operation','otherwise'}):raise ValueError('stateful IF fields are exact')
            expression(args['condition'],condition=True,by=step['by']);depth+=1
            for key in ('operation','otherwise'):
                if key in args:pending.append((args[key],depth))
        elif kind=='state_group':
            if set(args)!={'body'} or type(args['body']) is not list:raise ValueError('stateful group body is an exact list')
            depth+=1;pending.extend((child,depth) for child in args['body'])
        elif kind=='state_output':
            if set(args)!={'target'} or args['target'] not in (None,step['name']):raise ValueError('stateful OUTPUT target must be the single DATA destination')
        elif kind=='expression_put':
            if set(args)!={'items'} or type(args['items']) is not list or not 1<=len(args['items'])<=32:raise ValueError('stateful PUT requires bounded primitive items')
            for item in args['items']:
                if not ex.primitive(item) or item['kind'] not in ('character','variable'):raise ValueError('stateful PUT requires primitive names or literals')
                expression(item)
        else:raise ValueError('operation requires a later stateful composition stage')
        if depth>16:raise ValueError('stateful action depth budget exceeded')
    explicit={n for n in declarations if n not in step['lengths']}
    if [n for n in declarations if n in step['lengths']]!=list(step['lengths']) or set(step['retained'])!=explicit|sums or set(step['display_names'])!=set(declarations):raise ValueError('stateful declaration order and descriptor maps must agree')
    for name in sums-explicit:
        initial=step['retained'][name]
        if initial['kind']!='number' or initial['value']!=0:raise ValueError('implicit expression sum state requires its zero initializer')
    declared=[];read_seen=False;started=False
    for op in step['operations']:
        kind,args=op['kind'],op['args']
        if kind=='stateful_profile':continue
        if kind=='declare':
            if args['name'] in step['lengths'] and (read_seen or started):raise ValueError('stateful LENGTH declarations must precede SET')
            declared.append(args['name'])
        elif kind=='read':
            if read_seen or started:raise ValueError('stateful SET must precede computations')
            read_seen=True
        else:
            if not read_seen:raise ValueError('stateful actions require the preceding SET')
            started=True
    if declared!=list(declarations) or reads!=1:raise ValueError('stateful declarations/read must be top-level and unique')
    if source:
        if markers:raise ValueError('source cannot supply a portable marker')
    elif len(markers)!=1 or markers[0] is not step['operations'][0]:raise ValueError('stateful profile requires exactly one leading marker')
    if not source and not genuine(step):raise ValueError('stateful marker requires a genuine newly qualified join')


class SourceActions:
    """Parse simple groups and nearest-IF ELSE without admitting iterative loops."""
    def __init__(self,statements,step,source):self.statements=statements;self.step=step;self.source=source

    def action(self,text,line,index,depth=0):
        if depth>16:raise ValueError('stateful source action depth budget exceeded')
        if re.fullmatch('do',text,re.I):
            body=[]
            while index<len(self.statements) and self.statements[index].text.lower()!='end':
                st=self.statements[index];child,index=self.action(st.text,st.line,index+1,depth+1);body.append(child)
            if index>=len(self.statements):raise ValueError('stateful group requires END')
            return {'kind':'state_group','line':line,'args':{'body':body}},index+1
        if re.match(r'if\b',text,re.I):
            parser=Parser(text);parser.need('if');test=parser.expression();parser.need('then');expression(test,condition=True)
            rest=parser.tail()
            if not rest:raise ValueError('stateful IF requires an action')
            branch,index=self.action(rest,line,index,depth+1)
            args={'condition':test,'operation':branch}
            if index<len(self.statements) and re.match(r'else\b',self.statements[index].text,re.I):
                st=self.statements[index];tail=re.sub(r'^else\s*','',st.text,flags=re.I)
                other,index=self.action(tail,st.line,index+1,depth+1);args['otherwise']=other
            return {'kind':'if','line':line,'args':args},index
        match=re.fullmatch(r'('+NAME+r')\s*=\s*(.+)',text,re.I|re.S)
        if match:
            ordinary(match[1].lower())
            return {'kind':'assign','line':line,'args':{'name':match[1].lower(),'value':parse_expression(match[2])}},index
        match=re.fullmatch(r'output(?:\s+('+NAME+'))?',text,re.I)
        if match:return {'kind':'state_output','line':line,'args':{'target':match[1].lower() if match[1] else None}},index
        match=re.fullmatch(r'('+NAME+r')\s*\+\s*(.+)',text,re.I|re.S)
        if match and STAGE>=3:
            ordinary(match[1].lower())
            return {'kind':'state_sum','line':line,'args':{'name':match[1].lower(),'value':parse_expression(match[2])}},index
        match=re.fullmatch(r'put\s+(.+)',text,re.I|re.S)
        if match:
            parser=ex.Parser(match[1]);items=[]
            while parser.index<len(parser.tokens):
                kind,value=parser.pop()
                if kind==1:items.append(parse_expression(value))
                elif kind==3:ordinary(value.lower());items.append({'kind':'variable','value':value.lower()})
                else:raise ValueError('stateful PUT requires primitive values')
            return {'kind':'expression_put','line':line,'args':{'items':items}},index
        raise ValueError('statement is outside the current stateful expression stage')


def parse_step(statements,source):
    from .parser import Kind,tokenize
    from .plan import Step,Operation
    code=' '.join(t.text for t in tokenize(source) if t.kind not in (Kind.STRING,Kind.DATA))
    if re.search(r'&[A-Za-z_]',code):raise ValueError('unresolved macro references require separate review')
    first=statements[0];match=re.fullmatch(r'data\s+('+NAME+')',first.text,re.I)
    if not match or statements[-1].text.lower()!='run' or not all(st.terminated for st in statements):raise ValueError('stateful DATA requires exact header and terminators')
    step=Step('data',match[1].lower(),first.line);body=statements[1:-1];actions=SourceActions(body,step,source);index=0
    while index<len(body):
        st=body[index];text=st.text;index+=1
        match=re.fullmatch(r'length\s+((?:'+NAME+r'\s+)+)\$(\d+)',text,re.I)
        if match:
            for spelling in match[1].split():
                name=spelling.lower()
                if name in step.lengths:raise ValueError('duplicate stateful LENGTH declaration')
                step.lengths[name]=int(match[2]);step.display_names[name]=spelling
                step.operations.append(Operation('declare',st.line,{'name':name,'spec':{'type':'character','length':int(match[2])}}))
            continue
        match=re.fullmatch(r'set\s+('+NAME+')',text,re.I)
        if match:
            if step.inputs:raise ValueError('stateful profile has one driving SET')
            step.inputs=[match[1].lower()];step.operations.append(Operation('read',st.line,{'datasets':step.inputs.copy()}));continue
        match=re.fullmatch(r'retain\s+('+NAME+r')\s+(.+)',text,re.I|re.S)
        if match and STAGE>=2:
            name=match[1].lower();ordinary(name)
            if name in step.retained:raise ValueError('duplicate explicit numeric RETAIN')
            value=parse_expression(match[2])
            if not ex.primitive(value) or value['kind'] not in ('number','missing'):raise ValueError('RETAIN requires one numeric or ordinary-missing literal')
            sem.sas_stateful_expression_state(value['value']);step.retained[name]=value;step.display_names[name]=match[1]
            step.operations.append(Operation('declare',st.line,{'name':name,'spec':'number'}));continue
        match=re.fullmatch(r'by\s+('+NAME+')',text,re.I)
        if match and STAGE>=4:
            if step.by:raise ValueError('stateful profile has exactly one BY declaration')
            step.by=[match[1].lower()];continue
        if re.search(r'\bput\b',text,re.I):
            for left,right in zip(st.tokens,st.tokens[1:]):
                if left.kind==Kind.STRING and right.kind==Kind.WORD and (left.end is None or not source[left.end:left.end+1].isspace()):raise ValueError('literal-to-variable PUT requires original source whitespace')
        action,index=actions.action(text,st.line,index)
        step.operations.append(Operation(action['kind'],action['line'],action['args']))
    for op in walk_ops(asdict(step)['operations']):
        if op['kind']=='state_sum':step.retained.setdefault(op['args']['name'],{'kind':'number','value':0})
    validate_step(asdict(step),source=True)
    step.operations.insert(0,Operation('stateful_profile',step.line,{'profile':PROFILE}))
    validate_step(asdict(step));return step


def compile_program(source,fallback):
    from .parser import ParseError,split_statements
    from .plan import Plan,Ticket
    try:ex.source_guard(source)
    except ParseError:return fallback(source)
    except ValueError as error:return Plan(tickets=[Ticket(1,'','stateful-expressions',str(error))])
    old=fallback(source)
    if not old.blocked:return old
    try:
        statements=split_statements(source);blocks=[];block=[]
        for st in statements:
            if not block and not re.fullmatch(r'data\s+'+NAME,st.text,re.I):return old
            block.append(st)
            if st.text.lower()=='run':blocks.append(block);block=[]
        if block or not 1<=len(blocks)<=16:return old
        plan=Plan();selected=False
        for block in blocks:
            start=block[0].tokens[0].start;end=block[-1].tokens[-1].end
            if start is None or end is None:return old
            end=ex._run_end(source,end);fragment='\n'*(block[0].line-1)+source[start:end]
            prior=fallback(fragment)
            if not prior.blocked:
                if len(prior.steps)!=1 or prior.steps[0].kind!='data':return old
                plan.steps.extend(prior.steps);plan.matched.extend(prior.matched)
            else:
                step=parse_step(block,source);plan.steps.append(step);selected=True
                plan.matched.append(('decision-groups-and-output','DS-123',step.line))
                if any(op['kind']=='declare' and op['args']['spec']=='number' for op in walk_ops(asdict(step)['operations'])):plan.matched.append(('numeric-retention','DS-124',step.line))
                if any(op['kind']=='state_sum' for op in walk_ops(asdict(step)['operations'])):plan.matched.append(('expression-sum-statements','DS-125',step.line))
                if step.by:plan.matched.append(('ordered-by-groups','DS-126',step.line))
        if not selected:return old
        validate_program(plan.to_dict());return plan
    except (ValueError,ParseError,KeyError,TypeError,RecursionError):return old


def validate_program(plan):
    if type(plan) is not dict or set(plan)!={'steps','tickets','matched','version'} or type(plan['version']) is not int or plan['version']!=2 or type(plan['tickets']) is not list or plan['tickets']:raise ValueError('stateful program requires exact unticketed version2 fields')
    if type(plan['steps']) is not list or not 1<=len(plan['steps'])<=16 or type(plan['matched']) is not list or len(plan['matched'])>4096:raise ValueError('stateful program step/provenance budget exceeded')
    for item in plan['matched']:
        if not isinstance(item,(list,tuple)) or len(item)!=3 or type(item[0]) is not str or type(item[1]) is not str or type(item[2]) is not int or item[2]<1:raise ValueError('stateful provenance rows are exact')
    selected=set()
    for step in plan['steps']:
        ex.preflight(step)
        if type(step) is not dict or step.get('kind')!='data' or type(step.get('operations')) is not list:raise ValueError('stateful programs compose ordinary DATA steps only')
        ops=list(walk_ops(step['operations']));markers=[op for op in ops if type(op) is dict and op.get('kind')=='stateful_profile']
        if markers:validate_step(step);selected.add(id(step))
        elif claimed(step):raise ValueError('stateful step requires its own marker')
    if not selected:raise ValueError('stateful program requires a genuine marker')
    return selected


def step_schema(step,tables):
    name=step['inputs'][0]
    if name not in tables:raise ValueError('stateful input dataset is missing: '+name)
    source=tables[name]
    if len(source['rows'])>10000:raise ValueError('stateful input observation budget exceeded')
    if set(step['retained'])&set(source['schema']):raise ValueError('retained state collides with imported input columns')
    for key in step['by']:
        if key not in source['schema'] or column_type(source['schema'][key])!='number':raise ValueError('stateful BY requires an imported numeric key descriptor')
    schema={};read=False
    def type_view():return {**{n:'number' for n in step['retained']},**schema}
    def retained_uses(node):
        pending=[node]
        while pending:
            value=pending.pop()
            if type(value) is dict:
                if value.get('kind')=='variable' and value.get('value') in step['retained']:schema.setdefault(value['value'],'number')
                pending.extend(reversed(list(value.values())))
            elif type(value) in (list,tuple):pending.extend(reversed(value))
    for op in walk_ops(step['operations']):
        kind,args=op['kind'],op['args']
        if kind=='declare':schema.setdefault(args['name'],deepcopy(args['spec']))
        elif kind=='read':
            read=True
            for key,spec in source['schema'].items():
                if key in schema:
                    if column_type(schema[key])!=column_type(spec):raise ValueError('stateful input descriptor type mismatch')
                    width=schema[key]['length'];schema[key]={**deepcopy(spec),'type':'character','length':width}
                else:schema[key]=deepcopy(spec)
        elif kind=='assign':
            typ,width,known,value=expression(args['value'],type_view(),by=step['by'])
            if typ is None or typ=='character' and width is None:raise ValueError('stateful result descriptor is unresolved')
            spec={'type':'character','length':width} if typ=='character' else 'number';key=args['name']
            if key in step['retained'] and typ!='number':raise ValueError('retained assignments require numeric column descriptors')
            if key in schema and column_type(schema[key])!=typ:raise ValueError('stateful assignment descriptor type mismatch')
            schema.setdefault(key,spec)
            retained_uses(args['value'])
            if known and typ=='character' and len(value)>schema[key]['length']:raise ValueError('stateful destination buffer is too short')
        elif kind=='state_sum':
            info=expression(args['value'],type_view(),by=step['by'])
            if info[0]!='number':raise ValueError('expression sum contribution must be numeric')
            schema.setdefault(args['name'],'number');retained_uses(args['value'])
        elif kind=='if':expression(args['condition'],type_view(),condition=True,by=step['by']);retained_uses(args['condition'])
        elif kind=='expression_put':
            types=[expression(item,type_view())[0] for item in args['items']]
            for item in args['items']:retained_uses(item)
            if len(set(types))!=1:raise ValueError('mixed stateful PUT requires separate output composition')
            if any(item['kind']=='variable' and type(schema[item['value']]) is dict and schema[item['value']].get('format') for item in args['items']):raise ValueError('stateful PUT requires unformatted variables')
            if types[0]=='number':sem.sas_put_numeric_list([None]*len(args['items']))
            else:
                items=[{'kind':'literal','value':"'"+item['value'].replace("'","''")+"'"} if item['kind']=='character' else {'kind':'character','value':'x'} for item in args['items']]
                if all(item['kind']=='literal' for item in items):sem.sas_put_literals([item['value'] for item in items])
                else:sem.sas_put_character_list(items)
    if not read or not 1<=len(schema)<=64:raise ValueError('stateful stored-column budget exceeded')
    metadata={k:deepcopy(v) for k,v in source.items() if k not in ('schema','rows')}
    return schema,metadata,source


def execute_step(step,tables):
    schema,metadata,source=step_schema(step,tables);encoding=metadata.get('encoding','ascii');output=[];logs=[];spent=0
    retained={name:sem.sas_stateful_expression_state(value['value']) for name,value in step['retained'].items()}
    keys=[]
    if step['by']:
        key=step['by'][0]
        for original in source['rows']:
            value=sem._sas_expression_number(original[key]);keys.append((0,0) if value is None else (1,value))
        if any(right<left for left,right in zip(keys,keys[1:])):raise ValueError('stateful BY input must already be sorted in ascending missing-first order')
    explicit=any(op['kind']=='state_output' for op in walk_ops(step['operations']))
    def spend():
        nonlocal spent
        spent+=1
        if spent>1000000:raise ValueError('stateful scheduled action budget exceeded')
    for index,original in enumerate(source['rows']):
        spend();row={n:' '*s['length'] if column_type(s)=='character' else None for n,s in schema.items()}
        row.update(retained);row.update(deepcopy(original));row={n:coerce(v,schema[n],encoding) for n,v in row.items()}
        flags={} if not step['by'] else {('first',key):int(index==0 or keys[index]!=keys[index-1]),('last',key):int(index==len(keys)-1 or keys[index]!=keys[index+1])}
        def snapshot():
            if len(output)>=10000:raise ValueError('stateful output observation budget exceeded')
            output.append({n:deepcopy(row[n]) for n in schema})
        def perform(op):
            kind,args=op['kind'],op['args']
            if kind in ('stateful_profile','declare','read'):return
            spend()
            try:
                if kind=='assign':
                    value=value_of(args['value'],row,flags);spec=schema[args['name']]
                    if type(value) is str and len(value)>spec['length']:raise ValueError('stateful destination buffer is too short')
                    if column_type(spec)=='number':sem._sas_expression_number(value)
                    if args['name'] in retained:sem.sas_stateful_expression_state(value)
                    row[args['name']]=coerce(value,spec,encoding)
                elif kind=='state_sum':row[args['name']]=sem.sas_stateful_expression_accumulate(row[args['name']],value_of(args['value'],row,flags))
                elif kind=='if':
                    branch=args['operation'] if sem.sas_expression_truth(value_of(args['condition'],row,flags)) else args.get('otherwise')
                    if branch is not None:perform(branch)
                elif kind=='state_group':
                    for child in args['body']:perform(child)
                elif kind=='state_output':snapshot()
                elif kind=='expression_put':
                    values=[ex.value_of(item,row) for item in args['items']]
                    if all(type(value) is str for value in values):
                        items=[{'kind':'literal','value':"'"+value.replace("'","''")+"'"} if item['kind']=='character' else {'kind':'character','value':value} for item,value in zip(args['items'],values)]
                        record=sem.sas_put_literals([i['value'] for i in items]) if all(i['kind']=='literal' for i in items) else sem.sas_put_character_list(items)
                    else:record=sem.sas_put_numeric_list(values)
                    if len(logs)>=10000:raise ValueError('stateful logical record budget exceeded')
                    logs.append(record)
            except ValueError as error:
                if str(error).startswith('SAS line '):raise
                raise ValueError('SAS line '+str(op['line'])+': '+str(error)) from error
        for op in step['operations']:perform(op)
        if not explicit:spend();snapshot()
        retained={name:deepcopy(row[name]) for name in retained}
    return {**metadata,'schema':schema,'rows':output},logs


def run_program(plan,catalog,legacy):
    selected=validate_program(plan);tables=normalize_catalog({} if catalog is None else catalog);logs=[]
    for step in plan['steps']:
        if id(step) in selected:
            if step['name'] in tables:raise ValueError('stateful DATA destination must be fresh')
            table,records=execute_step(step,tables);tables[step['name']]=table;logs.extend(records)
        else:
            result=legacy({'version':2,'steps':[deepcopy(step)],'tickets':[],'matched':[]},tables)
            if set(result)!={'datasets','log'}:raise ValueError('specialized legacy results require separate composition')
            tables=result['datasets'];logs.extend(result['log'])
    return {'datasets':tables,'log':logs}
