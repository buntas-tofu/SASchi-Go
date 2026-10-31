"""DS-064/065 separately marked bounded scalar program-counter flow."""
from copy import deepcopy
from dataclasses import asdict
from enum import Enum
import re

from sas_semantics import (sas_counted_control, sas_counted_capture,
                           sas_put_numeric_list, sas_put_literals, sas_numeric_order, sas_mod, sas_input_records, sas_input_number)
from .counted import parse_control, validate_control, evaluate_control
from .parser import split_statements, ParseError, Kind
from .projection import dataset, declaration, names_valid, selected_names, project_table
from .values import normalize_catalog, column_type
from .input_list import names_valid as input_names_valid, source_records

PROFILE = 'scalar-jump-v1'
LINK_PROFILE = 'scalar-link-v1'
PROFILES = {PROFILE,LINK_PROFILE}
KINDS = {'flow_profile', 'label', 'goto', 'link', 'return', 'stop'}
LOOPS = {'do_counted', 'do_while', 'do_until'}
STEP_FIELDS = {'kind','name','line','inputs','by','operations','nodupkey','where','retained','lengths','display_names'}
NAME = r'[A-Za-z_][A-Za-z0-9_]{0,31}'
RESERVED = {'_n_','_error_','_all_','_numeric_','_character_','_temporary_','_infile_','_file_','_ods_','_page_','_blankpage_','_null_'}
COMPARISONS = {'=','eq','ne','^=','~=','<>','<','lt','<=','le','>','gt','>=','ge','truth'}


def ordinary(name):
    return (isinstance(name,str) and name.isascii() and re.fullmatch(NAME,name) is not None
            and name == name.lower() and name not in RESERVED)


def integer(value):
    return None if value is None else float(sas_counted_control(value))


def guard_structure(value):
    pending=[(value,0,frozenset())];count=0
    while pending:
        node,depth,ancestors=pending.pop();count+=1
        if count>20000 or depth>256:
            raise ValueError('scalar flow structure exceeds its bounded size/depth')
        if isinstance(node,(dict,list)):
            if id(node) in ancestors:raise ValueError('scalar flow structure is cyclic')
            ancestry=ancestors|{id(node)}
            if isinstance(node,dict):
                if any(type(k) is not str for k in node):raise ValueError('scalar flow keys must be strings')
                children=node.values()
            else:children=node
            pending.extend((child,depth+1,ancestry) for child in children)
        elif type(node) not in (str,int,float,bool,type(None)):
            raise ValueError('scalar flow requires portable JSON values')


def refuse_legacy(ops):
    """New operations cannot disappear on empty legacy DATA paths."""
    if not isinstance(ops,list):return
    pending=list(ops);seen=set()
    while pending:
        op=pending.pop()
        if not isinstance(op,dict):continue
        if id(op) in seen:continue
        seen.add(id(op))
        if isinstance(op.get('kind'),str) and op['kind'] in KINDS:raise ValueError('scalar flow requires its separate control_data profile')
        args=op.get('args')
        if isinstance(args,dict):
            for key in ('operation','otherwise'):
                if key in args:pending.append(args[key])
            if isinstance(args.get('body'),list):pending.extend(args['body'])


def evaluate(expr,row):
    if type(expr) is int:return integer(expr)
    kind=expr['kind']
    if kind in ('number','missing'):return integer(expr['value'])
    if kind in ('variable','automatic'):return integer(row.get(expr['value']))
    if kind=='call':return integer(sas_mod(*(evaluate(e,row) for e in expr['args'])))
    a,b=evaluate(expr['left'],row),evaluate(expr['right'],row)
    if a is None or b is None:return None
    return integer(a+b if expr['op']=='+' else a-b if expr['op']=='-' else a*b)


def condition(test,row):
    a=evaluate(test['left'],row);op=test['op']
    if op=='truth':return a is not None and a!=0
    b=evaluate(test['right'],row);a,b=sas_numeric_order(a),sas_numeric_order(b)
    if op in ('=','eq'):return a==b
    if op in ('ne','^=','~=','<>'):return a!=b
    if op in ('<','lt'):return a<b
    if op in ('<=','le'):return a<=b
    if op in ('>','gt'):return a>b
    return a>=b


def validate_step(step,version=2,catalog=None):
    guard_structure(step)
    if (type(version) is not int or version!=2 or type(step) is not dict or set(step)!=STEP_FIELDS
            or step['kind']!='flow_data' or step['inputs']!=[] or not (ordinary(step['name']) or step['name']=='_null_')
            or type(step['line']) is not int or step['line']<1 or type(step['operations']) is not list
            or type(step['inputs']) is not list or len(step['inputs'])>1 or any(not ordinary(n) for n in step['inputs'])
            or step['by']!=[] or step['where'] is not None or step['nodupkey'] is not False
            or step['lengths']!={} or step['display_names']!={} or type(step['retained']) is not dict):
        raise ValueError('scalar flow requires its exact version2 control_data step shape')
    roots=step['operations']
    if (not roots or type(roots[0]) is not dict or type(roots[0].get('args')) is not dict
            or type(roots[0]['args'].get('name')) is not str or roots[0]['args']['name'] not in PROFILES
            or roots[0]!={'kind':'flow_profile','line':step['line'],'args':{'name':roots[0]['args']['name']}}
            or type(roots[0]['line']) is not int):
        raise ValueError('scalar flow requires its first declaration at the DATA line')
    operation_count=0;arithmetic_count=0;features=set();flat=[];declared=set();sums=set();put_ops=[];selections=[];reads=[]
    def expr(node,depth=1,control=False):
        nonlocal arithmetic_count
        if depth>32:raise ValueError('scalar flow expression exceeds32 levels')
        if type(node) is int:
            if not control:raise ValueError('scalar expression requires a mapping')
            return True,integer(node)
        if type(node) is not dict:raise ValueError('scalar flow expression requires a mapping')
        kind=node.get('kind')
        if kind in ('number','missing','variable','automatic'):
            if set(node)!={'kind','value'}:raise ValueError('scalar flow scalar operand fields differ')
            value=node['value']
            if kind in ('number','missing'):
                if (kind=='number' and value is None or kind=='missing' and value is not None or control and kind=='missing'):
                    raise ValueError('scalar flow numeric/missing encoding is invalid')
                return True,integer(value)
            if (kind=='variable' and not ordinary(value) or kind=='automatic' and value!='_n_'):
                raise ValueError('scalar flow requires ordinary names or _N_')
            return False,None
        if kind=='call':
            if (control or roots[0]['args']['name']!=LINK_PROFILE or set(node)!={'kind','name','args'}
                    or node['name']!='mod' or type(node['args']) is not list or len(node['args'])!=2):
                raise ValueError('scalar link profile admits only the existing integer MOD call')
            arithmetic_count+=1
            a,av=expr(node['args'][0],depth+1);b,bv=expr(node['args'][1],depth+1)
            if a and av is None or b and (bv is None or bv==0):raise ValueError('MOD constant arguments require ordinary integers and a nonzero divisor')
            features.add('mod')
            return (True,integer(sas_mod(av,bv))) if a and b else (False,None)
        if kind!='arithmetic' or set(node)!={'kind','op','left','right'} or node['op'] not in ('+','-','*') or control and node['op']=='*':
            raise ValueError('scalar flow admits integer +/-/* without numeric calls')
        arithmetic_count+=1
        a,av=expr(node['left'],depth+1,control);b,bv=expr(node['right'],depth+1,control)
        return (True,evaluate(node,{})) if a and b else (False,None)
    def predicate(test):
        if (type(test) is not dict or type(test.get('op')) is not str or test['op'] not in COMPARISONS
                or set(test)!=({'op','left'} if test['op']=='truth' else {'op','left','right'})):
            raise ValueError('scalar flow requires an existing scalar predicate')
        expr(test['left'])
        if test['op']!='truth':expr(test['right'])
    def visit(op,depth=0,loops=(),active=(),conditional=False,jumps=True):
        nonlocal operation_count
        operation_count+=1
        if operation_count>1024 or depth>32:raise ValueError('scalar flow exceeds1024 operations or32 mixed container levels')
        if type(op) is not dict or set(op)!={'kind','line','args'} or type(op.get('kind')) is not str or type(op.get('line')) is not int or op['line']<1 or type(op['args']) is not dict:
            raise ValueError('scalar flow operation requires exact kind/line/args')
        flat.append(op);kind,args=op['kind'],op['args']
        if kind in {'do_group','if','do_counted','do_while','do_until'} and depth>=32:raise ValueError('scalar flow exceeds32 mixed containers')
        if kind=='label':
            if depth or set(args)!={'name'} or not ordinary(args.get('name')):raise ValueError('statement labels require unique top-level ordinary names')
            features.add('jump')
        elif kind=='goto':
            if not jumps or loops or set(args)!={'name'} or not ordinary(args.get('name')):raise ValueError('GOTO requires a top-level or IF action with an ordinary target')
            features.add('jump')
        elif kind=='stop':
            if args:raise ValueError('STOP takes no arguments')
            features.add('jump')
        elif kind=='link':
            if not jumps or loops or set(args)!={'name'} or not ordinary(args.get('name')):raise ValueError('LINK requires a top-level or IF action and ordinary target')
            if roots[0]['args']['name']!=LINK_PROFILE:raise ValueError('LINK requires its separate stage2 profile')
            features.add('link')
        elif kind=='return':
            if args or roots[0]['args']['name']!=LINK_PROFILE:raise ValueError('RETURN requires its separate stage2 profile and no arguments')
            features.add('link')
        elif kind=='input_list':
            if (depth or set(args)!={'names','records','data_line'} or not input_names_valid(args.get('names'))
                    or any(not ordinary(n) for n in args['names']) or roots[0]['args']['name']!=LINK_PROFILE
                    or type(args.get('data_line')) is not int or args['data_line']<=op['line']):
                raise ValueError('scalar flow INPUT requires one first numeric inline source in its stage2 profile')
            decode_rows(args['records'],args['names'])
            features.add('input')

        elif kind in ('leave','continue'):
            if args or not loops:raise ValueError('transfer requires no arguments and a statically owning loop')
            features.add('transfer')
        elif kind=='do_group':
            if set(args)!={'body'} or type(args['body']) is not list:raise ValueError('group requires only a body list')
            features.add('group')
            for child in args['body']:visit(child,depth+1,loops,active,jumps=False)
        elif kind=='if':
            if set(args) not in ({'condition','operation'},{'condition','operation','otherwise'}):raise ValueError('scalar flow IF shape differs')
            predicate(args['condition'])
            for key in ('operation','otherwise'):
                if key in args:
                    if type(args[key]) is dict and args[key].get('kind') in LOOPS:raise ValueError('conditional iterative loops remain deferred')
                    visit(args[key],depth+1,loops,active,True,jumps)
        elif kind in LOOPS:
            if conditional or len(loops)>=8 or loops and (kind!='do_counted' or any(p!='do_counted' for p in loops)):
                raise ValueError('scalar flow iterative nesting retains counted-only8-level control')
            if kind=='do_counted':
                if set(args)!={'index','start','stop','by','body','profile'} or args['profile']!='bounded' or not ordinary(args.get('index')) or args['index'] in active:
                    raise ValueError('scalar flow counted loop requires captured bounded controls and a distinct index')
                known=[]
                for key in ('start','stop','by'):
                    validate_control(args[key]);known.append(expr(args[key],control=True))
                    pending=[args[key]]
                    while pending:
                        node=pending.pop()
                        if isinstance(node,dict):
                            if node.get('kind') in ('variable','automatic') and node.get('value')==args['index']:
                                raise ValueError('scalar flow counted controls cannot reference their own index')
                            pending.extend(v for v in node.values() if isinstance(v,dict))
                if known[2][0] and known[2][1]==0:raise ValueError('scalar flow counted BY is zero')
                if all(x[0] for x in known):sas_counted_capture(*(x[1] for x in known),0)
                next_active=active+(args['index'],)
            else:
                if set(args)!={'condition','body'}:raise ValueError('scalar flow conditional loop shape differs')
                predicate(args['condition']);next_active=active
            if type(args['body']) is not list:raise ValueError('scalar flow loop requires a body list')
            for child in args['body']:visit(child,depth+1,loops+(kind,),next_active,jumps=False)
        elif kind in ('assign','sum_statement'):
            if set(args)!={'name','value'} or not ordinary(args.get('name')) or args['name'] in active:raise ValueError('scalar flow scalar assignment changes reserved/control state')
            expr(args['value'])
            if kind=='sum_statement':sums.add(args['name'])
        elif kind=='subset':
            if set(args)!={'condition'} or loops:raise ValueError('scalar flow subsetting IF remains outside iterative bodies')
            predicate(args['condition'])
        elif kind=='declare':
            if depth or set(args)!={'name','spec'} or not ordinary(args.get('name')) or args['spec']!='number':raise ValueError('scalar flow declaration must be a top-level numeric RETAIN target')
            declared.add(args['name'])
        elif kind=='read':
            raise ValueError('SET requires a separate scalar-flow characterization')
            if depth or set(args)!={'datasets'} or args['datasets']!=step['inputs'] or len(step['inputs'])!=1:raise ValueError('scalar flow SET requires one top-level matching source')
            reads.append(op)
        elif kind=='projection':
            if (depth or set(args)!={'mode','names','scope'} or args['mode'] not in ('keep','drop')
                    or args['scope'] not in ('statement','input','output') or not names_valid(args['names'])):
                raise ValueError('scalar flow projection requires a top-level bounded selector')
            selections.append(op)
        elif kind in ('put','put_numeric_list'):
            if set(args)!={'names'} or type(args['names']) is not list or not args['names'] or any(not ordinary(n) for n in args['names']) or len(args['names'])>64:
                raise ValueError('scalar flow numeric PUT requires ordinary named operands')
            put_ops.append(op)
            if kind=='put_numeric_list':sas_put_numeric_list([None]*len(args['names']))
            elif len(' '.join(n+'=.' for n in args['names']))>64:raise ValueError('scalar flow named PUT exceeds64 columns')
        elif kind=='put_literal':
            if set(args)!={'literals'}:raise ValueError('scalar flow literal PUT shape differs')
            text=sas_put_literals(args['literals'])
            if len(text)>64 or not text.isascii():raise ValueError('scalar flow literal PUT requires64 ASCII columns')
        elif kind=='output':
            if set(args)!={'target'} or args['target'] not in (None,step['name']) or step['name']=='_null_':raise ValueError('scalar flow OUTPUT requires its named DATA destination')
        else:raise ValueError('operation requires a separate scalar-flow contract')
    for op in roots[1:]:visit(op)
    if not features & {'jump','link'}:raise ValueError('flow profile requires actual local label or flow syntax')
    if roots[0]['args']['name']==LINK_PROFILE and not features & {'link','input','mod'}:raise ValueError('stage2 marker requires actual LINK/RETURN or numeric composition')
    labels={}
    for position,op in enumerate(roots):
        if op['kind']=='label':
            name=op['args']['name']
            if name in labels:raise ValueError('duplicate local statement label')
            labels[name]=position
    if len(labels)>64:raise ValueError('scalar flow exceeds64 statement labels')
    for op in flat:
        if op['kind'] in ('goto','link') and op['args']['name'] not in labels:raise ValueError('undefined local statement label')
    if arithmetic_count>128:raise ValueError('scalar flow expressions exceed128 arithmetic nodes')
    for name,value in step['retained'].items():
        if not ordinary(name) or name not in declared|sums or type(value) is not dict or value.get('kind') not in ('number','missing'):
            raise ValueError('scalar flow RETAIN requires declared ordinary literal state')
        expr(value)
    if not sums<=set(step['retained']):raise ValueError('scalar flow sum targets require explicit retained plan state')
    if len(reads)!=len(step['inputs']):raise ValueError('scalar flow SET source and read count differ')
    input_sel=[o for o in selections if o['args']['scope']=='input'];output_sel=[o for o in selections if o['args']['scope']!='input']
    if len(input_sel)>1 or len(output_sel)>1:raise ValueError('scalar flow selectors conflict')
    if reads:
        pos=next(i for i,o in enumerate(roots) if o is reads[0])
        if any(o['kind'] not in ('flow_profile','declare','projection') for o in roots[:pos]):raise ValueError('scalar flow SET must precede executable actions')
        if input_sel and (pos<1 or roots[pos-1] is not input_sel[0] or input_sel[0]['line']!=reads[0]['line']):raise ValueError('scalar flow input selector must directly precede SET')
    elif input_sel:raise ValueError('scalar flow input selector requires SET')
    for o in output_sel:
        if o['args']['scope']=='output' and (roots[1] is not o or o['line']!=step['line']):raise ValueError('scalar-flow DATA option must immediately follow its marker')
    info={'flat':flat,'input':input_sel[0]['args'] if input_sel else None,'output':output_sel[0]['args'] if output_sel else None,'puts':put_ops,'features':features,'labels':labels,'inline_rows':None}
    inputs=[op for op in flat if op['kind']=='input_list']
    if len(inputs)>1:raise ValueError('scalar flow supports one numeric INPUT')
    if inputs:
        position=next(i for i,op in enumerate(roots) if op is inputs[0])
        if any(op['kind'] not in ('flow_profile','declare','projection') for op in roots[:position]):raise ValueError('numeric INPUT must be the first top-level executable operation')
        if any(labels[op['args']['name']]<=position for op in flat if op['kind'] in ('goto','link')):raise ValueError('scalar flow cannot jump to or before its INPUT')
        args=inputs[0]['args'];info['inline_rows']=decode_rows(args['records'],args['names'])
    validate_links(roots,flat,labels,bool(inputs))
    if not step['inputs']:
        schema_for(step,info,{})
    return info


def schema_for(step,info,catalog):
    schema={};source=None
    def add(name):
        if name!='_n_':schema.setdefault(name,'number')
    def names(expr):
        if type(expr) is int:return
        if expr['kind'] in ('variable','automatic'):add(expr['value'])
        elif expr['kind']=='arithmetic':names(expr['left']);names(expr['right'])
        elif expr['kind']=='call':
            for arg in expr['args']:names(arg)
    for op in info['flat']:
        kind,args=op['kind'],op['args']
        if kind=='read':
            name=step['inputs'][0]
            if name not in catalog:raise ValueError('scalar flow SET source is absent')
            source=project_table(catalog[name],info['input']) if info['input'] else deepcopy(catalog[name])
            if len(source['rows'])>10000:raise ValueError('scalar flow SET exceeds10000 observations')
            for name,spec in source['schema'].items():
                if not ordinary(name) or column_type(spec)!='number':raise ValueError('scalar flow SET requires ordinary numeric descriptors')
                schema[name]=deepcopy(spec)
            for row in source['rows']:
                for value in row.values():integer(value)
        elif kind=='input_list':
            for name in args['names']:add(name)
        elif kind in ('assign','sum_statement','declare'):add(args['name'])
        elif kind=='do_counted':
            add(args['index'])
            for key in ('start','stop','by'):names(args[key])
        if 'value' in args:names(args['value'])
        if 'condition' in args:
            names(args['condition']['left'])
            if args['condition']['op']!='truth':names(args['condition']['right'])
    if not schema or len(schema)>64:raise ValueError('scalar-flow DATA requires1..64 numeric PDV columns')
    selected=selected_names(schema,info['output'])
    for op in info['puts']:
        for name in op['args']['names']:
            if name not in schema:raise ValueError('scalar flow PUT variable is absent from its complete PDV')
            if isinstance(schema[name],dict) and schema[name].get('format'):raise ValueError('scalar flow PUT requires unformatted numeric columns')
    return schema,selected,source


def decode_rows(records,names):
    values=sas_input_records(records,len(names));used=0
    for record in records:
        for token in record.split(' '):
            if not token:continue
            integer(sas_input_number(token));used+=1
            if used==len(names):used=0;break
    return [dict(zip(names,row)) for row in values]


def validate_links(roots,flat,labels,has_input):
    links=[op for op in flat if op['kind']=='link']
    targets={op['args']['name'] for op in links}
    if len(targets)>1:raise ValueError('scalar flow admits one unique LINK destination')
    target=labels[next(iter(targets))] if targets else len(roots)
    def contains_link(op):
        if op['kind']=='link':return True
        args=op['args']
        return any(contains_link(child) for child in args.get('body',[])) or any(contains_link(args[key]) for key in ('operation','otherwise') if key in args)
    if any(contains_link(op) for op in roots[target:]):raise ValueError('LINK target region cannot contain another LINK, including dead code')
    def outcomes(op):
        kind,args=op['kind'],op['args']
        if kind in ('goto','link'):return {(kind,args['name'])}
        if kind in ('return','stop'):return {(kind,None)}
        if kind=='if':return outcomes(args['operation']) | (outcomes(args['otherwise']) if 'otherwise' in args else {('next',None)})
        if kind in ('do_group','do_counted','do_while','do_until'):
            result={('next',None)}
            for child in args['body']:
                if ('next',None) in result:result=(result-{('next',None)})|outcomes(child)
            if kind!='do_group':result|={('next',None)}
            return result
        return {('next',None)}
    edges=[outcomes(op) for op in roots];pending=[(pc,None,False) for pc in range(len(roots))]+[(0,None,True)];seen=set()
    while pending:
        pc,caller,reachable=pending.pop();state=(pc,caller,reachable)
        if state in seen:continue
        seen.add(state)
        if len(seen)>20000:raise ValueError('scalar flow static caller analysis exceeds20000 states')
        if pc==len(roots):
            if caller is not None:pending.append((caller,None,reachable))
            continue
        for kind,name in edges[pc]:
            if kind=='next':pending.append((pc+1,caller,reachable))
            elif kind=='goto':pending.append((labels[name],caller,reachable))
            elif kind=='link':
                if caller is not None:raise ValueError('scalar flow refuses nested or recursive active LINK paths')
                pending.append((labels[name],pc+1,reachable))
            elif kind=='return':
                if caller is not None:pending.append((caller,None,reachable))
                elif reachable and not has_input:raise ValueError('unlinked RETURN reachable without INPUT requires further characterization')


class Signal(Enum):
    NORMAL=0
    REJECT=1
    LEAVE=2
    CONTINUE=3
    STOP=4
    RETURN=5


def execute_step(step,catalog=None,version=2,trace=None):
    info=validate_step(step,version);tables=normalize_catalog({} if catalog is None else catalog)
    schema,selected,_=schema_for(step,info,tables);rows=info['inline_rows'] if info['inline_rows'] is not None else [{}]
    explicit=any(o['kind']=='output' for o in info['flat'])
    retained={n:integer(e['value']) for n,e in step['retained'].items()};output=[];logs=[];events=0;instructions=0
    def show(value):return '.' if value is None else str(int(value))
    def charge():
        nonlocal instructions
        instructions+=1
        if instructions>100000:raise ValueError('scalar flow exceeds100000 dispatched instructions per step')
    def event(kind,*parts):
        nonlocal events
        events+=1
        if events>1000000:raise ValueError('scalar flow exceeds1000000 events per step')
        if trace is not None:trace.append('|'.join((kind,*(str(p) for p in parts))))
    for row_index,incoming in enumerate(rows,1):
        row={n:None for n in schema};row.update(deepcopy(retained));row['_n_']=float(row_index);spent=0;event('row',row_index)
        def snapshot():
            if len(output)>=10000:raise ValueError('scalar flow OUTPUT exceeds10000 observations')
            output.append({n:deepcopy(row[n]) for n in selected});event('output',';'.join(n+'='+show(row[n]) for n in selected))
        def sequence(body):
            for op in body:
                signal=perform(op)
                if signal is not Signal.NORMAL:return signal
            return Signal.NORMAL
        def perform(op):
            nonlocal spent
            charge();kind,args=op['kind'],op['args']
            if kind in ('flow_profile','declare','projection'):return Signal.NORMAL
            if kind=='input_list':
                for name in args['names']:row[name]=integer(incoming[name])
                event('input',';'.join(n+'='+show(row[n]) for n in args['names']));return Signal.NORMAL
            if kind=='label':event('label',args['name'])
            elif kind in ('goto','link'):event(kind,args['name']);return (kind,args['name'])
            elif kind=='return':event('return');return Signal.RETURN
            elif kind=='stop':event('stop');return Signal.STOP
            elif kind=='assign':row[args['name']]=evaluate(args['value'],row);event('assign',args['name'],show(row[args['name']]))
            elif kind=='sum_statement':
                value=evaluate(args['value'],row);row[args['name']]=integer((row[args['name']] or 0)+(value or 0));event('sum',args['name'],show(row[args['name']]))
            elif kind=='do_group':event('group','enter');signal=sequence(args['body']);event('group','exit');return signal
            elif kind=='if':
                value=condition(args['condition'],row);event('if',int(value));branch=args.get('operation') if value else args.get('otherwise');return perform(branch) if branch is not None else Signal.NORMAL
            elif kind=='subset':
                value=condition(args['condition'],row);event('subset',int(value));return Signal.NORMAL if value else Signal.REJECT
            elif kind in ('leave','continue'):event('transfer',kind);return Signal.LEAVE if kind=='leave' else Signal.CONTINUE
            elif kind=='do_counted':
                controls=[evaluate_control(args[k],row) for k in ('start','stop','by')];values,final,spent=sas_counted_capture(*controls,spent);row[args['index']]=integer(controls[0]);event('capture',args['index'],*controls,len(values));left=False
                for value in values:
                    row[args['index']]=integer(value);event('iteration','counted',args['index'],show(row[args['index']]));signal=sequence(args['body'])
                    if signal not in (Signal.NORMAL,Signal.LEAVE,Signal.CONTINUE):return signal
                    if signal is Signal.LEAVE:left=True;break
                    charge();row[args['index']]=integer(value+controls[2]);event('increment',args['index'],show(row[args['index']]))
                if not left:row[args['index']]=integer(final)
                event('loop','exit','counted')
            elif kind in ('do_while','do_until'):
                trips=0
                while True:
                    if kind=='do_while':
                        charge();test=condition(args['condition'],row);event('test','while',int(test))
                        if not test:break
                    trips+=1
                    if trips>10000:raise ValueError('scalar flow conditional loop exceeds10000 bodies')
                    event('iteration',kind[3:],trips);signal=sequence(args['body'])
                    if signal not in (Signal.NORMAL,Signal.LEAVE,Signal.CONTINUE):return signal
                    if signal is Signal.LEAVE:break
                    if kind=='do_until':
                        charge();test=condition(args['condition'],row);event('test','until',int(test))
                        if test:break
                event('loop','exit',kind[3:])
            elif kind=='output':snapshot()
            elif kind in ('put','put_numeric_list','put_literal'):
                if len(logs)>=10000:raise ValueError('scalar flow PUT exceeds10000 logical records')
                text=(sas_put_literals(args['literals']) if kind=='put_literal' else sas_put_numeric_list([row[n] for n in args['names']]) if kind=='put_numeric_list' else ' '.join(n+'='+show(row[n]) for n in args['names']))
                if len(text)>64:raise ValueError('scalar flow PUT exceeds64 columns')
                logs.append(text);event('put',text.encode().hex())
            else:raise ValueError('unvalidated scalar-flow operation')
            return Signal.NORMAL
        pc=0;caller=None;stopped=False;result=Signal.NORMAL
        while True:
            if pc==len(step['operations']):
                if caller is None:break
                charge();event('resume','implicit',caller);pc=caller;caller=None;continue
            event('pc',pc);result=perform(step['operations'][pc])
            if isinstance(result,tuple):
                if result[0]=='link':
                    if caller is not None:raise ValueError('scalar flow exceeded one active LINK caller')
                    caller=pc+1;event('call',caller)
                pc=info['labels'][result[1]];continue
            if result is Signal.RETURN:
                if caller is None:result=Signal.NORMAL;event('next-record');break
                event('resume','explicit',caller);pc=caller;caller=None;continue
            if result is Signal.STOP:stopped=True;break
            if result is Signal.REJECT:break
            if result is not Signal.NORMAL:raise ValueError('scalar-flow loop transfer escaped its owner')
            pc+=1
        retained={name:deepcopy(row[name]) for name in retained}
        if not stopped and result is Signal.NORMAL and not explicit and step['name']!='_null_':snapshot()
        if stopped:break
    return (None if step['name']=='_null_' else {'schema':{n:deepcopy(schema[n]) for n in selected},'rows':output}),logs


def _trigger(statement):
    if any(t.kind is Kind.DATA for t in statement.tokens):return False
    text=statement.text
    return bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]{0,31}\s*:',text,re.ASCII)
        or re.fullmatch(r'(?:go\s*to\s+[A-Za-z_][A-Za-z0-9_]{0,31}|stop|return|link\s+[A-Za-z_][A-Za-z0-9_]{0,31})',text,re.I|re.ASCII)
        or re.fullmatch(r'(?:if\s+.+\s+then|else)\s+(?:go\s*to\s+[A-Za-z_][A-Za-z0-9_]{0,31}|stop|return|link\s+[A-Za-z_][A-Za-z0-9_]{0,31})',text,re.I|re.ASCII))


def parse_block(statements):
    from .plan import Step,Operation,expression,predicate,atom
    if not statements or statements[-1].text.lower()!='run' or not statements[-1].terminated:raise ValueError('scalar-flow DATA requires explicit final RUN')
    statements=list(statements);data=None;data_line=None
    for at,st in enumerate(statements):
        if st.text.lower() in ('cards','datalines'):
            if data is not None or at+2!=len(statements)-1 or len(statements[at+1].tokens)!=1 or statements[at+1].tokens[0].kind is not Kind.DATA:raise ValueError('scalar flow requires one complete final inline-data block')
            data=source_records(statements[at+1].tokens[0].text);data_line=st.line+1
            statements=statements[:at]+statements[at+2:];break
    for st in statements:
        if not st.terminated or any(t.kind is Kind.DATA or t.kind is not Kind.STRING and not t.text.isascii() for t in st.tokens):raise ValueError('scalar flow syntax requires complete ASCII statements without inline INPUT')
        if len(st.text)>4096:raise ValueError('scalar flow statement exceeds4096 characters')
    if len(statements)>2050:raise ValueError('scalar flow source exceeds2050 statements before its1024-operation check')
    name,selection=dataset(statements[0].text,'data');step=Step('flow_data',name,statements[0].line)
    ops=[{'kind':'flow_profile','line':step.line,'args':{'name':PROFILE}}]
    if selection:ops.append({'kind':'projection','line':step.line,'args':selection})
    position=1;seen_action=False
    def make(kind,line,args):return {'kind':kind,'line':line,'args':args}
    def parsed_expression(text):
        if len(text)>4096:raise ValueError('scalar flow expression source too long')
        depth=0
        for ch in text:
            depth+=(ch=='(')-(ch==')')
            if depth>32:raise ValueError('scalar flow source expression exceeds32 levels')
        result=expression(text)
        if result is None:raise ValueError('unsupported scalar flow scalar expression')
        return result
    def body(depth=0,loops=(),close=False):
        nonlocal position
        if depth>32:raise ValueError('scalar flow source exceeds32 mixed container levels')
        result=[]
        while position<len(statements)-1:
            st=statements[position]
            if st.text.lower()=='end':
                if not close:raise ValueError('unmatched scalar flow END')
                position+=1;return result
            position+=1;result.append(one(st.text,st.line,depth,loops))
        if close:raise ValueError('scalar flow body requires END before RUN')
        return result
    def one(text,line,depth,loops,branch=False):
        nonlocal position,seen_action
        if depth>32:raise ValueError('scalar flow source exceeds32 levels')
        low=text.lower()
        if low=='do':seen_action=True;return make('do_group',line,{'body':body(depth+1,loops,True)})
        match=re.fullmatch(r'if\s+(.+?)\s+then\s+(.+)',text,re.I|re.ASCII)
        if match:
            seen_action=True;test=predicate(match[1])
            if test is None:raise ValueError('unsupported scalar flow IF predicate')
            child=one(match[2],line,depth+1,loops,True);args={'condition':test,'operation':child}
            if position<len(statements)-1:
                otherwise=re.fullmatch(r'else\s+(.+)',statements[position].text,re.I|re.ASCII)
                if otherwise:
                    st=statements[position];position+=1;args['otherwise']=one(otherwise[1],st.line,depth+1,loops,True)
            return make('if',line,args)
        if low in ('leave','continue','stop','return'):seen_action=True;return make(low,line,{})
        linked=re.fullmatch(r'link\s+('+NAME+r')',text,re.I|re.ASCII)
        if linked:seen_action=True;return make('link',line,{'name':linked[1].lower()})
        read=re.fullmatch(r'input\s+('+NAME+r'(?:\s+'+NAME+r')*)',text,re.I|re.ASCII)
        if read:
            if depth or branch or seen_action or data is None:raise ValueError('scalar flow INPUT must be first and have one final CARDS/DATALINES block')
            seen_action=True;return make('input_list',line,{'names':[n.lower() for n in read[1].split()],'records':data,'data_line':data_line})
        jump=re.fullmatch(r'go\s*to\s+('+NAME+r')',text,re.I|re.ASCII)
        if jump:seen_action=True;return make('goto',line,{'name':jump[1].lower()})
        conditional=re.fullmatch(r'do\s+(while|until)\s*\((.*)\)',text,re.I|re.ASCII)
        counted=re.fullmatch(r'do\s+('+NAME+r')\s*=\s*(.+?)\s+to\s+(.+?)(?:\s+by\s+(.+))?',text,re.I|re.ASCII)
        if conditional or counted:
            if branch:raise ValueError('conditional iterative loops remain deferred')
            seen_action=True
            if conditional:
                kind='do_'+conditional[1].lower();test=predicate(conditional[2])
                if test is None:raise ValueError('unsupported scalar flow loop predicate')
                args={'condition':test,'body':body(depth+1,loops+(kind,),True)}
            else:
                kind='do_counted';args={'index':counted[1].lower(),'start':parse_control(counted[2]),'stop':parse_control(counted[3]),'by':parse_control(counted[4] or '1'),'profile':'bounded','body':body(depth+1,loops+(kind,),True)}
            return make(kind,line,args)
        if re.match(r'set\s',text,re.I|re.ASCII):
            if depth or branch or seen_action or step.inputs:raise ValueError('scalar flow SET must be the first executable source')
            source,option=dataset(text,'set');step.inputs=[source]
            if option:ops.append(make('projection',line,option))
            return make('read',line,{'datasets':[source]})
        retain=re.fullmatch(r'retain\s+('+NAME+r')\s+(.+)',text,re.I|re.ASCII)
        if retain:
            if depth or branch or seen_action:raise ValueError('scalar flow RETAIN must be a top-level prefix')
            value=atom(retain[2]);target=retain[1].lower()
            if value is None or value['kind'] not in ('number','missing') or target in step.retained:raise ValueError('scalar flow RETAIN requires one unique literal initializer')
            step.retained[target]=value;return make('declare',line,{'name':target,'spec':'number'})
        if re.match(r'(?:keep|drop)\s',text,re.I|re.ASCII):
            if depth or branch:raise ValueError('scalar flow selectors must be top-level')
            return make('projection',line,declaration(text))
        seen_action=True
        if low=='output' or re.fullmatch(r'output\s+'+NAME,text,re.I|re.ASCII):return make('output',line,{'target':None if low=='output' else text.split()[1].lower()})
        named=re.fullmatch(r'put\s+((?:'+NAME+r'\s*=\s*)+)',text,re.I|re.ASCII)
        if named:return make('put',line,{'names':[n.lower() for n in re.findall('('+NAME+r')\s*=',named[1],re.ASCII)]})
        plain=re.fullmatch(r'put\s+('+NAME+r'(?:\s+'+NAME+r')*)',text,re.I|re.ASCII)
        if plain:return make('put_numeric_list',line,{'names':[n.lower() for n in plain[1].split()]})
        if re.match(r'put\s',text,re.I|re.ASCII):
            tokens=split_statements(text+';')[0].tokens[1:]
            if tokens and all(t.kind is Kind.STRING for t in tokens):return make('put_literal',line,{'literals':[t.text for t in tokens]})
        subset=re.fullmatch(r'if\s+(.+)',text,re.I|re.ASCII)
        if subset:
            test=predicate(subset[1])
            if test is None:raise ValueError('unsupported scalar flow subset predicate')
            return make('subset',line,{'condition':test})
        assignment=re.fullmatch('('+NAME+r')\s*=\s*(.+)',text,re.ASCII);summation=re.fullmatch('('+NAME+r')\s*\+\s*(.+)',text,re.ASCII)
        if assignment or summation:
            match=assignment or summation;target=match[1].lower();value=parsed_expression(match[2])
            if not assignment:step.retained.setdefault(target,{'kind':'number','value':0.0})
            return make('assign' if assignment else 'sum_statement',line,{'name':target,'value':value})
        raise ValueError('statement is outside bounded scalar-flow DATA control: '+text)
    while position<len(statements)-1:
        st=statements[position];position+=1;text=st.text
        labeled=re.fullmatch('('+NAME+r')\s*:\s*(.*)',text,re.ASCII)
        if labeled:
            ops.append(make('label',st.line,{'name':labeled[1].lower()}));text=labeled[2]
        if text:ops.append(one(text,st.line,0,()))
    if (data is not None)!=any(op['kind']=='input_list' for op in ops):raise ValueError('scalar flow inline records require matching INPUT')
    pending=list(ops[1:]);stage2=False
    while pending:
        node=pending.pop()
        if isinstance(node,dict):
            stage2|=node.get('kind') in ('link','return','input_list') or node.get('kind')=='call' and node.get('name')=='mod'
            pending.extend(node.values())
        elif isinstance(node,list):pending.extend(node)
    ops[0]['args']['name']=LINK_PROFILE if stage2 else PROFILE
    step.operations=[Operation(**o) for o in ops];validate_step(asdict(step));return step


def compile_program(source,legacy):
    """Select only scoped new syntax; retain the legacy source path otherwise."""
    from .plan import Plan,Ticket
    try:statements=split_statements(source)
    except ParseError:return None
    blocks=[];position=0
    while position<len(statements):
        st=statements[position]
        if not re.match(r'data\s',st.text,re.I|re.ASCII):position+=1;continue
        end=position+1
        while end<len(statements) and statements[end].text.lower()!='run':
            if re.match(r'(?:data|proc)\s',statements[end].text,re.I|re.ASCII):break
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
            combined.matched.append(('scalar-link','DS-065',step.line) if step.operations[0].args['name']==LINK_PROFILE else ('scalar-jump','DS-064',step.line))
        except (ValueError,RecursionError) as exc:combined.tickets.append(Ticket(block[0].line,block[0].text,'scalar-flow',str(exc)))
        cursor=stop
    prior(cursor,len(source));return combined
