"""Bounded source admission for independently qualified scalar function groups."""
import math
import re

from sas_semantics import _sas_concat_text
from .operations import walk_operations

FAMILIES={'case-search':('DS-096',frozenset({'upcase','lowcase','index','find'})),
          'word-functions':('DS-097',frozenset({'scan','countw'})),
          'character-rewriting':('DS-098',frozenset({'compress','translate','tranwrd'})),
          'missing-summaries':('DS-099',frozenset({'missing','n','nmiss','cmiss','coalesce','coalescec','mean'})),
          'numeric-helpers':('DS-100',frozenset({'abs','sign','ceil','floor'})),
          'calendar-intervals':('DS-101',frozenset({'year','month','day','intck','intnx'})),
          'whitespace-alignment':('DS-102',frozenset({'left','right','compbl','trimn'})),
          'cat-functions':('DS-103',frozenset({'cat','cats','catt'})),
          'character-validation':('DS-104',frozenset({'verify','anyalpha','anydigit','anyalnum','anyspace','notdigit'})),
          'search-extraction':('DS-105',frozenset({'findc','findw','indexc','indexw','substrn'})),
          'row-statistics':('DS-106',frozenset({'median','range','var','std'})),
          'datetime-components':('DS-107',frozenset({'qtr','dhms','datepart','timepart','hour','minute','second'}))}
FAMILIES['text-and-quoting']=('DS-109',frozenset({'propcase','quote','dequote','countc','transtrn'}))
FAMILIES['ascii-positions']=('DS-110',frozenset(('anylower', 'anyupper', 'anypunct', 'anyxdigit', 'notalpha', 'notalnum', 'notspace')))
FAMILIES['selection-and-lookup']=('DS-111',frozenset(('ifn', 'ifc', 'choosen', 'choosec', 'whichn', 'whichc')))
FAMILIES['ranks-and-sums-of-squares']=('DS-112',frozenset(('largest', 'smallest', 'css', 'uss')))
FAMILIES['zero-fuzz-numeric']=('DS-113',frozenset(('ceilz', 'floorz', 'intz', 'roundz', 'modz')))
FAMILIES['calendar-constructors']=('DS-114',frozenset(('hms', 'yyq', 'datejul', 'juldate7')))
NAMES=frozenset(name for _,names in FAMILIES.values() for name in names)
NAME_FAMILY={name:family for family,(_,names) in FAMILIES.items() for name in names}
RESERVED={'_n_','_error_','_all_','_numeric_','_character_','_infile_','_file_','_ods_','_page_','_blankpage_'}


def nodes(value):
    pending=[(value,False)];active=set();count=0
    while pending:
        node,closing=pending.pop()
        if not isinstance(node,(dict,list,tuple)):continue
        if closing:
            active.remove(id(node));continue
        if id(node) in active:raise ValueError('function-wave expression trees cannot contain cycles')
        count+=1
        if count>16384:raise ValueError('function-wave container budget exceeded')
        active.add(id(node));pending.append((node,True))
        if isinstance(node,dict):
            yield node
            pending.extend((v,False) for v in reversed(list(node.values())))
        else:pending.extend((v,False) for v in reversed(node))


def is_call(value):
    return isinstance(value,dict) and value.get('kind')=='call' and isinstance(value.get('name'),str) and value['name'] in NAMES


def selected_family(value):
    pending=[value];seen=set()
    while pending:
        node=pending.pop()
        if not isinstance(node,(dict,list,tuple)) or id(node) in seen:continue
        seen.add(id(node))
        if is_call(node):return NAME_FAMILY[node['name']]
        pending.extend(node.values() if isinstance(node,dict) else node)
    return None


def contains(value):
    return selected_family(value) is not None


def character_argument(arg,schema=None,*,empty=False):
    if type(arg) is not dict or set(arg)!={'kind','value'}:raise ValueError('function wave requires primitive character arguments')
    kind,value=arg['kind'],arg['value']
    if kind=='character':return 0 if empty and value=='' else len(_sas_concat_text(value))
    if (kind!='variable' or type(value) is not str or not re.fullmatch('[a-z_][a-z0-9_]{0,31}',value,re.ASCII)
            or value in RESERVED):raise ValueError('function wave requires ordinary character literals or variables')
    if schema is None:return None
    spec=schema.get(value)
    if type(spec) is not dict or spec.get('type')!='character' or type(spec.get('length')) is not int or not 1<=spec['length']<=32767:
        raise ValueError('function wave requires a preceding character descriptor, width1..32767')
    return spec['length']


def call_width(expr,schema=None):
    if not is_call(expr) or set(expr)!={'kind','name','args'} or type(expr['args']) is not list:
        raise ValueError('function wave requires an exact call shape')
    name,args=expr['name'],expr['args']
    from .function_wave3 import NAMES as WAVE3,call_width as wave3_width
    if name in WAVE3:return wave3_width(expr,schema)
    if name in ('qtr','dhms','datepart','timepart','hour','minute','second'):return datetime_width(expr,schema)
    if name in ('median','range','var','std'):return row_stat_width(expr,schema)
    if name in ('findc','findw','indexc','indexw','substrn'):return search_width(expr,schema)
    if name in ('verify','anyalpha','anydigit','anyalnum','anyspace','notdigit'):
        minimum,maximum=(2,32) if name=='verify' else (1,2)
        if not minimum<=len(args)<=maximum:raise ValueError('character validation call arity is outside its bounded contract')
        for arg in args if name=='verify' else args[:1]:character_argument(arg,schema)
        if name!='verify' and len(args)==2:
            numeric_argument(args[1],schema,missing=True)
            if args[1]['kind'] in ('number','missing'):
                from sas_semantics import _sas_wave2_integer
                _sas_wave2_integer(args[1]['value'],missing=True)
        return None
    if name in ('cat','cats','catt'):
        if not 1<=len(args)<=32:raise ValueError('CAT family requires1..32primitive character arguments')
        widths=[character_argument(arg,schema) for arg in args]
        if name=='cat' and all(width is not None for width in widths) and sum(widths)>200:
            raise ValueError('CAT raw argument width exceeds200bytes')
        if all(arg['kind']=='character' for arg in args):
            from sas_semantics import sas_cat,sas_cats,sas_catt
            {'cat':sas_cat,'cats':sas_cats,'catt':sas_catt}[name](*(arg['value'] for arg in args))
        return 200
    if name in ('left','right','compbl','trimn'):
        if len(args)!=1:raise ValueError('whitespace/alignment requires one primitive character argument')
        return character_argument(args[0],schema)
    if name in ('scan','countw'):return word_width(expr,schema)
    if name in ('compress','translate','tranwrd'):return rewriting_width(expr,schema)
    if name in ('missing','n','nmiss','cmiss','coalesce','coalescec','mean'):return summary_width(expr,schema)
    if name in ('abs','sign','ceil','floor'):return numeric_width(expr,schema)
    if name in ('year','month','day','intck','intnx'):return calendar_width(expr,schema)
    minimum,maximum=(1,1) if name in ('upcase','lowcase') else (2,2) if name=='index' else (2,4)
    if not minimum<=len(args)<=maximum:raise ValueError('case/search call arity is outside its bounded contract')
    widths=[character_argument(arg,schema) for arg in args[:minimum]]
    if name=='find':
        modifiers=None;start=None
        for arg in args[2:]:
            if type(arg) is not dict or set(arg)!={'kind','value'}:raise ValueError('FIND optional arguments require literals')
            if arg['kind']=='character':
                value=arg['value']
                if modifiers is not None or type(value) is not str or len(value)>8 or any(c not in 'iItT' for c in value):
                    raise ValueError('FIND supports one literal I/T modifier argument')
                modifiers=value
            elif arg['kind']=='number':
                value=arg['value']
                if start is not None or type(value) not in (int,float) or not 0<=value<=2147483647 or not math.isfinite(value) or value!=int(value):
                    raise ValueError('FIND supports one integral forward literal start,0..2147483647')
                start=value
            else:raise ValueError('FIND optional arguments require literal I/T or a forward integer start')
        if modifiers and 't' in modifiers.lower() and args[1]['kind']=='character' and not args[1]['value'].rstrip(' '):
            raise ValueError('FIND empty trimmed needle requires separate characterization')
    return widths[0] if name in ('upcase','lowcase') else None



def search_width(expr,schema=None):
    """DS-105 primitive operands and explicit, independently qualified controls."""
    from sas_semantics import _sas_wave2_integer
    name,args=expr['name'],expr['args']
    lower,upper={'findc':(2,4),'findw':(3,5),'indexc':(2,32),'indexw':(2,3),'substrn':(2,3)}[name]
    if not lower<=len(args)<=upper:raise ValueError('search/extraction call arity is outside its bounded contract')
    width=character_argument(args[0],schema)
    if name=='substrn':
        for arg in args[1:]:
            numeric_argument(arg,schema,missing=True)
            if arg['kind'] in ('number','missing'):_sas_wave2_integer(arg['value'],missing=True)
        return width
    for arg in args[1:] if name=='indexc' else args[1:2]:character_argument(arg,schema)
    if name=='findc':
        size=character_argument(args[1],schema)
        if size is not None and size>64:raise ValueError('FINDC character set exceeds64bytes')
    if name=='indexw' and len(args)==3:literal_option(args[2],maximum=1,choices={' '})
    if name=='findw':
        delimiters=literal_option(args[2])
        if any('A'<=c<='Z' or 'a'<=c<='z' for c in delimiters):raise ValueError('FINDW alphabetic delimiters need separate evidence')
    if name in ('findc','findw'):
        modifiers=False;start=False
        for arg in args[2 if name=='findc' else 3:]:
            if type(arg) is dict and arg.get('kind')=='character':
                if modifiers:raise ValueError('duplicate search modifiers')
                literal_option(arg,maximum=2 if name=='findc' else 1,empty=True,choices={'','I','K','IK','KI'} if name=='findc' else {'','I'})
                modifiers=True
            else:
                if start:raise ValueError('duplicate search start')
                numeric_argument(arg,schema)
                if arg['kind']=='number':_sas_wave2_integer(arg['value'])
                start=True
    return None



def row_stat_width(expr,schema=None):
    from sas_semantics import _sas_wave2_integer
    args=expr['args']
    if not 1<=len(args)<=32:raise ValueError('row statistics require1..32primitive numeric operands')
    for arg in args:
        numeric_argument(arg,schema,missing=True)
        if arg['kind'] in ('number','missing'):_sas_wave2_integer(arg['value'],-1000000,1000000,missing=True)
    return None



def datetime_width(expr,schema=None):
    from sas_semantics import _sas_wave2_integer,SAS_CALENDAR_MIN_DAY,SAS_CALENDAR_MAX_DAY
    name,args=expr['name'],expr['args']
    if len(args)!=(4 if name=='dhms' else 1):raise ValueError('datetime component call requires its bounded argument count')
    bounds=([(SAS_CALENDAR_MIN_DAY,SAS_CALENDAR_MAX_DAY),(0,23),(0,59),(0,59)] if name=='dhms' else
            [(SAS_CALENDAR_MIN_DAY,SAS_CALENDAR_MAX_DAY)] if name=='qtr' else
            [(SAS_CALENDAR_MIN_DAY*86400,SAS_CALENDAR_MAX_DAY*86400+86399)])
    for arg,(low,high) in zip(args,bounds):
        numeric_argument(arg,schema,missing=True,limit=max(abs(low),abs(high)))
        if arg['kind'] in ('number','missing'):_sas_wave2_integer(arg['value'],low,high,missing=True)
    return None


def numeric_argument(arg,schema=None,*,missing=False,tags=False,limit=2147483647):
    if type(arg) is not dict or set(arg)!={'kind','value'}:raise ValueError('function requires a primitive numeric operand')
    kind,value=arg['kind'],arg['value']
    if kind=='number':
        if type(value) not in (int,float) or abs(value)>limit or not math.isfinite(value):
            raise ValueError('function numeric literal is outside the bounded finite domain')
    elif kind=='missing':
        if not missing or value is not None:raise ValueError('function ordinary missing operand requires separate admission')
    elif kind=='tagged_missing':
        from sas_semantics import sas_numeric_order
        if not tags or type(value) is not dict or set(value)!={'missing'}:
            raise ValueError('function requires an admitted exact tagged missing shape')
        sas_numeric_order(value)
    elif kind=='variable':
        if type(value) is not str or not re.fullmatch('[a-z_][a-z0-9_]{0,31}',value,re.ASCII) or value in RESERVED:
            raise ValueError('function requires an ordinary numeric variable')
        if schema is not None:
            spec=schema.get(value,'number')
            if spec!='number' and (type(spec) is not dict or spec.get('type')!='number'):
                raise ValueError('function requires a numeric variable descriptor')
    else:raise ValueError('function requires a primitive numeric literal or variable')


def literal_option(arg,*,maximum=64,empty=False,choices=None):
    if type(arg) is not dict or set(arg)!={'kind','value'} or arg['kind']!='character' or type(arg['value']) is not str:
        raise ValueError('function control requires a character literal')
    value=arg['value']
    if value or not empty:_sas_concat_text(value)
    if len(value)>maximum or choices is not None and value.upper() not in choices:
        raise ValueError('function literal control is outside its bounded subset')
    return value


def word_width(expr,schema=None):
    name,args=expr['name'],expr['args']
    lower,upper=(3,4) if name=='scan' else (2,3)
    if not lower<=len(args)<=upper:raise ValueError('word functions require explicit delimiter syntax')
    width=character_argument(args[0],schema)
    if name=='scan':
        numeric_argument(args[1],schema)
        if args[1]['kind']=='number' and (args[1]['value']==0 or args[1]['value']!=int(args[1]['value'])):
            raise ValueError('SCAN requires a nonzero integral count')
    literal_option(args[2] if name=='scan' else args[1])
    if len(args)==upper:literal_option(args[-1],maximum=1,empty=True,choices={'','M'})
    return width if name=='scan' else None


def rewriting_width(expr,schema=None):
    name,args=expr['name'],expr['args']
    if not (1<=len(args)<=3 if name=='compress' else len(args)==3):
        raise ValueError('character rewriting requires its bounded argument count')
    width=character_argument(args[0],schema)
    if name=='compress':
        if len(args)>1:literal_option(args[1])
        if len(args)>2:literal_option(args[2],maximum=2,empty=True,choices={'','I','K','IK','KI'})
    elif name=='translate':
        target,source=(literal_option(arg) for arg in args[1:])
        if len(target)!=len(source) or len(set(source))!=len(source):
            raise ValueError('TRANSLATE requires equal literal lists and distinct FROM bytes')
    else:
        target=literal_option(args[1]);replacement=literal_option(args[2],empty=True)
        if args[0]['kind']=='character':
            from sas_semantics import sas_tranwrd
            sas_tranwrd(args[0]['value'],target,replacement)
    return 200 if name=='tranwrd' else width


def summary_width(expr,schema=None):
    name,args=expr['name'],expr['args']
    if not (len(args)==1 if name=='missing' else 1<=len(args)<=32):
        raise ValueError('missing/summary calls require their bounded argument count')
    for arg in args:
        kind=arg.get('kind') if type(arg) is dict else None
        spec=(schema or {}).get(arg.get('value')) if kind=='variable' and type(arg.get('value')) is str else None
        character=kind=='character' or kind=='variable' and type(spec) is dict and spec.get('type')=='character'
        if name=='coalescec' or name in ('missing','cmiss') and character:
            character_argument(arg,schema,empty=True)
        else:
            numeric_argument(arg,schema,missing=True,tags=name in ('missing','n','nmiss','cmiss'))
            if name=='mean' and kind=='number' and arg['value']!=int(arg['value']):
                raise ValueError('MEAN fractional inputs require a separate numerical contract')
    if name=='coalescec' and all(arg['kind']=='character' for arg in args):
        from sas_semantics import sas_coalescec
        sas_coalescec(*(arg['value'] for arg in args))
    return 200 if name=='coalescec' else None


def numeric_width(expr,schema=None):
    args=expr['args']
    if len(args)!=1:raise ValueError('numeric helper requires one primitive operand')
    numeric_argument(args[0],schema,missing=True)
    if args[0]['kind'] in ('number','missing'):
        from sas_semantics import _sas_normal_operand
        _sas_normal_operand(args[0]['value'])
    return None


def calendar_width(expr,schema=None):
    from sas_semantics import _sas_source_date, _sas_interval_increment, sas_source_intnx
    name,args=expr['name'],expr['args']
    if name in ('year','month','day'):
        if len(args)!=1:raise ValueError('calendar component requires one date')
        dates=args
    else:
        if not 3<=len(args)<=4:raise ValueError('calendar interval call requires three or four arguments')
        literal_option(args[0],choices={'DAY','MONTH','QTR','YEAR'})
        dates=args[1:3] if name=='intck' else args[1:2]
        if len(args)==4:
            literal_option(args[3],choices={'D','DISCRETE'} if name=='intck' else {'B','BEGINNING','E','END','S','SAME','SAMEDAY'})
        if name=='intnx':
            numeric_argument(args[2],schema,missing=True)
            if args[2]['kind'] in ('number','missing'):_sas_interval_increment(args[2]['value'])
    for arg in dates:
        numeric_argument(arg,schema,missing=True)
        if arg['kind'] in ('number','missing'):_sas_source_date(arg['value'])
    if name=='intnx' and all(arg['kind']!='variable' for arg in args):
        sas_source_intnx(*(arg['value'] for arg in args))
    return None


def validate_expression(value,schema=None,*,context='other'):
    family=selected_family(value)
    if family is None:return
    try:
        if context!='assignment' or not is_call(value):raise ValueError('function-wave calls require a direct assignment RHS; temporary consumers need separate evidence')
        call_width(value,schema)
    except ValueError as error:
        error.family=family;raise


def validate_step(step,version=2):
    family=selected_family(step)
    if family is None:return
    try:_validate_selected_step(step,version)
    except ValueError as error:
        if not hasattr(error,'family'):error.family=family
        raise


def _validate_selected_step(step,version):
    for _ in nodes(step):pass
    if type(version) is not int or version!=2 or step.get('kind')!='data':raise ValueError('function wave requires version2 ordinary DATA execution')
    if step.get('where') or step.get('by') or step.get('retained') or len(step.get('inputs',[]))>1:
        raise ValueError('function wave WHERE,BY,RETAIN and multiple inputs require separate composition')
    allowed={'declare','assign','read','if','do_counted','output','put','put_literal','put_character_list','put_numeric_list'}
    for op in walk_operations(step['operations']):
        if op['kind'] not in allowed:raise ValueError('function wave operation requires separate composition')
        args=op['args']
        payloads=[(args.get('value'),'assignment')] if op['kind']=='assign' else [
            (v,'other') for k,v in args.items() if k not in ('body','operation','otherwise')]
        for value,context in payloads:validate_expression(value,context=context)
