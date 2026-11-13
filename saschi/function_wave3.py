"""Typed primitive admission for independently qualified wave-3 families."""
import sas_semantics as semantics

NAMES=frozenset({'propcase','quote','dequote','countc','transtrn'})

def apply(name,values):
    if name not in NAMES:raise ValueError('unqualified wave3 function')
    try:return getattr(semantics,'sas_'+name)(*values)
    except TypeError as error:raise ValueError('wave3 call arity or operand shape is outside its contract') from error

def text_width(expr,schema=None):
    from .function_wave import character_argument,literal_option
    name,args=expr['name'],expr['args']
    limits={'propcase':(2,2),'quote':(1,2),'dequote':(1,1),'countc':(2,3),'transtrn':(3,3)}
    if name not in limits or not limits[name][0]<=len(args)<=limits[name][1]:
        raise ValueError('wave3 primitive function arity is outside its contract')
    widths=[character_argument(arg,schema) for arg in args]
    if name=='propcase' and widths[1] is not None and not 1<=widths[1]<=64:
        raise ValueError('PROPCASE delimiter width requires1..64bytes')
    if name=='quote' and len(args)==2:literal_option(args[1],maximum=1,choices={'"',"'"})
    if name=='countc':
        if widths[1] is not None and widths[1]>64:raise ValueError('COUNTC character set exceeds64bytes')
        if len(args)==3:
            modifier=literal_option(args[2],maximum=3)
            if any(c not in 'IVT' for c in modifier.upper()):raise ValueError('COUNTC supports literal I/V/T modifiers')
    if name=='transtrn' and any(w is not None and w>64 for w in widths[1:]):
        raise ValueError('TRANSTRN target/replacement descriptor exceeds64bytes')
    if all(arg['kind']=='character' for arg in args):apply(name,[arg['value'] for arg in args])
    return widths[0] if name in ('propcase','dequote') else 200 if name in ('quote','transtrn') else None

POSITION_NAMES=frozenset(('anylower','anyupper','anypunct','anyxdigit','notalpha','notalnum','notspace'))
NAMES=NAMES|POSITION_NAMES

def position_width(expr,schema=None):
    from .function_wave import character_argument,numeric_argument
    name,args=expr['name'],expr['args']
    if not 1<=len(args)<=2:raise ValueError('ASCII position requires1..2primitive arguments')
    character_argument(args[0],schema)
    if len(args)==2:
        numeric_argument(args[1],schema,missing=name!='anypunct')
        if args[1]['kind'] in ('number','missing'):
            semantics._sas_wave2_integer(args[1]['value'],missing=name!='anypunct')
    return None

def call_width(expr,schema=None):
    if expr['name'] in POSITION_NAMES:return position_width(expr,schema)
    if expr['name'] in SELECTION_NAMES:return selection_width(expr,schema)
    if expr['name'] in RANK_NAMES:return rank_width(expr,schema)
    if expr['name'] in ZERO_NAMES:return zero_width(expr,schema)
    if expr['name'] in CALENDAR_NAMES:return calendar_constructor_width(expr,schema)
    return text_width(expr,schema)

SELECTION_NAMES=frozenset(('ifn','ifc','choosen','choosec','whichn','whichc'))
NAMES=NAMES|SELECTION_NAMES

def selection_width(expr,schema=None):
    from .function_wave import character_argument,numeric_argument
    name,args=expr['name'],expr['args']
    conditional=name in ('ifn','ifc');character=name in ('ifc','choosec','whichc')
    if not (3<=len(args)<=4 if conditional else 2<=len(args)<=32):
        raise ValueError('selection call arity is outside its bounded contract')
    numeric=args if not character else args[:1] if name!='whichc' else []
    characters=args if name=='whichc' else args[1:] if character else []
    for arg in numeric:numeric_argument(arg,schema,missing=True,limit=1000000)
    for arg in characters:
        width=character_argument(arg,schema)
        if width is not None and width>200:raise ValueError('selection character descriptor exceeds200bytes')
    if all(arg['kind']!='variable' for arg in args):apply(name,[arg['value'] for arg in args])
    return 200 if name in ('ifc','choosec') else None

RANK_NAMES=frozenset(('largest','smallest','css','uss'))
NAMES=NAMES|RANK_NAMES

def rank_width(expr,schema=None):
    from .function_wave import numeric_argument
    name,args=expr['name'],expr['args'];ranked=name in ('largest','smallest')
    if not (2<=len(args)<=33 if ranked else 1<=len(args)<=32):
        raise ValueError('rank/squares requires1..32measurement arguments and a rank where applicable')
    if ranked:
        numeric_argument(args[0],schema)
        if args[0]['kind']=='number':semantics._sas_wave2_integer(args[0]['value'],1,len(args)-1)
    for arg in args[1:] if ranked else args:
        numeric_argument(arg,schema,missing=True,limit=1000000)
        if arg['kind']!='variable':semantics._sas_wave2_integer(arg['value'],-1000000,1000000,missing=True)
    if all(arg['kind']!='variable' for arg in args):apply(name,[arg['value'] for arg in args])
    return None

ZERO_NAMES=frozenset(('ceilz','floorz','intz','roundz','modz'))
NAMES=NAMES|ZERO_NAMES

def zero_width(expr,schema=None):
    from .function_wave import numeric_argument
    name,args=expr['name'],expr['args']
    if not (len(args)==2 if name=='modz' else 1<=len(args)<=2 if name=='roundz' else len(args)==1):
        raise ValueError('zero-fuzz call arity is outside its bounded contract')
    for index,arg in enumerate(args):
        numeric_argument(arg,schema,missing=True,limit=1000000)
        if arg['kind']!='variable':
            if index==0:semantics._sas_wave3_zero_value(arg['value'])
            else:semantics._sas_wave3_power(arg['value'],signed=name=='modz')
    return None

def zero_source_underflows(statements):
    """Retain nonzero source text before the binary64 atom loses its magnitude."""
    from decimal import Decimal,InvalidOperation
    from .parser import Kind
    import re
    pattern=re.compile(r'(?<![A-Za-z0-9_.])[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][-+]?[0-9]+)?(?![A-Za-z0-9_.])')
    for statement in statements:
        for token in statement.tokens:
            if token.kind in (Kind.STRING,Kind.DATA):continue
            for match in pattern.finditer(token.text):
                raw=match.group()
                try:underflow=float(raw)==0 and Decimal(raw)!=0
                except (ValueError,OverflowError,InvalidOperation):underflow=True
                if underflow:yield statement

CALENDAR_NAMES=frozenset(('hms','yyq','datejul','juldate7'))
NAMES=NAMES|CALENDAR_NAMES

def calendar_constructor_width(expr,schema=None):
    from .function_wave import numeric_argument
    name,args=expr['name'],expr['args']
    bounds={'hms':[(0,23),(0,59),(0,59)],'yyq':[(1753,3999),(1,4)],
            'datejul':[(1753001,3999365)],'juldate7':[(semantics.SAS_CALENDAR_MIN_DAY,semantics.SAS_CALENDAR_MAX_DAY)]}[name]
    if len(args)!=len(bounds):raise ValueError('calendar constructor requires its bounded argument count')
    for arg,(low,high) in zip(args,bounds):
        numeric_argument(arg,schema,missing=True,limit=max(abs(low),abs(high)))
        if arg['kind']!='variable':semantics._sas_wave2_integer(arg['value'],low,high,missing=True)
    if all(arg['kind']!='variable' for arg in args):apply(name,[arg['value'] for arg in args])
    return None
