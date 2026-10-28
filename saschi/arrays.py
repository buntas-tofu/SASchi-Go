"""DS-039 numeric source-array declarations and independent plan validation.

Array metadata stays in declaration operations, so old plan/receipt shapes do
not change. Each reference resolves into the current row's named variables.
"""
from __future__ import annotations

import re
from .functions import FUNCTIONS, LAG_FUNCTIONS, expression_nodes
from .operations import walk_operations
from .values import column_type
from sas_semantics import (SAS_NUMERIC_ARRAY_LIMIT, sas_numeric_array_value,
                           sas_numeric_array_index, sas_numeric_array_add, sas_numeric_array_sum)

NAME = r'[a-z_][a-z0-9_]{0,31}'
RESERVED = {'_n_', '_error_', '_all_', '_numeric_', '_character_', '_temporary_',
            '_infile_', '_file_', '_ods_', '_page_', '_blankpage_'}
ARRAY_RESERVED = RESERVED | set(FUNCTIONS) | {
    'array', 'data', 'do', 'end', 'if', 'else', 'set', 'merge', 'retain',
    'length', 'output', 'where', 'run', 'quit'}
KINDS = {'array_get', 'array_sum', 'array_current'}


def ordinary(name):
    return isinstance(name, str) and re.fullmatch(NAME, name) and name not in RESERVED


def declaration(text, *, preserve_mode=False):
    """Parse only the documented bounded syntax; reject all leftover text."""
    match = re.fullmatch(r'array\s+(' + NAME + r')(?=\s|[({\[]|$)\s*(.*)', text.lower(), re.S)
    if not match:
        raise ValueError('numeric ARRAY requires an ordinary name and fixed element list')
    name, rest = match.groups()
    if name in ARRAY_RESERVED:
        raise ValueError('numeric ARRAY name conflicts with a function, statement or automatic name')
    extent = None
    if rest.startswith(('{', '[', '(')):
        close = {'{': '}', '[': ']', '(': ')'}[rest[0]]
        end = rest.find(close)
        if end < 0:
            raise ValueError('numeric ARRAY declaration has unclosed bounds')
        extent, rest = rest[1:end].strip(), rest[end + 1:].strip()
    names = []
    # A numbered name range is not the PDV-order double-dash list syntax.
    while rest:
        item = re.match(r'(' + NAME + r')(?:\s*-\s*(' + NAME + r'))?(?=\s|$)', rest)
        if not item:
            raise ValueError('numeric ARRAY supports explicit names/numbered ranges; type, initializer and other lists require review')
        first, last = item.groups()
        if last is None:
            names.append(first)
        else:
            a, b = re.fullmatch(r'([a-z_][a-z0-9_]*?)([0-9]+)', first), re.fullmatch(r'([a-z_][a-z0-9_]*?)([0-9]+)', last)
            if (not a or not b or a[1] != b[1] or a[2].startswith('0') or b[2].startswith('0') or
                    not 1 <= int(a[2]) <= int(b[2]) <= int(a[2]) + SAS_NUMERIC_ARRAY_LIMIT - 1):
                raise ValueError('numeric ARRAY numbered ranges require an ascending shared prefix and unpadded positive suffixes')
            names.extend(a[1] + str(i) for i in range(int(a[2]), int(b[2]) + 1))
        if len(names) > SAS_NUMERIC_ARRAY_LIMIT:
            raise ValueError('numeric ARRAY exceeds the1024-element policy')
        rest = rest[item.end():].strip()
    lower = 1
    if extent in (None, '*'):
        if not names:
            raise ValueError('inferred numeric ARRAY extent requires a nonempty element list')
        size = len(names)
    elif re.fullmatch(r'[+-]?[0-9]+(?:\s*:\s*[+-]?[0-9]+)?', extent):
        bounds = [int(v.strip()) for v in extent.split(':')]
        lower, size = (bounds[0], bounds[1] - bounds[0] + 1) if len(bounds) == 2 else (1, bounds[0])
        sas_numeric_array_index(lower, lower, size)
        if not names:
            names = [name + str(i + 1) for i in range(size)]
        if len(names) != size:
            raise ValueError('numeric ARRAY extent must equal its element count')
    else:
        raise ValueError('numeric ARRAY requires fixed integer bounds or inferred * extent')
    result = {'name': name, 'lower': lower, 'names': names}
    if preserve_mode and extent is None:
        result['mode'] = 'implicit'
    validate_declaration(result)
    return result


def validate_declaration(args):
    if not isinstance(args, dict) or set(args) not in ({'name', 'lower', 'names'}, {'name', 'lower', 'names', 'mode'}):
        raise ValueError('numeric ARRAY plan requires name/lower/names and optional implicit mode')
    if 'mode' in args and (args['mode'] != 'implicit' or type(args['lower']) is not int or args['lower'] != 1):
        raise ValueError('DO OVER declaration requires implicit mode and lower bound1')
    name, names = args['name'], args['names']
    if (not ordinary(name) or name in ARRAY_RESERVED or not isinstance(names, list) or
            not names or len(names) > SAS_NUMERIC_ARRAY_LIMIT or
            any(not ordinary(n) or n == name for n in names) or len(names) != len(set(names))):
        raise ValueError('numeric ARRAY requires unique ordinary element names distinct from its array name')
    sas_numeric_array_index(args['lower'], args['lower'], len(names))


def contains_array(value):
    return any(n.get('kind') in KINDS for n, _ in expression_nodes(value))


def literal(expr):
    """Known new-profile literals; references keep their dynamic schedule."""
    kind = expr['kind']
    if kind in ('number', 'missing'):
        return True, expr['value']
    if kind == 'arithmetic':
        a, x = literal(expr['left']); b, y = literal(expr['right'])
        if a and b:
            return True, sas_numeric_array_add(x, y, expr['op'] == '-')
    return False, None


def validate_expression(expr, arrays, schema=None, depth=0, current=None):
    if depth > 32 or not isinstance(expr, dict):
        raise ValueError('numeric array expression exceeds the32-level profile or is malformed')
    kind = expr.get('kind')
    if kind in ('number', 'missing'):
        if (set(expr) != {'kind', 'value'} or kind == 'missing' and expr['value'] is not None
                or kind == 'number' and expr['value'] is None):
            raise ValueError('numeric array literal is malformed')
        sas_numeric_array_value(expr['value'])
    elif kind in ('variable', 'automatic'):
        if (set(expr) != {'kind', 'value'} or
                kind == 'automatic' and expr['value'] != '_n_' or
                kind == 'variable' and (not ordinary(expr['value']) or expr['value'] in arrays)):
            raise ValueError('numeric array expressions require ordinary numeric variables or _N_')
        if schema is not None and column_type(schema.get(expr['value'], 'number')) != 'number':
            raise ValueError('numeric array expression cannot coerce a character descriptor')
    elif kind == 'arithmetic':
        if set(expr) != {'kind', 'left', 'op', 'right'} or expr['op'] not in ('+', '-'):
            raise ValueError('numeric array expressions support exact bounded + and - only; store other function results first')
        for side in ('left', 'right'):
            validate_expression(expr[side], arrays, schema, depth + 1, current)
        literal(expr)
    elif kind in KINDS:
        expected = {'kind', 'name', 'index'} if kind == 'array_get' else {'kind', 'name'}
        if set(expr) != expected or not isinstance(expr['name'], str) or expr['name'] not in arrays:
            raise ValueError('numeric array reference requires a preceding declaration in this DATA step')
        if kind == 'array_current' and (expr['name'] != current or arrays[expr['name']].get('mode') != 'implicit'):
            raise ValueError('current element requires its active implicit DO OVER loop')
        if kind == 'array_get':
            if arrays[expr['name']].get('mode') == 'implicit':
                raise ValueError('mixed indexed/current references to a DO OVER array require review')
            validate_expression(expr['index'], arrays, schema, depth + 1, current)
            known, value = literal(expr['index'])
            if known:
                a = arrays[expr['name']]
                sas_numeric_array_index(value, a['lower'], len(a['names']))
    else:
        raise ValueError('numeric array expression requires bounded numeric operands; calls/coercion/tags require review')


def validate_step(step, schema=None):
    """Enforce source order and plan shape, independently of compiler admission."""
    roots = step['operations']; flat = list(walk_operations(roots))
    if not any(op['kind'] in ('array_declare', 'array_set', 'array_current_set', 'do_over') or contains_array(op['args']) for op in flat) and not contains_array(step.get('where')):
        return {}
    if step['kind'] != 'data' or contains_array(step.get('where')):
        raise ValueError('numeric arrays require DATA execution; MERGE and array references in WHERE are deferred')
    if any(op['kind'] in ('array_declare', 'array_set', 'array_current_set', 'do_over') and not isinstance(op['args'], dict) for op in flat):
        raise ValueError('numeric array operation arguments must be mappings')
    all_names = [op['args'].get('name') for op in flat if op['kind'] == 'array_declare']
    if any(not isinstance(n, str) for n in all_names):
        raise ValueError('numeric ARRAY names must be strings')
    all_names = set(all_names)
    for op in flat:
        if op['kind'] == 'do_over':
            args = op['args']
            if (not any(op is root for root in roots) or not isinstance(args, dict)
                    or set(args) != {'name', 'body'} or not isinstance(args['name'], str)
                    or not isinstance(args['body'], list)):
                raise ValueError('DO OVER requires name/body only as an unconditional single-level loop')
            allowed = {'assign', 'array_current_set', 'if', 'put', 'put_literal', 'put_numeric_list', 'output'}
            if any(node.get('kind') == 'call' and node.get('name') in LAG_FUNCTIONS
                   for node, _ in expression_nodes(args)):
                raise ValueError('DO OVER queue scheduling requires separate review')
            if any(node.get('kind') == 'array_get' for node, _ in expression_nodes(args)):
                raise ValueError('indexed array reads inside DO OVER require composition review')
            for child in walk_operations(args['body']):
                if child['kind'] not in allowed:
                    raise ValueError('DO OVER body requires bounded assignments, IF/ELSE, PUT or OUTPUT')
    contexts = [root['args']['name'] if root['kind'] == 'do_over' and child is not root else None
                for root in roots for child in walk_operations([root])]
    if any(op['kind'] == 'do_over' for op in flat):
        if '_i_' in set(step.get('retained', {})) | set(step['by']) | set(schema or {}):
            raise ValueError('DO OVER implicit index _I_ is internal in this profile')
        for node, _ in expression_nodes(step):
            if (node.get('name') == '_i_' or node.get('value') == '_i_'
                    or isinstance(node.get('names'), list) and '_i_' in node['names']):
                raise ValueError('DO OVER implicit index _I_ is internal in this profile')
    arrays, cells, budget = {}, set(), 0
    for op, current in zip(flat, contexts):
        kind, args = op['kind'], op['args']
        if kind == 'array_declare':
            if not any(op is root for root in roots):
                raise ValueError('numeric ARRAY declarations must be unconditional DATA-step statements')
            validate_declaration(args)
            if args['name'] in arrays or any(n in all_names for n in args['names']):
                raise ValueError('numeric ARRAY names cannot collide with other arrays or elements')
            if sum(len(a['names']) for a in arrays.values()) + len(args['names']) > SAS_NUMERIC_ARRAY_LIMIT:
                raise ValueError('numeric arrays exceed the1024-element step policy')
            arrays[args['name']] = args
            cells.update(args['names'])
        elif kind == 'do_over':
            if args['name'] not in arrays or arrays[args['name']].get('mode') != 'implicit':
                raise ValueError('DO OVER requires a preceding implicit ARRAY declaration')
        elif kind == 'array_current_set':
            if set(args) != {'name', 'value'}:
                raise ValueError('current-element assignment requires name/value only')
            validate_expression({'kind': 'array_current', 'name': args['name']}, arrays, schema, current=current)
            validate_expression(args['value'], arrays, schema, current=current)
        elif kind == 'array_set':
            if set(args) != {'name', 'index', 'value'}:
                raise ValueError('numeric array assignment requires name/index/value only')
            validate_expression({'kind': 'array_get', 'name': args['name'], 'index': args['index']}, arrays, schema)
            validate_expression(args['value'], arrays, schema)
        elif contains_array({k: v for k, v in args.items() if k not in ('body', 'operation', 'otherwise')}):
            if kind in ('assign', 'sum_statement'):
                validate_expression(args['value'], arrays, schema, current=current)
            elif kind in ('if', 'subset', 'do_until', 'do_while'):
                # Body/branch expressions are checked at their own source positions.
                for side in ('left', 'right'):
                    if side in args['condition']:
                        validate_expression(args['condition'][side], arrays, schema, current=current)
            else:
                raise ValueError('array references in this operation require composition review')
        payload = {k: v for k, v in args.items() if k not in ('body', 'operation', 'otherwise')}
        if kind in ('array_set', 'array_current_set') or contains_array(payload):
            budget += sum(1 for n, _ in expression_nodes(payload) if 'kind' in n)
        if budget > 128:
            raise ValueError('numeric array expressions exceed the128-node step policy')
    for op in flat:
        kind, args = op['kind'], op['args']
        if kind in ('assign', 'round', 'sum_statement', 'declare') and args.get('name') in all_names:
            raise ValueError('an array name is not a scalar DATA-row variable')
        if kind == 'do_counted' and args['index'] in all_names | cells:
            raise ValueError('numeric array names/elements cannot be counted DO indices in this slice')
        for node, _ in expression_nodes(args):
            if node.get('kind') == 'variable' and node.get('value') in all_names:
                raise ValueError('bare array-name references require their active DO OVER loop')
        if kind in ('put', 'put_numeric_list') and any(n in all_names for n in args['names']):
            raise ValueError('PUT cannot emit an array name as a scalar')
        if kind == 'sum_statement' and args['name'] in cells:
            raise ValueError('array-element sum retention requires separate characterization')
        if kind == 'assign' and args['name'] in cells and args['value'].get('kind') in ('character', 'concat'):
            raise ValueError('numeric array elements cannot have character assignments')
        if kind == 'declare' and args['name'] in cells and column_type(args['spec']) != 'number':
            raise ValueError('numeric array elements cannot have character declarations')
    if cells & (set(step.get('retained', {})) | set(step['by'])):
        raise ValueError('retained or BY-key array elements require separate characterization')
    if schema is not None:
        if all_names & set(schema):
            raise ValueError('array names cannot collide with DATA-row descriptors')
        if any(column_type(schema[n]) != 'number' for n in cells):
            raise ValueError('numeric arrays require numeric element descriptors, even for empty input')
    return arrays


def value(expr, row, arrays, current=None):
    """Evaluate only the validated exact numeric array-expression profile."""
    kind = expr['kind']
    if kind in ('number', 'missing'):
        return sas_numeric_array_value(expr['value'])
    if kind in ('variable', 'automatic'):
        return sas_numeric_array_value(row.get(expr['value']))
    if kind == 'arithmetic':
        return sas_numeric_array_add(value(expr['left'], row, arrays, current), value(expr['right'], row, arrays, current), expr['op'] == '-')
    if kind in KINDS:
        a = arrays[expr['name']]
        if kind == 'array_sum':
            return sas_numeric_array_sum([row.get(n) for n in a['names']])
        if kind == 'array_current':
            if current is None or expr['name'] not in current:
                raise ValueError('current element has no active DO OVER binding')
            index = current[expr['name']]
        else:
            index = sas_numeric_array_index(value(expr['index'], row, arrays, current), a['lower'], len(a['names']))
        return sas_numeric_array_value(row.get(a['names'][index]))
    raise ValueError('expression is outside the numeric array profile')
