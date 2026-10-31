"""DS-060/061 separately marked integer DATA groups and loop transfers."""
from copy import deepcopy
from dataclasses import asdict
from enum import Enum
import re

from sas_semantics import (sas_counted_control, sas_counted_capture,
                           sas_put_numeric_list, sas_put_literals, sas_numeric_order)
from .counted import parse_control, validate_control, evaluate_control
from .parser import split_statements, ParseError, Kind
from .projection import dataset, declaration, names_valid, selected_names, project_table
from .values import normalize_catalog, column_type

PROFILE = 'bounded-control-v1'
KINDS = {'control_profile', 'do_group', 'leave', 'continue'}
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
            raise ValueError('grouped control structure exceeds its bounded size/depth')
        if isinstance(node,(dict,list)):
            if id(node) in ancestors:raise ValueError('grouped control structure is cyclic')
            ancestry=ancestors|{id(node)}
            if isinstance(node,dict):
                if any(type(k) is not str for k in node):raise ValueError('grouped control keys must be strings')
                children=node.values()
            else:children=node
            pending.extend((child,depth+1,ancestry) for child in children)
        elif type(node) not in (str,int,float,bool,type(None)):
            raise ValueError('grouped control requires portable JSON values')


def refuse_legacy(ops):
    """New operations cannot disappear on empty legacy DATA paths."""
    if not isinstance(ops,list):return
    pending=list(ops);seen=set()
    while pending:
        op=pending.pop()
        if not isinstance(op,dict):continue
        if id(op) in seen:continue
        seen.add(id(op))
        if isinstance(op.get('kind'),str) and op['kind'] in KINDS:raise ValueError('grouped control requires its separate control_data profile')
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
            or step['kind']!='control_data' or not (ordinary(step['name']) or step['name']=='_null_')
            or type(step['line']) is not int or step['line']<1 or type(step['operations']) is not list
            or type(step['inputs']) is not list or len(step['inputs'])>1 or any(not ordinary(n) for n in step['inputs'])
            or step['by']!=[] or step['where'] is not None or step['nodupkey'] is not False
            or step['lengths']!={} or step['display_names']!={} or type(step['retained']) is not dict):
        raise ValueError('grouped control requires its exact version2 control_data step shape')
    roots=step['operations']
    if not roots or roots[0]!={'kind':'control_profile','line':step['line'],'args':{'name':PROFILE}} or type(roots[0]['line']) is not int:
        raise ValueError('grouped control requires its first declaration at the DATA line')
    operation_count=0;arithmetic_count=0;features=set();flat=[];declared=set();sums=set();put_ops=[];selections=[];reads=[]
    def expr(node,depth=1,control=False):
        nonlocal arithmetic_count
        if depth>32:raise ValueError('grouped control expression exceeds32 levels')
        if type(node) is int:
            if not control:raise ValueError('scalar expression requires a mapping')
            return True,integer(node)
        if type(node) is not dict:raise ValueError('grouped control expression requires a mapping')
        kind=node.get('kind')
        if kind in ('number','missing','variable','automatic'):
            if set(node)!={'kind','value'}:raise ValueError('grouped scalar operand fields differ')
            value=node['value']
            if kind in ('number','missing'):
                if (kind=='number' and value is None or kind=='missing' and value is not None or control and kind=='missing'):
                    raise ValueError('grouped numeric/missing encoding is invalid')
                return True,integer(value)
            if (kind=='variable' and not ordinary(value) or kind=='automatic' and value!='_n_'):
                raise ValueError('grouped control requires ordinary names or _N_')
            return False,None
        if kind!='arithmetic' or set(node)!={'kind','op','left','right'} or node['op'] not in ('+','-','*') or control and node['op']=='*':
            raise ValueError('grouped control admits integer +/-/* without numeric calls')
        arithmetic_count+=1
        a,av=expr(node['left'],depth+1,control);b,bv=expr(node['right'],depth+1,control)
        return (True,evaluate(node,{})) if a and b else (False,None)
    def predicate(test):
        if (type(test) is not dict or type(test.get('op')) is not str or test['op'] not in COMPARISONS
                or set(test)!=({'op','left'} if test['op']=='truth' else {'op','left','right'})):
            raise ValueError('grouped control requires an existing scalar predicate')
        expr(test['left'])
        if test['op']!='truth':expr(test['right'])
    def visit(op,depth=0,loops=(),active=(),conditional=False):
        nonlocal operation_count
        operation_count+=1
        if operation_count>1024 or depth>32:raise ValueError('grouped control exceeds1024 operations or32 mixed container levels')
        if type(op) is not dict or set(op)!={'kind','line','args'} or type(op.get('kind')) is not str or type(op.get('line')) is not int or op['line']<1 or type(op['args']) is not dict:
            raise ValueError('grouped operation requires exact kind/line/args')
        flat.append(op);kind,args=op['kind'],op['args']
        if kind in ('leave','continue'):
            if args or not loops:raise ValueError('transfer requires no arguments and a statically owning loop')
            features.add('transfer')
        elif kind=='do_group':
            if set(args)!={'body'} or type(args['body']) is not list:raise ValueError('group requires only a body list')
            features.add('group')
            for child in args['body']:visit(child,depth+1,loops,active)
        elif kind=='if':
            if set(args) not in ({'condition','operation'},{'condition','operation','otherwise'}):raise ValueError('grouped IF shape differs')
            predicate(args['condition'])
            for key in ('operation','otherwise'):
                if key in args:
                    if type(args[key]) is dict and args[key].get('kind') in LOOPS:raise ValueError('conditional iterative loops remain deferred')
                    visit(args[key],depth+1,loops,active,True)
        elif kind in LOOPS:
            if conditional or len(loops)>=8 or loops and (kind!='do_counted' or any(p!='do_counted' for p in loops)):
                raise ValueError('grouped iterative nesting retains counted-only8-level control')
            if kind=='do_counted':
                if set(args)!={'index','start','stop','by','body','profile'} or args['profile']!='bounded' or not ordinary(args.get('index')) or args['index'] in active:
                    raise ValueError('grouped counted loop requires captured bounded controls and a distinct index')
                known=[]
                for key in ('start','stop','by'):
                    validate_control(args[key]);known.append(expr(args[key],control=True))
                    pending=[args[key]]
                    while pending:
                        node=pending.pop()
                        if isinstance(node,dict):
                            if node.get('kind') in ('variable','automatic') and node.get('value')==args['index']:
                                raise ValueError('grouped counted controls cannot reference their own index')
                            pending.extend(v for v in node.values() if isinstance(v,dict))
                if known[2][0] and known[2][1]==0:raise ValueError('grouped counted BY is zero')
                if all(x[0] for x in known):sas_counted_capture(*(x[1] for x in known),0)
                next_active=active+(args['index'],)
            else:
                if set(args)!={'condition','body'}:raise ValueError('grouped conditional loop shape differs')
                predicate(args['condition']);next_active=active
            if type(args['body']) is not list:raise ValueError('grouped loop requires a body list')
            for child in args['body']:visit(child,depth+1,loops+(kind,),next_active)
        elif kind in ('assign','sum_statement'):
            if set(args)!={'name','value'} or not ordinary(args.get('name')) or args['name'] in active:raise ValueError('grouped scalar assignment changes reserved/control state')
            expr(args['value'])
            if kind=='sum_statement':sums.add(args['name'])
        elif kind=='subset':
            if set(args)!={'condition'} or loops:raise ValueError('grouped subsetting IF remains outside iterative bodies')
            predicate(args['condition'])
        elif kind=='declare':
            if depth or set(args)!={'name','spec'} or not ordinary(args.get('name')) or args['spec']!='number':raise ValueError('grouped declaration must be a top-level numeric RETAIN target')
            declared.add(args['name'])
        elif kind=='read':
            if depth or set(args)!={'datasets'} or args['datasets']!=step['inputs'] or len(step['inputs'])!=1:raise ValueError('grouped SET requires one top-level matching source')
            reads.append(op)
        elif kind=='projection':
            if (depth or set(args)!={'mode','names','scope'} or args['mode'] not in ('keep','drop')
                    or args['scope'] not in ('statement','input','output') or not names_valid(args['names'])):
                raise ValueError('grouped projection requires a top-level bounded selector')
            selections.append(op)
        elif kind in ('put','put_numeric_list'):
            if set(args)!={'names'} or type(args['names']) is not list or not args['names'] or any(not ordinary(n) for n in args['names']) or len(args['names'])>64:
                raise ValueError('grouped numeric PUT requires ordinary named operands')
            put_ops.append(op)
            if kind=='put_numeric_list':sas_put_numeric_list([None]*len(args['names']))
            elif len(' '.join(n+'=.' for n in args['names']))>64:raise ValueError('grouped named PUT exceeds64 columns')
        elif kind=='put_literal':
            if set(args)!={'literals'}:raise ValueError('grouped literal PUT shape differs')
            text=sas_put_literals(args['literals'])
            if len(text)>64 or not text.isascii():raise ValueError('grouped literal PUT requires64 ASCII columns')
        elif kind=='output':
            if set(args)!={'target'} or args['target'] not in (None,step['name']) or step['name']=='_null_':raise ValueError('grouped OUTPUT requires its named DATA destination')
        else:raise ValueError('operation requires a separate grouped-control contract')
    for op in roots[1:]:visit(op)
    if not features:raise ValueError('control profile requires an actual group or transfer')
    if arithmetic_count>128:raise ValueError('grouped expressions exceed128 arithmetic nodes')
    for name,value in step['retained'].items():
        if not ordinary(name) or name not in declared|sums or type(value) is not dict or value.get('kind') not in ('number','missing'):
            raise ValueError('grouped RETAIN requires declared ordinary literal state')
        expr(value)
    if not sums<=set(step['retained']):raise ValueError('grouped sum targets require explicit retained plan state')
    if len(reads)!=len(step['inputs']):raise ValueError('grouped SET source and read count differ')
    input_sel=[o for o in selections if o['args']['scope']=='input'];output_sel=[o for o in selections if o['args']['scope']!='input']
    if len(input_sel)>1 or len(output_sel)>1:raise ValueError('grouped selectors conflict')
    if reads:
        pos=next(i for i,o in enumerate(roots) if o is reads[0])
        if any(o['kind'] not in ('control_profile','declare','projection') for o in roots[:pos]):raise ValueError('grouped SET must precede executable actions')
        if input_sel and (pos<1 or roots[pos-1] is not input_sel[0] or input_sel[0]['line']!=reads[0]['line']):raise ValueError('grouped input selector must directly precede SET')
    elif input_sel:raise ValueError('grouped input selector requires SET')
    for o in output_sel:
        if o['args']['scope']=='output' and (roots[1] is not o or o['line']!=step['line']):raise ValueError('grouped DATA option must immediately follow its marker')
    info={'flat':flat,'input':input_sel[0]['args'] if input_sel else None,'output':output_sel[0]['args'] if output_sel else None,'puts':put_ops,'features':features}
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
    for op in info['flat']:
        kind,args=op['kind'],op['args']
        if kind=='read':
            name=step['inputs'][0]
            if name not in catalog:raise ValueError('grouped SET source is absent')
            source=project_table(catalog[name],info['input']) if info['input'] else deepcopy(catalog[name])
            if len(source['rows'])>10000:raise ValueError('grouped SET exceeds10000 observations')
            for name,spec in source['schema'].items():
                if not ordinary(name) or column_type(spec)!='number':raise ValueError('grouped SET requires ordinary numeric descriptors')
                schema[name]=deepcopy(spec)
            for row in source['rows']:
                for value in row.values():integer(value)
        elif kind in ('assign','sum_statement','declare'):add(args['name'])
        elif kind=='do_counted':
            add(args['index'])
            for key in ('start','stop','by'):names(args[key])
        if 'value' in args:names(args['value'])
        if 'condition' in args:
            names(args['condition']['left'])
            if args['condition']['op']!='truth':names(args['condition']['right'])
    if not schema or len(schema)>64:raise ValueError('grouped DATA requires1..64 numeric PDV columns')
    selected=selected_names(schema,info['output'])
    for op in info['puts']:
        for name in op['args']['names']:
            if name not in schema:raise ValueError('grouped PUT variable is absent from its complete PDV')
            if isinstance(schema[name],dict) and schema[name].get('format'):raise ValueError('grouped PUT requires unformatted numeric columns')
    return schema,selected,source


class Signal(Enum):
    NORMAL=0
    REJECT=1
    LEAVE=2
    CONTINUE=3


def execute_step(step,catalog=None,version=2,trace=None):
    info=validate_step(step,version);tables=normalize_catalog({} if catalog is None else catalog)
    schema,selected,source=schema_for(step,info,tables);rows=source['rows'] if source is not None else [{}]
    explicit=any(o['kind']=='output' for o in info['flat']);retained={n:integer(e['value']) for n,e in step['retained'].items()};output=[];logs=[];events=0
    def show(value):return '.' if value is None else str(int(value))
    def event(kind,*parts):
        nonlocal events
        events+=1
        if events>1000000:raise ValueError('grouped schedule exceeds1000000 events per step')
        if trace is not None:trace.append('|'.join((kind,*(str(p) for p in parts))))
    for row_index,incoming in enumerate(rows,1):
        row={n:None for n in schema};row.update(deepcopy(retained));row.update({n:integer(v) for n,v in incoming.items()});row['_n_']=float(row_index);spent=0;event('row',row_index)
        def snapshot():
            if len(output)>=10000:raise ValueError('grouped OUTPUT exceeds10000 observations')
            output.append({n:deepcopy(row[n]) for n in selected});event('output',';'.join(n+'='+show(row[n]) for n in selected))
        def sequence(body):
            for op in body:
                signal=perform(op)
                if signal is not Signal.NORMAL:return signal
            return Signal.NORMAL
        def perform(op):
            nonlocal spent
            kind,args=op['kind'],op['args']
            if kind in ('control_profile','declare','projection','read'):return Signal.NORMAL
            if kind=='assign':row[args['name']]=evaluate(args['value'],row);event('assign',args['name'],show(row[args['name']]))
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
                    if signal is Signal.REJECT:return signal
                    if signal is Signal.LEAVE:left=True;break
                    row[args['index']]=integer(value+controls[2]);event('increment',args['index'],show(row[args['index']]))
                if not left:row[args['index']]=integer(final)
                event('loop','exit','counted')
            elif kind in ('do_while','do_until'):
                trips=0
                while True:
                    if kind=='do_while':
                        test=condition(args['condition'],row);event('test','while',int(test))
                        if not test:break
                    trips+=1
                    if trips>10000:raise ValueError('grouped conditional loop exceeds10000 bodies')
                    event('iteration',kind[3:],trips);signal=sequence(args['body'])
                    if signal is Signal.REJECT:return signal
                    if signal is Signal.LEAVE:break
                    if kind=='do_until':
                        test=condition(args['condition'],row);event('test','until',int(test))
                        if test:break
                event('loop','exit',kind[3:])
            elif kind=='output':snapshot()
            elif kind in ('put','put_numeric_list','put_literal'):
                if len(logs)>=10000:raise ValueError('grouped PUT exceeds10000 logical records')
                text=(sas_put_literals(args['literals']) if kind=='put_literal' else sas_put_numeric_list([row[n] for n in args['names']]) if kind=='put_numeric_list' else ' '.join(n+'='+show(row[n]) for n in args['names']))
                if len(text)>64:raise ValueError('grouped PUT exceeds64 columns')
                logs.append(text);event('put',text.encode().hex())
            else:raise ValueError('unvalidated grouped operation')
            return Signal.NORMAL
        result=sequence(step['operations'])
        if result in (Signal.LEAVE,Signal.CONTINUE):raise ValueError('grouped transfer escaped its owning loop')
        retained={name:deepcopy(row[name]) for name in retained}
        if result is Signal.NORMAL and not explicit and step['name']!='_null_':snapshot()
    table={**({k:deepcopy(v) for k,v in source.items() if k not in ('schema','rows')} if source is not None else {}),'schema':{n:deepcopy(schema[n]) for n in selected},'rows':output}
    return (None if step['name']=='_null_' else table),logs


def _trigger(statement):
    if any(t.kind is Kind.DATA for t in statement.tokens):return False
    text=statement.text
    # Strings cannot be statement heads or bare transfer/group actions.
    return bool(re.fullmatch(r'(?:do|leave|continue)',text,re.I|re.ASCII) or re.fullmatch(r'(?:if\s+.+\s+then|else)\s+(?:do|leave|continue)',text,re.I|re.ASCII))


def parse_block(statements):
    from .plan import Step,Operation,expression,predicate,atom
    if not statements or statements[-1].text.lower()!='run' or not statements[-1].terminated:raise ValueError('grouped DATA requires explicit final RUN')
    for st in statements:
        if not st.terminated or any(t.kind is Kind.DATA or t.kind is not Kind.STRING and not t.text.isascii() for t in st.tokens):raise ValueError('grouped syntax requires complete ASCII statements without inline INPUT')
        if len(st.text)>4096:raise ValueError('grouped statement exceeds4096 characters')
    if len(statements)>2050:raise ValueError('grouped source exceeds2050 statements before its1024-operation check')
    name,selection=dataset(statements[0].text,'data');step=Step('control_data',name,statements[0].line);ops=[{'kind':'control_profile','line':step.line,'args':{'name':PROFILE}}]
    if selection:ops.append({'kind':'projection','line':step.line,'args':selection})
    position=1;seen_action=False
    def make(kind,line,args):return {'kind':kind,'line':line,'args':args}
    def parsed_expression(text):
        if len(text)>4096:raise ValueError('grouped expression source too long')
        depth=0
        for ch in text:
            depth+=(ch=='(')-(ch==')')
            if depth>32:raise ValueError('grouped source expression exceeds32 levels')
        result=expression(text)
        if result is None:raise ValueError('unsupported grouped scalar expression')
        return result
    def body(depth=0,loops=(),close=False):
        nonlocal position
        if depth>32:raise ValueError('grouped source exceeds32 mixed container levels')
        result=[]
        while position<len(statements)-1:
            st=statements[position]
            if st.text.lower()=='end':
                if not close:raise ValueError('unmatched grouped END')
                position+=1;return result
            position+=1;result.append(one(st.text,st.line,depth,loops))
        if close:raise ValueError('grouped body requires END before RUN')
        return result
    def one(text,line,depth,loops,branch=False):
        nonlocal position,seen_action
        if depth>32:raise ValueError('grouped source exceeds32 levels')
        low=text.lower()
        if low=='do':seen_action=True;return make('do_group',line,{'body':body(depth+1,loops,True)})
        match=re.fullmatch(r'if\s+(.+?)\s+then\s+(.+)',text,re.I|re.ASCII)
        if match:
            seen_action=True;test=predicate(match[1])
            if test is None:raise ValueError('unsupported grouped IF predicate')
            child=one(match[2],line,depth+1,loops,True);args={'condition':test,'operation':child}
            if position<len(statements)-1:
                otherwise=re.fullmatch(r'else\s+(.+)',statements[position].text,re.I|re.ASCII)
                if otherwise:
                    st=statements[position];position+=1;args['otherwise']=one(otherwise[1],st.line,depth+1,loops,True)
            return make('if',line,args)
        if low in ('leave','continue'):seen_action=True;return make(low,line,{})
        conditional=re.fullmatch(r'do\s+(while|until)\s*\((.*)\)',text,re.I|re.ASCII)
        counted=re.fullmatch(r'do\s+('+NAME+r')\s*=\s*(.+?)\s+to\s+(.+?)(?:\s+by\s+(.+))?',text,re.I|re.ASCII)
        if conditional or counted:
            if branch:raise ValueError('conditional iterative loops remain deferred')
            seen_action=True
            if conditional:
                kind='do_'+conditional[1].lower();test=predicate(conditional[2])
                if test is None:raise ValueError('unsupported grouped loop predicate')
                args={'condition':test,'body':body(depth+1,loops+(kind,),True)}
            else:
                kind='do_counted';args={'index':counted[1].lower(),'start':parse_control(counted[2]),'stop':parse_control(counted[3]),'by':parse_control(counted[4] or '1'),'profile':'bounded','body':body(depth+1,loops+(kind,),True)}
            return make(kind,line,args)
        if re.match(r'set\b',text,re.I|re.ASCII):
            if depth or branch or seen_action or step.inputs:raise ValueError('grouped SET must be the first executable source')
            source,option=dataset(text,'set');step.inputs=[source]
            if option:ops.append(make('projection',line,option))
            return make('read',line,{'datasets':[source]})
        retain=re.fullmatch(r'retain\s+('+NAME+r')\s+(.+)',text,re.I|re.ASCII)
        if retain:
            if depth or branch or seen_action:raise ValueError('grouped RETAIN must be a top-level prefix')
            value=atom(retain[2]);target=retain[1].lower()
            if value is None or value['kind'] not in ('number','missing') or target in step.retained:raise ValueError('grouped RETAIN requires one unique literal initializer')
            step.retained[target]=value;return make('declare',line,{'name':target,'spec':'number'})
        if re.match(r'(?:keep|drop)\b',text,re.I|re.ASCII):
            if depth or branch:raise ValueError('grouped selectors must be top-level')
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
            if test is None:raise ValueError('unsupported grouped subset predicate')
            return make('subset',line,{'condition':test})
        assignment=re.fullmatch('('+NAME+r')\s*=\s*(.+)',text,re.ASCII);summation=re.fullmatch('('+NAME+r')\s*\+\s*(.+)',text,re.ASCII)
        if assignment or summation:
            match=assignment or summation;target=match[1].lower();value=parsed_expression(match[2])
            if not assignment:step.retained.setdefault(target,{'kind':'number','value':0.0})
            return make('assign' if assignment else 'sum_statement',line,{'name':target,'value':value})
        raise ValueError('statement is outside bounded grouped DATA control: '+text)
    while position<len(statements)-1:
        st=statements[position];position+=1;ops.append(one(st.text,st.line,0,()))
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
            if 'group' in info['features']:combined.matched.append(('grouped-do','DS-060',step.line))
            if 'transfer' in info['features']:combined.matched.append(('loop-transfer','DS-061',step.line))
        except (ValueError,RecursionError) as exc:combined.tickets.append(Ticket(block[0].line,block[0].text,'grouped-control',str(exc)))
        cursor=stop
    prior(cursor,len(source));return combined
