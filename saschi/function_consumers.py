"""DS-108 finite typed consumers, isolated from the direct-call profiles."""
from sas_semantics import _sas_consumer_text,_sas_wave2_integer,sas_cats,sas_substrn
from . import function_wave as wave,trim_strip
from .operations import walk_operations

PROFILE='function-consumers-v1'
MARKER='function_profile'
NORMALS=frozenset({'upcase','lowcase','trim','strip','trimn','compbl'})
ITEMS=NORMALS|{'left','right','substrn'}
PREDICATES=frozenset({'missing','verify','anyalpha','anydigit','anyalnum','anyspace','notdigit'})
COMPARISONS=frozenset({'=','eq','^=','~=','<>','ne','<','lt','>','gt','<=','le','>=','ge'})
OPERATIONS=frozenset({MARKER,'declare','assign','read','if','output','put','put_literal','put_character_list','put_numeric_list'})


def has_marker(step):
    return (type(step) is dict and type(step.get('operations')) is list
            and any(type(op) is dict and op.get('kind')==MARKER for op in step['operations']))


def character_form(expr):
    if type(expr) is not dict or expr.get('kind')!='call' or type(expr.get('name')) is not str:
        return False
    return (expr['name'] in NORMALS|{'cats'} and type(expr.get('args')) is list
            and any(type(arg) is dict and arg.get('kind')=='call' for arg in expr['args']))


def predicate_form(value):
    left=value.get('left') if type(value) is dict else None
    return (type(left) is dict and left.get('kind')=='call'
            and type(left.get('name')) is str and left['name'] in PREDICATES)


def checked_call(expr):
    from .functions import FUNCTIONS
    if (type(expr) is not dict or set(expr)!={'kind','name','args'} or expr['kind']!='call'
            or type(expr['name']) is not str or expr['name'] not in FUNCTIONS or type(expr['args']) is not list):
        raise ValueError('function consumer requires an exact registered call shape')
    spec=FUNCTIONS[expr['name']];count=len(expr['args'])
    if count<spec.min_args or spec.max_args>=0 and count>spec.max_args:
        raise ValueError('function consumer call arity is outside its contract')
    return expr['name'],expr['args']


def character_width(expr,schema=None):
    name,args=checked_call(expr)
    if name=='cats':
        if not character_form(expr):raise ValueError('CATS consumer requires at least one nested item')
        for item in args:
            if type(item) is dict and item.get('kind')=='call':
                item_name,_=checked_call(item)
                if item_name not in ITEMS:raise ValueError('unqualified CATS item call')
                if item_name in ('trim','strip'):trim_strip.call_width(item,schema)
                else:wave.call_width(item,schema)
            else:wave.character_argument(item,schema)
        if not any(node.get('kind')=='variable' for node in wave.nodes(expr)):
            evaluate_character(expr,{})
        return 200
    node=expr;depth=0
    while type(node) is dict and node.get('kind')=='call':
        name,args=checked_call(node);depth+=1
        if name not in NORMALS or len(args)!=1 or depth>3:
            raise ValueError('normalization requires2..3qualified unary calls')
        node=args[0]
    if depth<2:raise ValueError('normalization consumer requires at least two calls')
    return wave.character_argument(node,schema)


def validate_predicate(value,schema=None):
    if (type(value) is not dict or set(value)!={'left','op','right'} or type(value['op']) is not str
            or value['op'] not in COMPARISONS or not predicate_form(value)):
        raise ValueError('function IF requires a selected left call and numeric comparison')
    checked_call(value['left']);wave.call_width(value['left'],schema)
    right=value['right']
    if type(right) is not dict or set(right)!={'kind','value'} or right['kind']!='number':
        raise ValueError('function IF requires a numeric literal on the right')
    _sas_wave2_integer(right['value'],0,32767)


def validate_payload(value,schema=None,*,context='other'):
    if context=='assignment' and character_form(value):
        character_width(value,schema);return True
    if context=='condition' and predicate_form(value):
        validate_predicate(value,schema);return True
    wave.validate_expression(value,schema,context=context)
    trim_strip.validate_expression(value,schema,context=context)
    return False


def payloads(op):
    kind,args=op['kind'],op['args']
    if kind=='assign':return [(args.get('value'),'assignment')]
    return [(value,'condition' if kind=='if' and key=='condition' else 'other')
            for key,value in args.items() if key not in ('body','operation','otherwise')]


def contains_candidate(step):
    for op in walk_operations(step['operations']):
        if (op['kind']=='assign' and character_form(op['args'].get('value'))
                or op['kind']=='if' and predicate_form(op['args'].get('condition'))):return True
    return False


def _validate_step(step,version,*,marked,require_consumer):
    if (type(version) is not int or version!=2 or type(step) is not dict or step.get('kind')!='data'
            or type(step.get('inputs')) is not list or len(step['inputs'])>1
            or type(step.get('by')) is not list or step['by']!=[] or step.get('where') is not None
            or type(step.get('retained')) is not dict or step['retained']!={}
            or type(step.get('operations')) is not list):
        raise ValueError('function consumers require unfiltered ordinary version2 DATA execution')
    for node in wave.nodes(step):
        if node.get('kind')=='call':checked_call(node)
    flat=list(walk_operations(step['operations']))
    markers=[op for op in flat if op['kind']==MARKER]
    if marked:
        if (len(markers)!=1 or not step['operations'] or step['operations'][0] is not markers[0]
                or type(markers[0]['args']) is not dict or markers[0]['args']!={'profile':PROFILE}):
            raise ValueError('function consumers require one exact leading profile marker')
    elif markers:raise ValueError('unmarked source step cannot supply a function profile operation')
    consumers=0
    for op in flat:
        if (op['kind'] not in OPERATIONS or type(op['args']) is not dict
                or type(op['line']) is not int or op['line']<1):
            raise ValueError('function consumer operation or source line requires separate composition')
        if op['kind']==MARKER:continue
        for value,context in payloads(op):consumers+=validate_payload(value,context=context)
    if require_consumer and not consumers:raise ValueError('function profile requires a genuine qualified consumer')
    return bool(consumers)


def select_source(step,version=2):
    if not contains_candidate(step):return False
    return _validate_step(step,version,marked=False,require_consumer=True)


def validate_program(plan):
    marked=[step for step in plan['steps'] if has_marker(step)]
    if not marked:return set()
    if (type(plan.get('version')) is not int or plan['version']!=2
            or type(plan.get('tickets')) is not list or plan['tickets']):
        raise ValueError('function consumer profile requires a complete unticketed version2 program')
    selected=set()
    for step in plan['steps']:
        present=has_marker(step)
        actual=_validate_step(step,plan['version'],marked=present,require_consumer=present)
        if actual and not present:raise ValueError('qualified function consumers require their explicit marker')
        if present:selected.add(id(step))
    return selected


def evaluate_character(expr,row):
    """Only a previously validated assignment grammar uses contextual temporaries."""
    if expr['kind']=='variable':return row.get(expr['value'])
    if expr['kind']!='call':return expr['value']
    values=[evaluate_character(arg,row) for arg in expr['args']]
    if expr['name']=='cats':return sas_cats(*values)
    if expr['name']=='substrn':return sas_substrn(*values)
    return _sas_consumer_text(expr['name'],values[0])
