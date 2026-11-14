"""Bounded typed expressions, independently marked and preflighted."""
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import math
import re

import sas_semantics as sem
from .functions import FUNCTIONS
from .values import normalize_catalog, coerce, column_type, descriptor

PROFILE = 'function-expressions-v1'
STAGE = 7
CHARACTERS = frozenset(('upcase','lowcase','trim','strip','trimn','compbl','propcase','dequote','cats','catx','transtrn','substrn'))
SUMMARIES = frozenset(('min','max','sum','coalesce','n','nmiss','largest','smallest'))
NUMERICS = SUMMARIES | {'abs','sign','ceilz','floorz','intz','roundz','modz'}
POSITIONS = frozenset(('anyalpha','anydigit','anyalnum','anyspace','notdigit','anylower','anyupper','anypunct','anyxdigit','notalpha','notalnum','notspace'))
BRIDGES = POSITIONS | {'missing','cmiss','length','lengthn','verify'}
SELECTORS = frozenset(('ifn','ifc'))
COHORT = CHARACTERS | NUMERICS | BRIDGES | SELECTORS
NAME = r'[A-Za-z_][A-Za-z0-9_]{0,31}'
COMPARISONS = {'=':'eq','eq':'eq','^=':'ne','~=':'ne','ne':'ne','<':'lt','lt':'lt','<=':'le','le':'le','>':'gt','gt':'gt','>=':'ge','ge':'ge'}
STEP_FIELDS = {'kind','name','line','inputs','by','operations','nodupkey','where','retained','lengths','display_names'}
TOKEN = re.compile(r'''\s*(?:('(?:[^']|'')*'|"(?:[^"]|"")*")|((?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)|([A-Za-z_][A-Za-z0-9_]*)|(<=|>=|\^=|~=|<>|\*\*|\|\||[(),.+\-*/=<>^~&|]))''')


def ordinary(value):
    if type(value) is not str or not re.fullmatch('[a-z_][a-z0-9_]{0,31}', value, re.ASCII) or value in ('_n_','_error_'):
        raise ValueError('expression profile requires normalized ordinary names')


def preflight(value):
    """Iterative resource check before any recursive expression or legacy walker."""
    pending = [(value,0,0,False)]; active=set(); containers=calls=0
    while pending:
        node,depth,levels,closing=pending.pop()
        if not isinstance(node,(dict,list,tuple)):continue
        if closing:active.remove(id(node));continue
        if id(node) in active:raise ValueError('expression trees cannot contain cycles')
        containers+=1
        if containers>16384 or depth>64:raise ValueError('expression container/structural depth budget exceeded')
        if type(node) is dict and node.get('kind')=='call':
            calls+=1;levels+=1
            if calls>128 or levels>4:raise ValueError('expression call budget/depth exceeded')
        active.add(id(node));pending.append((node,depth,levels,True))
        children=list(node.values()) if isinstance(node,dict) else list(node)
        if len(children)>16384:raise ValueError('expression container budget exceeded')
        pending.extend((child,depth+1,levels,False) for child in reversed(children))


def claimed(plan):
    """Find a genuine marker or reject unmarked novel nodes without recursion."""
    pending=[plan];seen=set();present=novel=False
    while pending:
        node=pending.pop()
        if not isinstance(node,(dict,list,tuple)) or id(node) in seen:continue
        seen.add(id(node))
        if len(seen)>294912:raise ValueError('expression program container budget exceeded')
        if isinstance(node,dict):
            if node.get('kind')=='function_profile' and type(node.get('args')) is dict and node['args'].get('profile')==PROFILE:present=True
            if node.get('kind') in ('expr_compare','expr_boolean','expr_unary'):novel=True
            pending.extend(node.values())
        else:pending.extend(node)
    if novel and not present:raise ValueError('typed expression nodes require their explicit profile marker')
    return present


class Parser:
    """Quote-aware bounded Pratt parser; admission is independently staged."""
    def __init__(self,text):
        self.tokens=[];position=0
        while position<len(text):
            if not text[position:].strip():break
            match=TOKEN.match(text,position)
            if not match:raise ValueError('unsupported expression token')
            self.tokens.append((match.lastindex,match.group(match.lastindex)))
            if len(self.tokens)>8192:raise ValueError('expression token budget exceeded')
            position=match.end()
        self.index=0
    def peek(self):return self.tokens[self.index][1].lower() if self.index<len(self.tokens) else ''
    def pop(self):
        if self.index>=len(self.tokens):raise ValueError('incomplete expression')
        value=self.tokens[self.index];self.index+=1;return value
    def need(self,token):
        if self.peek()!=token:raise ValueError('expression delimiter mismatch')
        self.pop()
    def expression(self,minimum=0,depth=0):
        if depth>16:raise ValueError('expression depth budget exceeded')
        kind,value=self.pop();lower=value.lower()
        if kind==1:
            if len(value)<=2:raise ValueError('empty source character literals require a separate contract')
            if value[0]=='"' and re.search(r'[&%][A-Za-z_]',value):raise ValueError('macro resolution is outside the expression profile')
            left={'kind':'character','value':value[1:-1].replace(value[0]*2,value[0])}
        elif kind==2:
            number=float(value)
            if not math.isfinite(number) or number==0 and Decimal(value)!=0:raise ValueError('numeric literal loses its finite nonzero value')
            left={'kind':'number','value':number}
        elif lower=='.':left={'kind':'missing','value':None}
        elif lower in ('+','-','not','^','~'):
            if lower in ('+','-') and self.index<len(self.tokens) and self.tokens[self.index][0]==2:
                text=self.pop()[1];number=float(lower+text)
                if not math.isfinite(number) or number==0 and Decimal(text)!=0:raise ValueError('numeric literal loses its finite nonzero value')
                left={'kind':'number','value':number}
            else:left={'kind':'expr_unary','op':'not' if lower in ('not','^','~') else lower,'value':self.expression(70,depth+1)}
        elif lower=='(':
            left=self.expression(0,depth+1);self.need(')')
        elif kind==3:
            ordinary(lower)
            if self.peek()=='(':
                self.pop();args=[]
                if self.peek()!=')':
                    while True:
                        args.append(self.expression(0,depth+1))
                        if len(args)>33:raise ValueError('expression call argument budget exceeded')
                        if self.peek()!=',':break
                        self.pop()
                self.need(')');left={'kind':'call','name':lower,'args':args}
            else:left={'kind':'variable','value':lower}
        else:raise ValueError('unsupported expression atom')
        levels={'or':10,'|':10,'and':20,'&':20,**{x:30 for x in COMPARISONS},'+':50,'-':50}
        compared=False
        while self.peek() in levels and levels[self.peek()]>=minimum:
            op=self.pop()[1].lower();priority=levels[op]
            right=self.expression(priority+1,depth+1)
            if op in COMPARISONS:
                if compared or left.get('kind')=='expr_compare' or right.get('kind')=='expr_compare':raise ValueError('chained comparisons require a separate contract')
                compared=True;left={'kind':'expr_compare','op':COMPARISONS[op],'left':left,'right':right}
            elif op in ('and','&','or','|'):left={'kind':'expr_boolean','op':'and' if op in ('and','&') else 'or','left':left,'right':right}
            else:left={'kind':'arithmetic','op':op,'left':left,'right':right}
        return left
    def complete(self):
        value=self.expression()
        if self.index!=len(self.tokens):raise ValueError('unqualified trailing expression syntax')
        return value


def parse_expression(text):return Parser(text).complete()


def checked_call(node):
    if set(node)!={'kind','name','args'} or type(node['name']) is not str or node['name'] not in COHORT or type(node['args']) is not list:
        raise ValueError('expression requires an exact call from the qualified cohort')
    spec=FUNCTIONS[node['name']];size=len(node['args'])
    if not spec.min_args<=size<=33 or spec.max_args>=0 and size>spec.max_args or node['name'] in ('min','max','sum') and size>32:
        raise ValueError('expression call arity exceeds its bounded contract')
    return spec


def primitive(node):return type(node) is dict and node.get('kind') in ('number','missing','character','variable') and set(node)=={'kind','value'}


def value_of(node,row):
    kind=node['kind']
    if kind=='variable':return row[node['value']]
    if kind in ('number','missing','character'):return node['value']
    if kind=='call':return sem.sas_expression_call(node['name'],[value_of(arg,row) for arg in node['args']])
    if kind=='arithmetic':return sem.sas_expression_arithmetic(node['op'],[value_of(node['left'],row),value_of(node['right'],row)])
    if kind=='expr_unary' and node['op'] in ('+','-'):return sem.sas_expression_arithmetic(node['op'],[value_of(node['value'],row)])
    if kind=='expr_boolean':return sem.sas_expression_boolean(node['op'],[value_of(node['left'],row),value_of(node['right'],row)])
    if kind=='expr_unary' and node['op']=='not':return sem.sas_expression_boolean('not',[value_of(node['value'],row)])
    if kind=='expr_compare':return sem.sas_expression_compare(node['op'],value_of(node['left'],row),value_of(node['right'],row))
    raise ValueError('expression operation requires a later qualified stage')


def _original_domains(node,info,schema):
    """Reuse original family literal/descriptor checks without erasing new temporaries."""
    from .function_wave import NAMES,call_width
    name=node['name']
    if name not in NAMES:return
    specs=dict(schema or {});arguments=[]
    def expected(i):
        if name in CHARACTERS:return 'number' if name=='substrn' and i else 'character'
        if name in NUMERICS:return 'number'
        if name in POSITIONS:return 'character' if i==0 else 'number'
        if name in ('length','lengthn','verify'):return 'character'
        if name=='ifc':return 'number' if i==0 else 'character'
        return info[i][0] or 'number'
    for i,(arg,item) in enumerate(zip(node['args'],info)):
        typ=expected(i)
        if primitive(arg):proxy=dict(arg)
        elif item[2] and not (type(item[3]) is str and not item[3]):
            value=item[3];proxy={'kind':'character' if type(value) is str else 'missing' if value is None else 'number','value':value}
        else:
            key='_expression_arg_'+str(i)
            suffix=0
            while key in specs:
                suffix+=1;key='_expression_arg_'+str(i)+'_'+str(suffix)
            specs[key]={'type':'character','length':1} if typ=='character' else 'number'
            proxy={'kind':'variable','value':key}
        if proxy['kind']=='variable' and proxy['value'] not in specs:
            specs[proxy['value']]={'type':'character','length':1} if typ=='character' else 'number'
        arguments.append(proxy)
    call_width({'kind':'call','name':name,'args':arguments},specs)


def describe(node,schema=None,*,context='value',depth=0):
    """Infer type/width, verify argument roles and fold every constant subtree."""
    if type(node) is not dict or type(node.get('kind')) is not str or depth>16:raise ValueError('expression node/depth is invalid')
    kind=node['kind'];known=False;value=None
    if context=='condition' and STAGE<3 and kind in ('arithmetic','expr_unary'):raise ValueError('computed numeric truth requires stage3')
    if kind in ('number','missing','character','variable'):
        if set(node)!={'kind','value'}:raise ValueError('expression primitive fields are exact')
        value=node['value']
        if kind=='character':
            sem._sas_expression_text(value)
            if not value:raise ValueError('empty source literals are outside the expression profile')
            typ,width='character',len(value);known=True
        elif kind=='number':
            if type(value) not in (int,float) or abs(value)>2147483647 or not math.isfinite(value):raise ValueError('expression numeric literal is outside finite bounds')
            typ,width='number',None;known=True
        elif kind=='missing':
            if value is not None:raise ValueError('expression ordinary missing must be null')
            typ,width='number',None;known=True
        else:
            ordinary(value)
            if schema is None:typ,width=None,None
            else:
                if value not in schema:raise ValueError('expression variable lacks a preceding descriptor: '+value)
                spec=schema[value];typ=column_type(spec);width=spec['length'] if typ=='character' else None
        return typ,width,known,value
    if kind=='call':
        if context=='condition' and STAGE<3:raise ValueError('bare function truth requires stage3')
        spec=checked_call(node);name=node['name'];args=node['args']
        info=[describe(arg,schema,depth=depth+1) for arg in args]
        types=[i[0] for i in info];widths=[i[1] for i in info]
        def require(index,typ):
            if types[index] not in (None,typ):raise ValueError('expression argument requires '+typ+' type')
        def control(index,typ,literal=False,limit=None):
            require(index,typ)
            if not primitive(args[index]) or literal and args[index]['kind']!='character':raise ValueError('expression control requires a qualified primitive or literal')
            if typ=='character' and limit is not None and widths[index] is not None and not 1<=widths[index]<=limit:raise ValueError('expression character control width is outside its contract')
        if name in CHARACTERS:
            if name=='substrn':
                require(0,'character')
                for i in range(1,len(args)):control(i,'number')
            else:
                for i in range(len(args)):require(i,'character')
            if name=='propcase':control(1,'character',True,64)
            if name=='catx':control(0,'character',True,64)
            if name=='transtrn':control(1,'character',limit=64)
            width=200 if name in ('cats','catx','transtrn') else widths[0]
        elif name in NUMERICS:
            for i in range(len(args)):require(i,'number')
            if STAGE<2 and any(not primitive(arg) for arg in args):raise ValueError('numeric expression trees require stage2')
            if name in ('largest','smallest'):control(0,'number')
            if name in ('roundz','modz') and len(args)>1:control(1,'number')
            width=None
        elif name in BRIDGES:
            if STAGE<3 and any(not primitive(arg) for arg in args):raise ValueError('computed bridge arguments require stage3')
            if name in POSITIONS:
                require(0,'character')
                if len(args)>1:control(1,'number')
            elif name=='verify':
                require(0,'character')
                for i in range(1,len(args)):control(i,'character',limit=64)
            elif name in ('length','lengthn'):require(0,'character')
            width=None
        else:
            require(0,'number')
            for i in range(1,len(args)):require(i,'character' if name=='ifc' else 'number')
            if STAGE<5 and any(not primitive(arg) for arg in args):raise ValueError('expression selector arguments require stage5')
            width=200 if name=='ifc' else None
        # Check literal control domains independently of a dynamic first value.
        for i,arg in enumerate(args):
            if not info[i][2]:continue
            v=info[i][3]
            if name in ('substrn',) and i>0 or name in POSITIONS and i==1:sem._sas_wave2_integer(v,missing=name!='anypunct')
            if name in ('largest','smallest') and i==0:sem._sas_wave2_integer(v,1,len(args)-1)
            if name in ('roundz','modz') and i==1:sem._sas_wave3_power(v,signed=name=='modz')
            if name in NUMERICS and not(name in ('largest','smallest') and i==0) and not(name in ('roundz','modz') and i==1):sem._sas_expression_number(v)
            if name=='sum' and v is not None and v*1024!=int(v*1024):raise ValueError('SUM expression requires the exact dyadic grid')
        _original_domains(node,info,schema)
        if name=='cats':
            minimum=sum(len(i[3].strip(' ')) for i in info if i[2])
            if minimum>200:raise ValueError('constant constructor buffer exceeds200bytes')
        if name=='catx':
            pieces=[i[3].strip(' ') for i in info[1:] if i[2] and i[3].strip(' ')]
            minimum=sum(map(len,pieces))+len(args[0]['value'])*max(0,len(pieces)-1)
            if minimum>200:raise ValueError('constant constructor buffer exceeds200bytes')
        known=all(i[2] for i in info)
        value=value_of(node,{}) if known else None
        return spec.returns,width,known,value
    if kind=='expr_boolean' or kind=='expr_unary' and node.get('op')=='not':
        fields={'kind','op','left','right'} if kind=='expr_boolean' else {'kind','op','value'}
        allowed=('and','or') if kind=='expr_boolean' else ('not',)
        if STAGE<4 or set(node)!=fields or type(node.get('op')) is not str or node['op'] not in allowed:
            raise ValueError('expression Boolean shape/operator is invalid')
        children=[node['left'],node['right']] if kind=='expr_boolean' else [node['value']]
        info=[describe(child,schema,depth=depth+1) for child in children]
        for typ,width,known,value in info:
            if typ not in (None,'number'):raise ValueError('Boolean predicates require numeric operands')
            if known:sem.sas_expression_truth(value)
        known=all(item[2] for item in info)
        return 'number',None,known,value_of(node,{}) if known else None
    if kind in ('arithmetic','expr_unary'):
        fields={'kind','op','left','right'} if kind=='arithmetic' else {'kind','op','value'}
        if STAGE<2 or set(node)!=fields or type(node.get('op')) is not str or node['op'] not in ('+','-'):
            raise ValueError('expression integer arithmetic shape/operator is invalid')
        children=[node['left'],node['right']] if kind=='arithmetic' else [node['value']]
        info=[describe(child,schema,depth=depth+1) for child in children]
        for typ,width,known,value in info:
            if typ not in (None,'number'):raise ValueError('integer arithmetic requires numeric operands')
            if known:sem.sas_expression_arithmetic('+',[value])
        known=all(item[2] for item in info)
        return 'number',None,known,value_of(node,{}) if known else None
    if kind=='expr_compare':
        if set(node)!={'kind','op','left','right'} or type(node['op']) is not str or node['op'] not in set(COMPARISONS.values()):raise ValueError('expression comparison shape/operator is invalid')
        a=describe(node['left'],schema,depth=depth+1);b=describe(node['right'],schema,depth=depth+1)
        if a[0] is not None and b[0] is not None and a[0]!=b[0]:raise ValueError('comparison requires compatible types')
        for item in (a,b):
            if item[2] and item[0]=='number':sem._sas_expression_number(item[3])
        if STAGE<3:
            left,right=node['left'],node['right']
            old_pred=(left.get('kind')=='call' and left.get('name') in POSITIONS|{'missing','verify'} and all(primitive(arg) for arg in left['args']) and right.get('kind')=='number' and type(right.get('value')) in (int,float) and 0<=right['value']<=32767 and right['value']==int(right['value']))
            if context!='condition' or not ((primitive(left) and primitive(right)) or old_pred):raise ValueError('computed comparisons require stage3')
        known=a[2] and b[2];return 'number',None,known,value_of(node,{}) if known else None
    raise ValueError('expression node requires a later qualified stage')


def _walk_ops(ops):
    pending=list(reversed(ops))
    while pending:
        op=pending.pop();yield op
        if type(op) is dict and op.get('kind')=='if' and type(op.get('args')) is dict:
            a=op['args']
            if 'otherwise' in a:pending.append(a['otherwise'])
            if 'operation' in a:pending.append(a['operation'])


def _predicate(node,schema=None):
    info=describe(node,schema,context='condition')
    if info[0]!='number' and not (schema is None and info[0] is None):raise ValueError('expression predicate requires numeric truth')
    if info[2]:sem.sas_expression_truth(info[3])
    return info


def validate_step(step,*,source=False):
    preflight(step)
    if type(step) is not dict or set(step)!=STEP_FIELDS or step['kind']!='data':raise ValueError('expression profile requires exact ordinary DATA steps')
    ordinary(step['name'])
    if type(step['line']) is not int or step['line']<1 or type(step['inputs']) is not list or len(step['inputs'])>1:raise ValueError('expression input/line fields are invalid')
    for name in step['inputs']:ordinary(name)
    if step['by']!=[] or type(step['by']) is not list or step['retained']!={} or type(step['retained']) is not dict or step['nodupkey'] is not False:raise ValueError('expression state/BY/RETAIN requires separate composition')
    if type(step['lengths']) is not dict or type(step['display_names']) is not dict or type(step['operations']) is not list:raise ValueError('expression descriptor/operation shape is invalid')
    for n,w in step['lengths'].items():
        ordinary(n)
        if type(w) is not int or not 1<=w<=32767:raise ValueError('expression storage width outside bounds')
    for n,d in step['display_names'].items():
        ordinary(n)
        if type(d) is not str or not re.fullmatch(NAME,d,re.ASCII):raise ValueError('expression display names are invalid')
    pending=[(op,0) for op in step['operations']]
    while pending:
        op,levels=pending.pop()
        if type(op) is dict and op.get('kind')=='if' and type(op.get('args')) is dict:
            levels+=1
            if levels>16:raise ValueError('expression conditional depth budget exceeded')
            pending.extend((op['args'][k],levels) for k in ('operation','otherwise') if k in op['args'])
    ops=list(_walk_ops(step['operations']))
    if not 1<=len(ops)<=256:raise ValueError('expression operation budget exceeded')
    markers=[];reads=0;subsets=0
    for op in ops:
        if type(op) is not dict or set(op)!={'kind','line','args'} or type(op['line']) is not int or op['line']<1 or type(op['args']) is not dict:raise ValueError('expression operation fields are exact')
        kind,args=op['kind'],op['args']
        if kind=='function_profile':
            markers.append(op)
            if args!={'profile':PROFILE}:raise ValueError('expression profile marker fields are exact')
        elif kind=='read':
            if set(args)!={'datasets'} or args['datasets']!=step['inputs'] or not step['inputs']:raise ValueError('expression read must match its input')
            reads+=1
        elif kind=='declare':
            if set(args)!={'name','spec'}:raise ValueError('expression declaration fields are exact')
            ordinary(args['name']);descriptor(args['spec'])
        elif kind=='assign':
            if set(args)!={'name','value'}:raise ValueError('expression assignment fields are exact')
            ordinary(args['name']);info=describe(args['value'])
            if info[0]=='number' and info[2]:sem._sas_expression_number(info[3])
        elif kind=='if':
            if set(args) not in ({'condition','operation'},{'condition','operation','otherwise'}):raise ValueError('expression IF fields are exact')
            if any(type(args[k]) is not dict or args[k].get('kind') not in ('assign','if') for k in ('operation','otherwise') if k in args):raise ValueError('expression IF actions are assignment/IF only')
            info=describe(args['condition'],context='condition');typ=info[0]
            if info[2]:sem._sas_expression_number(info[3])
            if typ not in (None,'number'):raise ValueError('IF requires numeric truth')
        elif kind=='expression_put':
            if set(args)!={'items'} or type(args['items']) is not list or not 1<=len(args['items'])<=32 or any(not primitive(i) or i['kind'] not in ('character','variable') for i in args['items']):raise ValueError('expression PUT requires bounded primitive items')
            for item in args['items']:
                describe(item)
                if item['kind']=='variable' and item['value'] in ('_all_','_numeric_','_character_','_n_','_error_','_infile_','_file_','_ods_','_page_','_blankpage_'):
                    raise ValueError('special PUT controls require their separate output profile')
        elif kind=='subset':
            subsets+=1
            if STAGE<6 or set(args)!={'condition'}:raise ValueError('composed subsetting IF requires stage6')
            _predicate(args['condition'])
        else:raise ValueError('expression operation requires separate composition')
    declared={};read_seen=started=False
    for op in step['operations']:
        kind,args=op['kind'],op['args']
        if kind=='function_profile':continue
        if kind=='declare':
            n=args['name']
            if started or read_seen or n in declared or n not in step['lengths'] or args['spec']!={'type':'character','length':step['lengths'][n]}:
                raise ValueError('expression declaration must match its ordered step descriptor before SET')
            declared[n]=args['spec']
        elif kind=='read':
            if started or read_seen:raise ValueError('expression SET must precede computations')
            read_seen=True
        else:
            if step['inputs'] and not read_seen:raise ValueError('expression computations require their preceding SET')
            started=True
    if list(declared)!=list(step['lengths']) or set(step['display_names'])!=set(step['lengths']) or any(d.lower()!=n for n,d in step['display_names'].items()):
        raise ValueError('expression declarations, lengths and display names must agree')
    if source:
        if markers:raise ValueError('source cannot supply a portable profile marker')
    elif len(markers)!=1 or markers[0] is not step['operations'][0]:raise ValueError('expression profile requires one exact leading marker')
    if reads!=len(step['inputs']):raise ValueError('expression profile requires exactly its driving read')
    if subsets and (subsets>1 or not step['inputs'] or any(op.get('kind')=='subset' and op not in step['operations'] for op in ops)):raise ValueError('one top-level subset with one input is qualified')
    if step['where'] is not None:
        if STAGE<7 or not step['inputs']:raise ValueError('composed WHERE requires stage7 and one input')
        _predicate(step['where'])
    if not source and not genuine(step):raise ValueError('expression marker requires a genuine newly admitted expression or context')


def genuine(step):
    """Independently retain the old consumer grammars as compatibility controls."""
    pending=[step]
    while pending:
        node=pending.pop()
        if type(node) is dict:
            if node.get('kind')=='call' and type(node.get('args')) is list:
                children=[arg for arg in node['args'] if type(arg) is dict and arg.get('kind')=='call']
                # Legacy consumer validators do not own CATX temporary contexts.
                if children and (node.get('name')=='catx' or any(arg.get('name')=='catx' for arg in children)):return True
            pending.extend(node.values())
        elif type(node) is list:pending.extend(node)
    for op in _walk_ops(step['operations']):
        if op['kind']=='assign':
            pending=[op['args']['value']]
            while pending:
                node=pending.pop()
                if type(node) is dict:
                    if node.get('kind') in ('expr_compare','expr_boolean','expr_unary'):return True
                    pending.extend(node.values())
                elif type(node) is list:pending.extend(node)
        if op['kind'] in ('if','subset') and op['args']['condition'].get('kind') in ('expr_boolean','expr_unary'):return True
    old=deepcopy(step);old['operations']=[op for op in old['operations'] if op['kind'] not in ('function_profile','expression_put')]
    for op in _walk_ops(old['operations']):
        if op['kind'] in ('if','subset'):
            test=op['args']['condition']
            if test.get('kind')=='expr_compare':op['args']['condition']={k:v for k,v in test.items() if k!='kind'}
            else:op['args']['condition']={'left':test,'op':'truth'}
    from . import function_consumers as v1,function_consumers_v2 as v2
    for engine in (v1,v2):
        try:engine._validate_step(old,2,marked=False,require_consumer=False)
        except (ValueError,KeyError,TypeError):continue
        else:return False
    return True


def _action(text,line,_depth=0):
    if _depth>16:raise ValueError('expression conditional depth budget exceeded')
    from .plan import Operation
    p=Parser(text)
    if p.peek()=='if':
        p.pop();test=p.expression()
        if p.peek()=='then':
            p.pop();tail=' '.join(t[1] for t in p.tokens[p.index:]);return Operation('if',line,{'condition':test,'operation':asdict(_action(tail,line,_depth+1))})
        if p.index!=len(p.tokens):raise ValueError('unsupported IF syntax')
        return Operation('subset',line,{'condition':test})
    match=re.fullmatch('('+NAME+r')\s*=\s*(.+)',text,re.S)
    if not match:raise ValueError('expression action requires assignment or IF')
    return Operation('assign',line,{'name':match[1].lower(),'value':parse_expression(match[2])})


def _unmatched_ifs(operation):
    # ELSE binds to the nearest unmatched IF, including nested THEN actions.
    args=operation.args if hasattr(operation,'args') else operation['args']
    kind=operation.kind if hasattr(operation,'kind') else operation['kind']
    unmatched=[]
    while kind=='if':
        unmatched.append(args)
        child=args.get('otherwise',args['operation']);kind=child['kind'];args=child['args']
    return unmatched


def parse_step(statements,source_text):
    from .parser import tokenize,Kind
    code=' '.join(t.text for t in tokenize(source_text) if t.kind not in (Kind.STRING,Kind.DATA))
    if re.search(r'&[A-Za-z_]',code):raise ValueError('unresolved macro references are outside the expression profile')
    from .plan import Step,Operation
    first=statements[0];match=re.fullmatch(r'data\s+('+NAME+')',first.text,re.I)
    if not match or statements[-1].text.lower()!='run':raise ValueError('expression DATA header/terminator is outside scope')
    step=Step('data',match[1].lower(),first.line);pending=[];computed=False
    for st in statements[1:-1]:
        text=st.text
        if not st.terminated:raise ValueError('expression statements require terminators')
        m=re.fullmatch(r'length\s+((?:'+NAME+r'\s+)+)\$(\d+)',text,re.I)
        if m:
            if computed or step.inputs:raise ValueError('expression LENGTH declarations must precede SET/computations')
            for n in m[1].split():
                key=n.lower()
                if key in step.lengths:raise ValueError('expression LENGTH names must be distinct')
                step.lengths[key]=int(m[2]);step.display_names[key]=n
                step.operations.append(Operation('declare',st.line,{'name':key,'spec':{'type':'character','length':int(m[2])}}))
            pending=[];continue
        m=re.fullmatch(r'set\s+('+NAME+')',text,re.I)
        if m:
            if step.inputs or computed:raise ValueError('expression step requires one SET before computations')
            step.inputs=[m[1].lower()];step.operations.append(Operation('read',st.line,{'datasets':step.inputs.copy()}));pending=[];continue
        m=re.match(r'where\s+(.+)\Z',text,re.I|re.S)
        if m:
            if step.where is not None:raise ValueError('one WHERE is qualified')
            step.where=parse_expression(m[1]);pending=[];continue
        m=re.fullmatch(r'put\s+(.+)',text,re.I|re.S)
        if m:
            from .parser import Kind
            tokens=st.tokens[1:]
            if any(left.kind==Kind.STRING and right.kind==Kind.WORD and (left.end is None or not source_text[left.end:left.end+1].isspace()) for left,right in zip(tokens,tokens[1:])):
                raise ValueError('literal-to-variable PUT requires original source whitespace')
            p=Parser(m[1]);items=[]
            while p.index<len(p.tokens):
                k,v=p.pop()
                if k==1:items.append(parse_expression(v))
                elif k==3:items.append({'kind':'variable','value':v.lower()})
                else:raise ValueError('expression PUT permits primitive names/literals')
            step.operations.append(Operation('expression_put',st.line,{'items':items}));pending=[];computed=True;continue
        m=re.fullmatch(r'else\s+(.+)',text,re.I|re.S)
        if m:
            if not pending:raise ValueError('ELSE requires an unmatched IF')
            action=asdict(_action(m[1],st.line));pending.pop()['otherwise']=action
            pending.extend(_unmatched_ifs(action));continue
        action=_action(text,st.line);step.operations.append(action);computed=True
        pending=_unmatched_ifs(action)
    data=asdict(step);validate_step(data,source=True)
    step.operations.insert(0,Operation('function_profile',first.line,{'profile':PROFILE}))
    return step


def source_guard(source):
    """Protect the legacy parser from deeply nested candidate expressions."""
    from .parser import tokenize,Kind
    tokens=tokenize(source);code=' '.join(t.text for t in tokens if t.kind not in (Kind.STRING,Kind.DATA))
    if not re.search(r'\b(?:'+ '|'.join(sorted(COHORT))+r')\s*\(',code,re.I):return
    for statement in code.split(';'):
        if len(re.findall(r'\bthen\b',statement,re.I))>16:raise ValueError('expression source conditional depth budget exceeded')
    depth=0
    for char in code:
        if char=='(':depth+=1
        elif char==')':depth-=1
        if depth>64:raise ValueError('expression source structural depth budget exceeded')


def features(step):
    selected=set();pending=[step]
    while pending:
        node=pending.pop()
        if type(node) is dict:
            kind=node.get('kind');name=node.get('name')
            if kind=='call' and name in CHARACTERS and any(not primitive(a) for a in node['args']):selected.add(1)
            if kind=='call' and name in NUMERICS and any(not primitive(a) for a in node['args']):selected.add(2)
            if kind=='arithmetic' or kind=='expr_unary' and node.get('op') in ('+','-'):selected.add(2)
            if kind=='expr_boolean' or kind=='expr_unary' and node.get('op')=='not':selected.add(4)
            if kind=='expr_compare':selected.add(3)
            if kind=='subset':selected.add(6)
            if kind=='data' and node['where'] is not None:selected.add(7)
            if kind=='call' and name in SELECTORS and any(not primitive(a) for a in node['args']):selected.add(5)
            if kind=='call' and name in BRIDGES and any(not primitive(a) for a in node['args']):selected.add(3)
            if kind=='if' and node['args']['condition'].get('kind') not in ('number','missing','variable','expr_compare'):selected.add(3)
            pending.extend(node.values())
        elif type(node) in (list,tuple):pending.extend(node)
    return [(('character-expressions','numeric-expressions','comparisons-and-truth','boolean-conditions','selector-expressions','subsetting-if','where-composition')[stage-1],'DS-'+str(115+stage),step['line']) for stage in sorted(selected or {1})]


def _run_end(source,index):
    while index<len(source):
        if source[index].isspace():index+=1;continue
        if source.startswith('/*',index):
            levels=1;index+=2
            while levels and index<len(source):
                if source.startswith('/*',index):levels+=1;index+=2
                elif source.startswith('*/',index):levels-=1;index+=2
                else:index+=1
            if levels:raise ValueError('unterminated RUN comment')
        elif source.startswith('%*',index):
            end=source.find(';',index+2)
            if end<0:raise ValueError('unterminated RUN macro comment')
            index=end+1
        elif source[index]==';':return index+1
        else:raise ValueError('RUN requires its lexical statement terminator')
    raise ValueError('RUN requires a statement terminator')


def compile_program(source,fallback):
    from .plan import Plan,Ticket
    from .parser import split_statements,ParseError
    try:source_guard(source)
    except ParseError:return fallback(source)
    except ValueError as error:return Plan(tickets=[Ticket(getattr(error,'line',1),'','function-expressions',str(error))])
    old=fallback(source)
    if not old.blocked:return old
    try:
        statements=split_statements(source);blocks=[];block=[]
        for st in statements:
            if not block and not re.fullmatch(r'data\s+'+NAME,st.text,re.I):return old
            block.append(st)
            if st.text.lower()=='run':blocks.append(block);block=[]
        if block or not blocks or len(blocks)>16:return old
        plan=Plan();new=False
        for block in blocks:
            start=block[0].tokens[0].start;end=block[-1].tokens[-1].end
            if start is None or end is None:return old
            end=_run_end(source,end)
            fragment='\n'*(block[0].line-1)+source[start:end]
            prior=fallback(fragment)
            if not prior.blocked:
                if len(prior.steps)!=1 or prior.steps[0].kind!='data':return old
                plan.steps.extend(prior.steps);plan.matched.extend(prior.matched)
            else:
                step=parse_step(block,source);plan.steps.append(step);new=True
                plan.matched.extend(features(asdict(step)))
        if not new:return old
        validate_program(plan.to_dict());return plan
    except (ValueError,ParseError,KeyError,TypeError,RecursionError) as error:
        return old


def validate_program(plan):
    if type(plan) is not dict or set(plan)!={'steps','tickets','matched','version'} or type(plan['version']) is not int or plan['version']!=2 or type(plan['tickets']) is not list or plan['tickets']:
        raise ValueError('expression program requires exact unticketed version2 fields')
    if type(plan['steps']) is not list or not 1<=len(plan['steps'])<=16 or type(plan['matched']) is not list or len(plan['matched'])>4096:raise ValueError('expression program step/provenance budget exceeded')
    for row in plan['matched']:
        if not isinstance(row,(list,tuple)) or len(row)!=3 or type(row[0]) is not str or type(row[1]) is not str or type(row[2]) is not int or row[2]<1:raise ValueError('expression provenance rows are exact')
    selected=[]
    for step in plan['steps']:
        preflight(step)
        if type(step) is not dict or step.get('kind')!='data' or type(step.get('operations')) is not list:raise ValueError('expression programs require ordinary DATA steps')
        markers=[op for op in _walk_ops(step['operations']) if type(op) is dict and op.get('kind')=='function_profile' and type(op.get('args')) is dict and op['args'].get('profile')==PROFILE]
        if markers:validate_step(step);selected.append(id(step))
        elif any(type(op) is not dict or op.get('kind') in ('do_counted','do_while','do_until','do_over','lookup','array_declare','sum_statement','file') for op in _walk_ops(step['operations'])):raise ValueError('legacy stateful joins require separate composition')
    if not selected:raise ValueError('expression program requires a genuine profile marker')
    return set(selected)


def _step_schema(step,tables):
    if any(n not in tables for n in step['inputs']):raise ValueError('expression input dataset is missing')
    source=tables[step['inputs'][0]] if step['inputs'] else None
    metadata={k:deepcopy(v) for k,v in source.items() if k not in ('schema','rows')} if source else {}
    schema={n:{'type':'character','length':w} for n,w in step['lengths'].items()}
    for n,spec in (source['schema'].items() if source else []):
        if n in schema and column_type(schema[n])!=column_type(spec):raise ValueError('expression input descriptor type mismatch')
        if n in schema:
            width=schema[n]['length'];schema[n]={**deepcopy(spec),'type':'character','length':width}
        else:schema[n]=deepcopy(spec)
    for op in _walk_ops(step['operations']):
        kind,args=op['kind'],op['args']
        if kind=='assign':
            typ,width,known,value=describe(args['value'],schema)
            if typ is None or typ=='character' and width is None:raise ValueError('expression result descriptor is unresolved')
            n=args['name'];spec={'type':'character','length':width} if typ=='character' else 'number'
            if n in schema and column_type(schema[n])!=typ:raise ValueError('expression assignment descriptor type mismatch')
            schema.setdefault(n,spec)
            if known and typ=='character' and len(value)>schema[n]['length']:raise ValueError('expression destination buffer is too short')
        elif kind in ('if','subset'):
            _predicate(args['condition'],schema)
        elif kind=='expression_put':
            types=[describe(i,schema)[0] for i in args['items']]
            if len(set(types))!=1:raise ValueError('mixed expression PUT types require separate composition')
            if any(item['kind']=='variable' and type(schema[item['value']]) is dict and schema[item['value']].get('format') for item in args['items']):
                raise ValueError('expression PUT requires unformatted variables')
            if types[0]=='number':sem.sas_put_numeric_list([None]*len(args['items']))
            else:
                items=[{'kind':'literal','value':"'"+item['value'].replace("'","''")+"'"} if item['kind']=='character' else {'kind':'character','value':'x'} for item in args['items']]
                if all(item['kind']=='literal' for item in items):sem.sas_put_literals([item['value'] for item in items])
                else:sem.sas_put_character_list(items)
    if step['where'] is not None:
        _predicate(step['where'],source['schema'])
    return schema,metadata,source


def execute_step(step,tables):
    schema,metadata,source=_step_schema(step,tables);encoding=metadata.get('encoding','ascii');output=[];logs=[]
    rows=source['rows'] if source else [{}]
    if step['where'] is not None:rows=[row for row in rows if _truth(value_of(step['where'],row))]
    for original in rows:
        row={n:' '*s['length'] if column_type(s)=='character' else None for n,s in schema.items()}
        row.update(deepcopy(original));row={n:coerce(v,schema[n],encoding) for n,v in row.items()}
        def perform(op):
            kind,args=op['kind'],op['args']
            if kind=='assign':
                v=value_of(args['value'],row);spec=schema[args['name']]
                if type(v) is str and len(v)>spec['length']:raise ValueError('expression destination buffer is too short')
                if column_type(spec)=='number':sem._sas_expression_number(v)
                row[args['name']]=coerce(v,spec,encoding)
            elif kind=='if':
                branch=args['operation'] if _truth(value_of(args['condition'],row)) else args.get('otherwise')
                if branch is not None:return perform(branch)
            elif kind=='subset':return _truth(value_of(args['condition'],row))
            elif kind=='expression_put':
                values=[value_of(i,row) for i in args['items']]
                if all(type(v) is str for v in values):
                    items=[{'kind':'literal','value':"'"+v.replace("'","''")+"'"} if i['kind']=='character' else {'kind':'character','value':v} for i,v in zip(args['items'],values)]
                    record=(sem.sas_put_literals([i['value'] for i in items]) if all(i['kind']=='literal' for i in items) else sem.sas_put_character_list(items))
                else:record=sem.sas_put_numeric_list(values)
                logs.append(record)
            return True
        if all(perform(op) for op in step['operations']):output.append({n:deepcopy(row[n]) for n in schema})
    return {**metadata,'schema':schema,'rows':output},logs


def _truth(value):
    return bool(sem.sas_expression_truth(value))


def run_program(plan,catalog,legacy):
    selected=validate_program(plan);tables=normalize_catalog({} if catalog is None else catalog);logs=[]
    for step in plan['steps']:
        if id(step) in selected:
            table,records=execute_step(step,tables)
            if step['name']!='_null_':tables[step['name']]=table
            logs.extend(records)
        else:
            result=legacy({'version':2,'steps':[deepcopy(step)],'tickets':[],'matched':[]},tables)
            if set(result)-{'datasets','log'}:raise ValueError('specialized legacy results require separate composition')
            tables=result['datasets'];logs.extend(result['log'])
    return {'datasets':tables,'log':logs}
