"""DS-115 exact finite consumers, with preflight before recursive runtime work."""
import math
import re

import sas_semantics as semantics
from . import function_wave as wave
from .function_wave3 import POSITION_NAMES

PROFILE='function-consumers-v2'
MARKER='function_profile'
PREDICATES=frozenset({'missing','verify','anyalpha','anydigit','anyalnum','anyspace','notdigit'})|POSITION_NAMES
COMPARISONS=frozenset({'=','eq','^=','~=','<>','ne','<','lt','>','gt','<=','le','>=','ge'})
STEP_FIELDS={'kind','name','line','inputs','by','operations','nodupkey','where','retained','lengths','display_names'}
OPERATIONS={MARKER,'declare','assign','read','if','output','put_literal','put_character_list','put_numeric_list'}


def loose_nodes(value):
    pending=[value];seen=set()
    while pending:
        node=pending.pop()
        if not isinstance(node,(dict,list,tuple)) or id(node) in seen:continue
        seen.add(id(node))
        if isinstance(node,dict):
            yield node;pending.extend(node.values())
        else:pending.extend(node)


def assignment_form(expr):
    if type(expr) is not dict or expr.get('kind')!='call' or type(expr.get('name')) is not str or type(expr.get('args')) is not list:return False
    name,args=expr['name'],expr['args']
    if name=='cats':
        return any(type(arg) is dict and arg.get('kind')=='call' and type(arg.get('name')) is str and arg['name'] in ('propcase','dequote') for arg in args)
    return name in ('ifc','ifn','transtrn') and any(type(arg) is dict and arg.get('kind') in ('call','comparison') for arg in args)


def character_form(expr):
    return assignment_form(expr) and expr['name']!='ifn'


def predicate_form(value):
    left=value.get('left') if type(value) is dict else None
    return type(left) is dict and left.get('kind')=='call' and type(left.get('name')) is str and left['name'] in PREDICATES


def contains_candidate(value):
    for node in loose_nodes(value):
        if assignment_form(node):return True
        if node.get('kind')=='if':
            test=node.get('args',{}).get('condition') if type(node.get('args')) is dict else None
            if predicate_form(test) and test['left']['name'] in POSITION_NAMES:return True
    return False


def selected_program(plan):
    for node in loose_nodes(plan):
        if node.get('kind')==MARKER and type(node.get('args')) is dict and node['args'].get('profile')==PROFILE:return True
    return contains_candidate(plan)


def checked_call(expr):
    from .functions import FUNCTIONS
    if (type(expr) is not dict or set(expr)!={'kind','name','args'} or expr['kind']!='call'
            or type(expr['name']) is not str or expr['name'] not in FUNCTIONS or type(expr['args']) is not list):
        raise ValueError('selection consumer requires an exact registered call shape')
    spec=FUNCTIONS[expr['name']];size=len(expr['args'])
    if size>33 or size<spec.min_args or spec.max_args>=0 and size>spec.max_args:
        raise ValueError('selection consumer call arity exceeds its qualified bounds')
    return expr['name'],expr['args']


def preflight(step):
    pending=[(step,0,0,False)];active=set();containers=calls=0
    while pending:
        node,depth,levels,closing=pending.pop()
        if not isinstance(node,(dict,list,tuple)):continue
        if closing:active.remove(id(node));continue
        if id(node) in active:raise ValueError('selection consumer trees cannot contain cycles')
        containers+=1
        if containers>16384 or depth>64:raise ValueError('selection consumer container/depth budget exceeded')
        if type(node) is dict and node.get('kind')=='call':
            checked_call(node);calls+=1;levels+=1
            if calls>128 or levels>2:raise ValueError('selection consumer call budget/depth exceeded')
        active.add(id(node));pending.append((node,depth,levels,True))
        children=list(node.values()) if isinstance(node,dict) else list(node)
        if len(children)>16384:raise ValueError('selection consumer container budget exceeded')
        pending.extend((child,depth+1,levels,False) for child in reversed(children))


def ordinary_name(value,*,dataset=False):
    if (type(value) is not str or not re.fullmatch('[a-z_][a-z0-9_]{0,31}',value,re.ASCII)
            or not dataset and value in wave.RESERVED):
        raise ValueError('selection consumer requires normalized ordinary names')


def primitive(expr,schema=None):
    if type(expr) is not dict or set(expr)!={'kind','value'}:raise ValueError('selection consumer requires a primitive leaf')
    kind,value=expr['kind'],expr['value']
    if kind=='variable':ordinary_name(value)
    elif kind=='character':
        if type(value) is not str or len(value)>32767 or any(not 32<=ord(c)<=126 for c in value):raise ValueError('selection consumer requires bounded printable ASCII')
    elif kind=='number':
        try:valid=type(value) in (int,float) and math.isfinite(value)
        except OverflowError:valid=False
        if not valid:raise ValueError('selection consumer requires finite numeric literals')
    elif kind=='missing':
        if value is not None:raise ValueError('selection consumer ordinary missing must be null')
    elif kind=='tagged_missing':wave.numeric_argument(expr,schema,missing=True,tags=True)
    else:raise ValueError('selection consumer primitive kind is outside its grammar')


def ifc_comparison(test):
    if type(test) is not dict or set(test)!={'left','op','right'} or type(test.get('op')) is not str or test['op'] not in ('=','eq'):return False
    left,right=test['left'],test['right']
    return (type(left) is dict and left.get('kind')=='call' and left.get('name')=='notalnum'
            and type(right) is dict and set(right)=={'kind','value'} and right['kind']=='number'
            and type(right['value']) in (int,float) and right['value']==0)


def validate_assignment(expr,schema=None):
    if not assignment_form(expr):
        if type(expr) is dict and expr.get('kind')=='call':
            name,args=checked_call(expr)
            if name in wave.NAMES:wave.call_width(expr,schema)
            elif name=='put':
                if args[1]!={'kind':'format','name':'date','w':9,'d':0}:raise ValueError('selection consumer only qualifies legacy PUT DATE9')
                wave.numeric_argument(args[0],schema,missing=True,limit=max(abs(semantics.SAS_CALENDAR_MIN_DAY),abs(semantics.SAS_CALENDAR_MAX_DAY)))
                if args[0]['kind']!='variable':semantics._sas_source_date(args[0]['value'])
            else:raise ValueError('legacy or specialized call requires a separate consumer contract')
        else:primitive(expr,schema)
        return False
    name,args=checked_call(expr)
    if name=='ifc':
        if len(args)!=3 or type(args[0]) is not dict or args[0].get('kind')!='comparison' or set(args[0])!={'kind','left','op','right'}:
            raise ValueError('IFC consumer requires one exact NOTALNUM zero comparison and two primitive choices')
        test={key:args[0][key] for key in ('left','op','right')}
        if not ifc_comparison(test):raise ValueError('IFC consumer only qualifies NOTALNUM=0 or EQ0')
        checked_call(test['left']);wave.call_width(test['left'],schema)
        for choice in args[1:]:
            width=wave.character_argument(choice,schema)
            if width is not None and width>200:raise ValueError('IFC consumer choice descriptor exceeds200bytes')
    elif name=='ifn':
        if len(args)!=3:raise ValueError('IFN consumer requires exactly3arguments')
        for leaf in args[:2]:wave.numeric_argument(leaf,schema,missing=True,limit=1000000)
        child_name,_=checked_call(args[2])
        if child_name!='largest':raise ValueError('IFN consumer requires false-branch LARGEST')
        wave.call_width(args[2],schema)
    elif name=='cats':
        for item in args:
            if type(item) is dict and item.get('kind')=='call':
                item_name,_=checked_call(item)
                if item_name not in ('propcase','dequote'):raise ValueError('unqualified CATS consumer item')
                wave.call_width(item,schema)
            else:wave.character_argument(item,schema)
    else:
        if len(args)!=3:raise ValueError('TRANSTRN deletion consumer requires3arguments')
        wave.character_argument(args[0],schema);width=wave.character_argument(args[1],schema)
        if width is not None and width>64:raise ValueError('TRANSTRN target descriptor exceeds64bytes')
        child_name,child_args=checked_call(args[2])
        if child_name!='trimn' or child_args!=[{'kind':'character','value':' '}]:
            raise ValueError('TRANSTRN deletion requires TRIMN over exactly one literal blank')
    if not any(node.get('kind')=='variable' for node in wave.nodes(expr)):evaluate_assignment(expr,{})
    return True


def character_width(expr,schema=None):
    if not character_form(expr):raise ValueError('selection consumer requires a qualified character root')
    validate_assignment(expr,schema);return 200


def validate_condition(test,schema=None):
    if type(test) is not dict or type(test.get('op')) is not str:raise ValueError('selection consumer condition requires an exact comparison')
    op=test['op']
    if predicate_form(test):
        if set(test)!={'left','op','right'} or op not in COMPARISONS:raise ValueError('function IF requires a qualified comparison')
        checked_call(test['left']);wave.call_width(test['left'],schema)
        right=test['right']
        if type(right) is not dict or set(right)!={'kind','value'} or right['kind']!='number':raise ValueError('function IF requires a right numeric literal')
        semantics._sas_wave2_integer(right['value'],0,32767)
        return True
    if op=='truth' and set(test)=={'left','op'}:primitive(test['left'],schema)
    elif op in COMPARISONS and set(test)=={'left','op','right'}:
        primitive(test['left'],schema);primitive(test['right'],schema)
    else:raise ValueError('selection consumer condition is outside its finite grammar')
    return False


def validate_payload(value,schema=None,*,context='other'):
    if context=='assignment':return validate_assignment(value,schema)
    if context=='condition':return validate_condition(value,schema)
    if any(node.get('kind') in ('call','comparison') for node in wave.nodes(value)):
        raise ValueError('selection consumer calls are restricted to qualified assignments and IF comparisons')
    return False


def _validate_step(step,version,*,marked,require_consumer):
    preflight(step)
    if (type(version) is not int or version!=2 or type(step) is not dict or set(step)!=STEP_FIELDS
            or step['kind']!='data' or type(step['line']) is not int or step['line']<1
            or type(step['inputs']) is not list or len(step['inputs'])>1 or type(step['operations']) is not list
            or type(step['by']) is not list or step['by'] or step['where'] is not None
            or type(step['retained']) is not dict or step['retained'] or step['nodupkey'] is not False
            or type(step['lengths']) is not dict or type(step['display_names']) is not dict):
        raise ValueError('selection consumers require exact ordinary unfiltered version2 DATA steps')
    ordinary_name(step['name'],dataset=True)
    for name in step['inputs']:ordinary_name(name,dataset=True)
    for name,width in step['lengths'].items():
        ordinary_name(name)
        if type(width) is not int or not 1<=width<=32767:raise ValueError('selection consumer requires bounded storage widths')
    for name,display in step['display_names'].items():
        ordinary_name(name)
        if type(display) is not str or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,31}',display,re.ASCII):raise ValueError('invalid selection consumer display name')
    pending=[(op,True) for op in reversed(step['operations'])];flat=[];consumer_count=reads=0
    while pending:
        op,top=pending.pop();flat.append(op)
        if len(flat)>256-(1 if require_consumer and not marked else 0):raise ValueError('selection consumer operation budget exceeded')
        if (type(op) is not dict or set(op)!={'kind','line','args'} or type(op['kind']) is not str
                or op['kind'] not in OPERATIONS or type(op['line']) is not int or op['line']<1 or type(op['args']) is not dict):
            raise ValueError('selection consumer requires exact qualified operation objects')
        kind,args=op['kind'],op['args']
        if not top and kind not in ('assign','if'):raise ValueError('selection consumer IF actions are assignment/IF only')
        if kind==MARKER:
            if not marked or op is not step['operations'][0] or args!={'profile':PROFILE}:raise ValueError('selection consumer requires one exact leading marker')
        elif kind=='assign':
            if set(args)!={'name','value'}:raise ValueError('selection consumer assignment fields are exact')
            ordinary_name(args['name']);consumer_count+=validate_assignment(args['value'])
        elif kind=='if':
            if set(args) not in ({'condition','operation'},{'condition','operation','otherwise'}):raise ValueError('selection consumer IF fields are exact')
            consumer_count+=validate_condition(args['condition'])
            if 'otherwise' in args:pending.append((args['otherwise'],False))
            pending.append((args['operation'],False))
        elif kind=='declare':
            from .values import descriptor
            if set(args)!={'name','spec'}:raise ValueError('selection consumer declaration fields are exact')
            ordinary_name(args['name']);descriptor(args['spec'])
        elif kind=='read':
            if set(args)!={'datasets'} or args['datasets']!=step['inputs'] or not step['inputs']:raise ValueError('selection consumer driving read must match its single input')
            reads+=1
        elif kind=='output':
            if set(args)!={'target'} or args['target'] not in (None,step['name']) or step['name']=='_null_':raise ValueError('selection consumer OUTPUT must name its DATA destination')
        elif kind=='put_literal':
            if set(args)!={'literals'} or type(args['literals']) is not list:raise ValueError('selection consumer literal PUT shape is exact')
            semantics.sas_put_literals(args['literals'])
        elif kind=='put_character_list':
            if set(args)!={'items'} or type(args['items']) is not list or not 1<=len(args['items'])<=32:raise ValueError('selection consumer character PUT requires bounded primitive items')
            for item in args['items']:wave.character_argument(item)
        else:
            if set(args)!={'names'} or type(args['names']) is not list or not 1<=len(args['names'])<=32:raise ValueError('selection consumer numeric PUT requires bounded ordinary names')
            for name in args['names']:ordinary_name(name)
    markers=[op for op in flat if op['kind']==MARKER]
    if marked and len(markers)!=1 or not marked and markers:raise ValueError('selection consumer marker is missing or repeated')
    if reads!=len(step['inputs']):raise ValueError('selection consumer requires exactly its driving read')
    if require_consumer and not consumer_count:raise ValueError('selection consumer marker requires a genuine qualified consumer')
    return bool(consumer_count)


def select_source(step,version=2):
    if not contains_candidate(step):return False
    return _validate_step(step,version,marked=False,require_consumer=True)


def validate_program(plan):
    if (type(plan) is not dict or set(plan)!={'version','steps','tickets','matched'}
            or type(plan['version']) is not int or plan['version']!=2 or type(plan['steps']) is not list
            or not 1<=len(plan['steps'])<=16 or type(plan['tickets']) is not list or plan['tickets']
            or type(plan['matched']) is not list or len(plan['matched'])>4096):
        raise ValueError('selection consumers require an exact unticketed version2 program')
    for match in plan['matched']:
        if (type(match) not in (list,tuple) or len(match)!=3 or type(match[0]) is not str or type(match[1]) is not str
                or type(match[2]) is not int or match[2]<1):raise ValueError('selection consumer source provenance requires exact rows')
    selected=set()
    for step in plan['steps']:
        marked=type(step) is dict and type(step.get('operations')) is list and any(type(op) is dict and op.get('kind')==MARKER for op in step['operations'])
        actual=_validate_step(step,plan['version'],marked=marked,require_consumer=marked)
        if actual and not marked:raise ValueError('qualified selection consumers require their marker')
        if marked:selected.add(id(step))
    return selected


def evaluate_assignment(expr,row):
    """Evaluate only the validated finite grammar using canonical scalar helpers."""
    if expr['kind']=='variable':return row.get(expr['value'])
    if expr['kind']=='comparison':return float(evaluate_assignment(expr['left'],row)==evaluate_assignment(expr['right'],row))
    if expr['kind']!='call':return expr['value']
    from .functions import apply
    return apply(expr['name'],[evaluate_assignment(arg,row) for arg in expr['args']])


def evaluate_character(expr,row):
    return evaluate_assignment(expr,row)
