"""Separately marked rounded numeric ingestion, array and loop composition.

The converter, exact index/control evaluators and runtime loop schedules retain
old bounds. Only numeric values in the new expression profile may round.
"""
from copy import deepcopy

from sas_semantics import sas_numeric_array_index, sas_do_counted
from . import binary64
from .arrays import (validate_declaration, validate_expression as validate_index_expression,
                     value as exact_array_value, contains_array)
from .counted import validate_control, validate_step as validate_counted_step
from .input_list import validate_step as validate_input_step
from .operations import walk_operations
from .projection import _validate_step as validate_projection_context
from .functions import expression_nodes
from .values import column_type, descriptor

PROFILE = 'binary64-pipeline-v1'


def array_sum(values):
    """Validate all members, ignore missing, and accumulate in declaration order."""
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 1024:
        raise ValueError('numeric pipeline SUM OF requires1..1024 declared values')
    checked = [binary64.numeric(value) for value in values]
    present = [value for value in checked if value is not None]
    if not present:
        return None
    total = 0.0
    for value in present:
        total = binary64.arithmetic('+', total, value)
    return total


def array_index(name, expr, row, arrays, current=None):
    declaration = arrays[name]
    value = exact_array_value(expr, row, arrays, current)
    return sas_numeric_array_index(value, declaration['lower'], len(declaration['names']))


def evaluate(expr, row, arrays=None, current=None):
    arrays = {} if arrays is None else arrays
    kind = expr['kind']
    if kind in ('number', 'missing'):
        return binary64.numeric(expr['value'])
    if kind in ('variable', 'automatic'):
        return binary64.numeric(row.get(expr['value']))
    if kind == 'arithmetic':
        return binary64.arithmetic(expr['op'], evaluate(expr['left'], row, arrays, current),
                                   evaluate(expr['right'], row, arrays, current))
    if kind == 'call':
        values = ([expr['args'][0]['value']] if expr['name'] == 'constant' else
                  [evaluate(arg, row, arrays, current) for arg in expr['args']])
        return binary64.apply(expr['name'], values)
    declaration = arrays[expr['name']]
    if kind == 'array_sum':
        return array_sum([row.get(name) for name in declaration['names']])
    if kind == 'array_current':
        if current is None or expr['name'] not in current:
            raise ValueError('numeric pipeline current element has no active binding')
        position = current[expr['name']]
        if type(position) is not int or not 0 <= position < len(declaration['names']):
            raise ValueError('numeric pipeline current offset is invalid')
    elif kind == 'array_get':
        position = array_index(expr['name'], expr['index'], row, arrays, current)
    else:
        raise ValueError('numeric pipeline expression is outside its validated profile')
    return binary64.numeric(row.get(declaration['names'][position]))


def array_set(args, row, arrays, current=None):
    position = array_index(args['name'], args['index'], row, arrays, current)
    value = evaluate(args['value'], row, arrays, current)
    row[arrays[args['name']]['names'][position]] = value


def array_current_set(args, row, arrays, current):
    if args['name'] not in current:
        raise ValueError('numeric pipeline current assignment has no active binding')
    position = current[args['name']]
    if type(position) is not int or not 0 <= position < len(arrays[args['name']]['names']):
        raise ValueError('numeric pipeline current offset is invalid')
    row[arrays[args['name']]['names'][position]] = evaluate(args['value'], row, arrays, current)


def validate_step(step, version=2, schema=None):
    """Validate the new marker and inactive paths independently of compilation."""
    if not isinstance(step, dict) or not isinstance(step.get('operations'), list):
        raise ValueError('numeric pipeline requires a DATA-step mapping')
    # A cycle-safe scan identifies this profile without admitting metadata as a
    # semantic trigger. Full structure validation then bounds every container.
    pending, seen, markers = [step], set(), []
    while pending:
        node = pending.pop()
        if isinstance(node, (dict, list, tuple)):
            if id(node) in seen:
                continue
            seen.add(id(node))
        if isinstance(node, dict):
            if node.get('kind') == 'numeric_profile' and node.get('args') == {'name': PROFILE}:
                markers.append(node)
            pending.extend(node.values())
        elif isinstance(node, (list, tuple)):
            pending.extend(node)
    if not markers:
        return None
    if binary64._structure(step) != 1 or len(markers) != 1:
        raise ValueError('numeric pipeline requires one unique declaration occurrence')
    roots = step['operations']
    marker = markers[0]
    expected = {'kind', 'name', 'line', 'inputs', 'by', 'operations', 'nodupkey',
                'where', 'retained', 'lengths', 'display_names'}
    if (type(version) is not int or version != 2 or set(step) != expected or step['kind'] != 'data'
            or not (binary64.ordinary(step['name']) or step['name'] == '_null_')
            or type(step['line']) is not int or step['line'] < 1
            or not roots or roots[0] is not marker or marker != {'kind': 'numeric_profile', 'line': step['line'], 'args': {'name': PROFILE}}
            or type(marker['line']) is not int or not isinstance(step['inputs'], list)
            or len(step['inputs']) > 1 or any(not binary64.ordinary(n) for n in step['inputs'])
            or step['by'] != [] or step['where'] is not None or step['lengths'] != {} or step['nodupkey'] is not False):
        raise ValueError('numeric pipeline requires its first version2 DATA declaration and one source')
    display = step['display_names']
    if (not isinstance(display, dict) or any(not (binary64.ordinary(name) or name == '_n_')
            or not isinstance(shown, str) or shown.lower() != name for name, shown in display.items())):
        raise ValueError('numeric pipeline display names must match ordinary numeric names')
    flat = list(walk_operations(roots, all_containers=True))
    all_array_names = set()
    for op in flat:
        if op['kind'] == 'array_declare':
            validate_declaration(op['args'])
            all_array_names.add(op['args']['name'])
    arrays, cells, features = {}, set(), set()
    numeric_nodes, array_nodes, semantic_trigger = 0, 0, False
    input_ops, reads = [], []

    def expression(expr, depth=1, current=None):
        nonlocal numeric_nodes, semantic_trigger
        if not isinstance(expr, dict) or depth > 32:
            raise ValueError('numeric pipeline expression exceeds32 levels or has invalid shape')
        kind = expr.get('kind')
        if kind in ('number', 'missing', 'variable', 'automatic'):
            if set(expr) != {'kind', 'value'}:
                raise ValueError('numeric pipeline scalar operand has unexpected fields')
            value = expr['value']
            if kind in ('number', 'missing'):
                if kind == 'number' and value is None or kind == 'missing' and value is not None:
                    raise ValueError('numeric pipeline missing literal encoding is invalid')
                return True, binary64.numeric(value)
            if (kind == 'variable' and (not binary64.ordinary(value) or value in all_array_names)
                    or kind == 'automatic' and value != '_n_'):
                raise ValueError('numeric pipeline requires ordinary scalar names or _N_')
            binary64._number_descriptor(value, schema)
            return False, None
        if kind == 'arithmetic':
            numeric_nodes += 1
            if set(expr) != {'kind', 'op', 'left', 'right'} or expr['op'] not in ('+', '-', '*', '/', '**'):
                raise ValueError('numeric pipeline arithmetic shape/operator is invalid')
            semantic_trigger |= expr['op'] == '**'
            a, left = expression(expr['left'], depth + 1, current)
            b, right = expression(expr['right'], depth + 1, current)
            if expr['op'] == '/' and b and right == 0:
                raise ValueError('numeric pipeline literal divisor is zero')
            if expr['op'] == '**' and b and right is not None and (right != int(right) or not 0 <= right <= 32):
                raise ValueError('numeric pipeline power requires an integer exponent in0..32')
            return (True, binary64.arithmetic(expr['op'], left, right)) if a and b else (False, None)
        if kind == 'call':
            numeric_nodes += 1
            if (set(expr) != {'kind', 'name', 'args'} or not isinstance(expr.get('name'), str)
                    or expr['name'] not in binary64.CALLS or not isinstance(expr.get('args'), list) or len(expr['args']) != 1):
                raise ValueError('numeric pipeline call shape/name/arity is invalid')
            semantic_trigger |= expr['name'] in binary64.FUNCTIONS
            if expr['name'] == 'constant':
                arg = expr['args'][0]
                if (not isinstance(arg, dict) or set(arg) != {'kind', 'value'}
                        or arg.get('kind') != 'character' or depth + 1 > 32):
                    raise ValueError('numeric pipeline CONSTANT requires a literal Pi name')
                return True, binary64.apply('constant', [arg['value']])
            known, value = expression(expr['args'][0], depth + 1, current)
            return (True, binary64.apply(expr['name'], [value])) if known else (False, None)
        expected_fields = {'kind', 'name', 'index'} if kind == 'array_get' else {'kind', 'name'}
        if kind not in ('array_get', 'array_current', 'array_sum') or set(expr) != expected_fields or not isinstance(expr.get('name'), str) or expr['name'] not in arrays:
            raise ValueError('numeric pipeline array reference requires a preceding declaration')
        declaration = arrays[expr['name']]
        if kind == 'array_current':
            if current != expr['name'] or declaration.get('mode') != 'implicit':
                raise ValueError('numeric pipeline current element requires its active implicit loop')
        elif kind == 'array_get':
            if declaration.get('mode') == 'implicit':
                raise ValueError('numeric pipeline does not mix indexed/current DO OVER references')
            validate_index_expression(expr['index'], arrays, schema, depth=depth + 1, current=current)
            # The old exact evaluator checks constant index intermediates before
            # any skipped path can hide a literal bounds/type failure.
            if not any(node.get('kind') in ('variable', 'automatic', 'array_get', 'array_current', 'array_sum')
                       for node, _ in expression_nodes(expr['index'])):
                array_index(expr['name'], expr['index'], {}, arrays)
        return False, None

    def predicate(test, current=None):
        if (not isinstance(test, dict) or not isinstance(test.get('op'), str)
                or test['op'] not in binary64.COMPARISONS | {'truth'}
                or set(test) != ({'left', 'op'} if test.get('op') == 'truth' else {'left', 'op', 'right'})):
            raise ValueError('numeric pipeline predicate shape is invalid')
        expression(test['left'], current=current)
        if test['op'] != 'truth': expression(test['right'], current=current)

    def operation(op, loops=(), active=(), current=None, conditional=False):
        nonlocal array_nodes
        if (not isinstance(op, dict) or set(op) != {'kind', 'line', 'args'} or type(op.get('line')) is not int
                or op['line'] < 1 or not isinstance(op.get('args'), dict)):
            raise ValueError('numeric pipeline operation requires kind/line/args')
        kind, args = op['kind'], op['args']
        if 'do_over' in loops and kind not in ('assign','array_current_set','if','put_numeric_list','output'):
            raise ValueError('numeric pipeline DO OVER descendants keep their prior action profile')
        payload = {k: v for k, v in args.items() if k not in ('body', 'operation', 'otherwise')}
        if kind in ('array_set', 'array_current_set') or contains_array(payload):
            array_nodes += sum(1 for n, _ in expression_nodes(payload) if 'kind' in n)
        if kind == 'array_declare':
            if loops or conditional or args['name'] in arrays or args['name'] in binary64.CALLS:
                raise ValueError('numeric pipeline ARRAY declarations must be unique top-level names')
            if any(n in all_array_names for n in args['names']):
                raise ValueError('numeric pipeline array names/elements collide')
            if sum(len(a['names']) for a in arrays.values()) + len(args['names']) > 1024:
                raise ValueError('numeric pipeline arrays exceed1024 declared element references')
            arrays[args['name']] = deepcopy(args);cells.update(args['names']);features.add('arrays')
        elif kind in ('assign', 'sum_statement'):
            if (set(args) != {'name', 'value'} or not binary64.ordinary(args.get('name'))
                    or args['name'] in all_array_names or args['name'] in active
                    or kind == 'sum_statement' and (args['name'] in cells or 'do_over' in loops)):
                raise ValueError('numeric pipeline scalar target collides with array/control state')
            binary64._number_descriptor(args['name'], schema);expression(args['value'], current=current)
        elif kind in ('array_set', 'array_current_set'):
            expected = {'name', 'value', 'index'} if kind == 'array_set' else {'name', 'value'}
            if set(args) != expected:
                raise ValueError('numeric pipeline array assignment fields are invalid')
            reference = {'kind': 'array_get', 'name': args['name'], 'index': args['index']} if kind == 'array_set' else {'kind': 'array_current', 'name': args['name']}
            expression(reference, current=current);expression(args['value'], current=current)
        elif kind == 'declare':
            if (set(args) != {'name', 'spec'} or not binary64.ordinary(args.get('name'))
                    or args['name'] in all_array_names or args['name'] in active or args['spec'] != 'number'):
                raise ValueError('numeric pipeline declarations require ordinary numeric targets')
        elif kind == 'input_list':
            if loops or conditional: raise ValueError('numeric pipeline INPUT must be top-level')
            input_ops.append(op);features.add('input')
        elif kind == 'read':
            if loops or conditional or set(args) != {'datasets'} or args['datasets'] != step['inputs'] or len(step['inputs']) != 1:
                raise ValueError('numeric pipeline SET requires one matching top-level source')
            reads.append(op)
        elif kind == 'projection':
            if loops or conditional: raise ValueError('numeric pipeline projection must be top-level')
        elif kind == 'if':
            if set(args) not in ({'condition', 'operation'}, {'condition', 'operation', 'otherwise'}):
                raise ValueError('numeric pipeline IF fields are invalid')
            predicate(args['condition'], current)
            operation(args['operation'], loops, active, current, True)
            if 'otherwise' in args: operation(args['otherwise'], loops, active, current, True)
        elif kind == 'subset':
            if set(args) != {'condition'} or loops: raise ValueError('numeric pipeline subset IF must be top-level')
            predicate(args['condition'])
        elif kind in ('do_while', 'do_until', 'do_over', 'do_counted'):
            if conditional: raise ValueError('numeric pipeline loops cannot be conditional')
            if kind == 'do_counted':
                if any(parent != 'do_counted' for parent in loops) or len(loops) >= 8:
                    raise ValueError('numeric pipeline counted nesting retains its8-level profile')
                fields = {'index', 'start', 'stop', 'by', 'body'} | ({'profile'} if args.get('profile') == 'bounded' else set())
                if set(args) != fields or args.get('index') in all_array_names | cells | set(active) or not binary64.ordinary(args.get('index')):
                    raise ValueError('numeric pipeline counted controls collide or have invalid shape')
                if args.get('profile') == 'bounded':
                    for key in ('start', 'stop', 'by'): validate_control(args[key], schema)
                else: sas_do_counted(args['start'], args['stop'], args['by'])
                next_active = active + (args['index'],);next_current = current
            elif kind == 'do_over':
                if loops or set(args) != {'name', 'body'} or not isinstance(args.get('name'), str) or args['name'] not in arrays or arrays[args['name']].get('mode') != 'implicit':
                    raise ValueError('numeric pipeline DO OVER requires one top-level implicit array')
                if any(node.get('kind') == 'array_get' for node, _ in expression_nodes(args)):
                    raise ValueError('numeric pipeline DO OVER keeps indexed/current references separate')
                features.add('over');next_active=active;next_current=args['name']
            else:
                if loops or set(args) != {'condition', 'body'}:
                    raise ValueError('numeric pipeline WHILE/UNTIL retain a single loop level')
                predicate(args['condition']);features.add('while' if kind == 'do_while' else 'until')
                next_active=active;next_current=current
            if not isinstance(args.get('body'), list): raise ValueError('numeric pipeline loop body must be a list')
            for child in args['body']:
                if kind == 'do_over' and child.get('kind') not in ('assign','array_current_set','if','put_numeric_list','output'):
                    raise ValueError('numeric pipeline DO OVER body keeps its prior action profile')
                operation(child, loops + (kind,), next_active, next_current)
        elif kind == 'put_numeric_list':
            names = args.get('names')
            if (set(args) not in ({'names'}, {'names','discover'}) or not isinstance(names, list) or not names
                    or any(not binary64.ordinary(n) or n in all_array_names for n in names)):
                raise ValueError('numeric pipeline PUT requires ordinary scalar names')
            for name in names:
                binary64._number_descriptor(name, schema)
                if schema is not None and isinstance(schema.get(name), dict) and schema[name].get('format'):
                    raise ValueError('numeric pipeline numeric PUT requires unformatted columns')
            if 'discover' in args:
                found=args['discover']
                if (step['inputs'] or not isinstance(found,list) or not found or len(found)>32
                        or any(not binary64.ordinary(n) for n in found) or len(set(found))!=len(found)
                        or found != [n for n in dict.fromkeys(names) if n in found]):
                    raise ValueError('numeric pipeline PUT discovery retains its catalog-free profile')
            binary64.render_numeric_list([None]*len(names))
        elif kind == 'output':
            if set(args) != {'target'} or args['target'] not in (None,step['name']):
                raise ValueError('numeric pipeline OUTPUT requires the DATA destination')
        else:
            raise ValueError('numeric pipeline operation requires separate composition evidence')

    retained=step['retained']
    if not isinstance(retained,dict): raise ValueError('numeric pipeline RETAIN requires a mapping')
    for name,initial in retained.items():
        if not binary64.ordinary(name) or name in all_array_names or not isinstance(initial,dict) or initial.get('kind') not in ('number','missing'):
            raise ValueError('numeric pipeline RETAIN requires ordinary literal initialization')
        expression(initial)
    for op in roots[1:]: operation(op)
    if not semantic_trigger or not features:
        raise ValueError('numeric pipeline requires executable new numeric syntax and a D1 feature')
    whole_numeric_nodes = sum(node.get('kind') in ('arithmetic', 'call') for node, _ in expression_nodes(step))
    if numeric_nodes > 128 or whole_numeric_nodes > 128 or array_nodes > 128:
        raise ValueError('numeric pipeline exceeds128 arithmetic/call or array-expression nodes')
    if cells & set(retained): raise ValueError('numeric pipeline retained/sum array elements remain deferred')
    if 'over' in features:
        if '_i_' in retained or schema is not None and '_i_' in schema:
            raise ValueError('numeric pipeline implicit index _I_ remains internal')
        if any(op['args'].get('name')=='_i_' or op['args'].get('index')=='_i_'
               or isinstance(op['args'].get('names'),list) and '_i_' in op['args']['names'] for op in flat):
            raise ValueError('numeric pipeline implicit index _I_ remains internal')
        if any(n.get('kind') in ('variable','automatic') and n.get('value')=='_i_' for n,_ in expression_nodes(step)):
            raise ValueError('numeric pipeline implicit index _I_ remains internal')
    if schema is not None:
        if not isinstance(schema,dict) or all_array_names & set(schema) or any(n not in schema or column_type(descriptor(schema[n]))!='number' for n in cells):
            raise ValueError('numeric pipeline arrays require numeric PDV members without array-name columns')
    if len(input_ops)>1 or len(reads)!=len(step['inputs']) or input_ops and reads:
        raise ValueError('numeric pipeline permits one inline or SET source per step')
    source_op = input_ops[0] if input_ops else reads[0] if reads else None
    inline_rows=None
    if source_op is not None:
        position=next(i for i,op in enumerate(roots) if op is source_op)
        if any(op['kind'] not in ('declare','projection','array_declare') for op in roots[1:position]):
            raise ValueError('numeric pipeline source must precede executable actions')
    if input_ops:
        # Reuse the unchanged converter and record cursor through a minimal
        # source-only view. Admission of the composed bodies is checked above.
        source_view=deepcopy(step);source_view['operations']=[deepcopy(input_ops[0])]
        inline_rows=validate_input_step(source_view,version)
        if any(not binary64.ordinary(n) for n in input_ops[0]['args']['names']):
            raise ValueError('numeric pipeline INPUT names must be ordinary')
    validate_counted_step(step,schema)
    validate_projection_context(step,version,prefix=1)
    return {'arrays':arrays,'inline_rows':inline_rows,'features':tuple(sorted(features))}
