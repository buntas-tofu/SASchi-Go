"""DS-041 captured integer controls and bounded counted-loop plan validation."""
import re

from sas_semantics import sas_counted_control, sas_counted_capture
from .arrays import ordinary
from .functions import expression_nodes, LAG_FUNCTIONS
from .operations import walk_operations
from .values import column_type

FIELDS = {'index', 'start', 'stop', 'by', 'body'}
PROFILE = 'bounded'
MAX_DEPTH = 8


def parse_control(text):
    """Linear tokenization and bounded recursive descent; no calls or coercion."""
    if not text.isascii():
        raise ValueError('counted control syntax requires ASCII')
    text = text.strip().lower()
    if len(text) > 4096:
        raise ValueError('counted control source exceeds4096 characters')
    if re.fullmatch(r'[+-]?[0-9]+', text):
        if len(text.lstrip('+-0')) > 10:
            raise ValueError('counted integer literal is outside the bounded range')
        return sas_counted_control(int(text))
    tokens, pos = [], 0
    token = re.compile(r'\s*([0-9]+|[a-z_][a-z0-9_]{0,31}|[()+-])', re.ASCII)
    while pos < len(text):
        match = token.match(text, pos)
        if not match:
            raise ValueError('computed counted controls require integer literals, variables, _N_ and +/-')
        tokens.append(match[1]); pos = match.end()
        if len(tokens) > 128:
            raise ValueError('counted control exceeds128 tokens')
    position = 0

    def primary(depth):
        nonlocal position
        if depth > 32 or position == len(tokens):
            raise ValueError('counted control is malformed or exceeds32 levels')
        item = tokens[position]; position += 1
        if item in ('+', '-'):
            child = primary(depth + 1)
            return child if item == '+' else {'kind': 'arithmetic', 'op': '-',
                'left': {'kind': 'number', 'value': 0}, 'right': child}
        if item == '(':
            child = addition(depth + 1)
            if position == len(tokens) or tokens[position] != ')':
                raise ValueError('counted control has unclosed parentheses')
            position += 1
            return child
        if item.isascii() and item.isdigit():
            if len(item.lstrip('0')) > 10:
                raise ValueError('counted integer literal is outside the bounded range')
            return {'kind': 'number', 'value': sas_counted_control(int(item))}
        if item == '_n_' or ordinary(item):
            return {'kind': 'automatic' if item == '_n_' else 'variable', 'value': item}
        raise ValueError('counted control requires an ordinary numeric operand')

    def addition(depth):
        nonlocal position
        left = primary(depth)
        while position < len(tokens) and tokens[position] in ('+', '-'):
            operator = tokens[position]; position += 1
            left = {'kind': 'arithmetic', 'op': operator, 'left': left, 'right': primary(depth)}
        return left

    result = addition(0)
    if position != len(tokens):
        raise ValueError('unconsumed counted control syntax')
    validate_control(result)
    return result


def validate_control(expr, schema=None, depth=0):
    if depth > 32:
        raise ValueError('counted control exceeds32 expression levels')
    if type(expr) is int:
        sas_counted_control(expr)
        return
    if not isinstance(expr, dict):
        raise ValueError('counted control requires an integer or expression mapping')
    kind = expr.get('kind')
    if not isinstance(kind, str):
        raise ValueError('counted control kind must be a string')
    if kind == 'arithmetic':
        if set(expr) != {'kind', 'op', 'left', 'right'} or expr['op'] not in ('+', '-'):
            raise ValueError('counted control supports exact integer +/- only')
        for side in ('left', 'right'):
            validate_control(expr[side], schema, depth + 1)
    elif kind in ('number', 'variable', 'automatic') and set(expr) == {'kind', 'value'}:
        value = expr['value']
        if kind == 'number':
            sas_counted_control(value)
        elif (kind == 'variable' and not ordinary(value)
              or kind == 'automatic' and value != '_n_'):
            raise ValueError('counted control requires ordinary variables or _N_')
        elif schema is not None and column_type(schema.get(value, 'number')) != 'number':
            raise ValueError('counted control cannot coerce a character descriptor')
    else:
        raise ValueError('counted control calls, arrays, missing and tags require separate review')
    if constant(expr):
        evaluate_control(expr, {})


def constant(expr):
    return type(expr) is int or expr['kind'] == 'number' or (
        expr['kind'] == 'arithmetic' and constant(expr['left']) and constant(expr['right']))


def evaluate_control(expr, row):
    if type(expr) is int:
        return sas_counted_control(expr)
    kind = expr['kind']
    if kind == 'arithmetic':
        left = evaluate_control(expr['left'], row)
        right = evaluate_control(expr['right'], row)
        return sas_counted_control(left + right if expr['op'] == '+' else left - right)
    return sas_counted_control(expr['value'] if kind == 'number' else row.get(expr['value']))


def validate_step(step, schema=None):
    """Check sparse profile markers and nesting independently of compilation."""
    flat = list(walk_operations(step['operations']))
    bounded = [op for op in flat if op['kind'] == 'do_counted' and 'profile' in op['args']]
    if not bounded:
        return False
    if step['kind'] != 'data':
        raise ValueError('bounded counted loops require a DATA step')
    node_count = 0
    seen = set()

    def check(loop, ancestors):
        nonlocal node_count
        args = loop['args']
        if type(loop['line']) is not int or loop['line'] < 1:
            raise ValueError('bounded counted source line must be a positive integer')
        if set(args) != FIELDS | {'profile'} or args['profile'] != PROFILE:
            raise ValueError('bounded counted DO requires exact fields and bounded profile')
        index = args['index']
        if not ordinary(index) or index in ancestors or len(ancestors) >= MAX_DEPTH:
            raise ValueError('counted DO requires distinct active indices and at most8 levels')
        seen.add(id(loop))
        for key in ('start', 'stop', 'by'):
            expr = args[key]
            validate_control(expr, schema)
            nodes = list(expression_nodes(expr))
            node_count += max(1, len(nodes))
            if any(n.get('kind') == 'variable' and n.get('value') == index for n, _ in nodes):
                raise ValueError('counted controls cannot reference their own index')
        if node_count > 128:
            raise ValueError('counted controls exceed128 expression nodes per step')
        if constant(args['by']) and evaluate_control(args['by'], {}) == 0:
            raise ValueError('counted DO BY must be nonzero')
        if all(constant(args[k]) for k in ('start', 'stop', 'by')):
            sas_counted_capture(*(evaluate_control(args[k], {}) for k in ('start', 'stop', 'by')), 0)
        active = ancestors + (index,)
        children = list(walk_operations(args['body']))
        if len(children) > 256:
            raise ValueError('bounded counted body exceeds256 operations')
        if any(n.get('kind') == 'call' and n.get('name') in LAG_FUNCTIONS
               for n, _ in expression_nodes(args['body'])):
            raise ValueError('bounded counted LAG/DIF scheduling requires separate review')
        allowed = {'assign', 'array_set', 'round', 'sum_statement', 'if', 'put',
                   'put_literal', 'put_character_list', 'put_numeric_list', 'put_mixed_numeric', 'output',
                   'declare', 'do_counted'}
        for child in children:
            if child['kind'] not in allowed:
                raise ValueError('bounded counted body operation requires separate review')
            if child['kind'] in ('assign', 'round', 'sum_statement', 'declare') and child['args'].get('name') in active:
                raise ValueError('counted body cannot write or redeclare any active index')
        for pos, child in enumerate(args['body']):
            if child['kind'] == 'declare':
                following = args['body'][pos + 1] if pos + 1 < len(args['body']) else {}
                if (following.get('kind') != 'do_counted' or
                        child['args'] != {'name': following['args'].get('index'), 'spec': 'number'}):
                    raise ValueError('nested declaration must introduce the immediately following counted index')
            if child['kind'] == 'do_counted':
                if pos == 0 or args['body'][pos - 1]['kind'] != 'declare':
                    raise ValueError('nested counted index needs its preceding declaration')
                check(child, active)
        # A nested loop/declare hidden in an IF is not an admitted container.
        direct = {id(c) for c in args['body']}
        for child in children:
            if child['kind'] == 'do_counted' and id(child) not in seen:
                raise ValueError('counted loops cannot be conditional or have unmarked parents')
            if child['kind'] == 'declare' and id(child) not in direct:
                # Descendant declarations belong to their nested loop's body.
                if not any(child is c for nested in children if nested['kind'] == 'do_counted'
                           for c in nested['args']['body']):
                    raise ValueError('conditional declarations require separate review')

    for root in step['operations']:
        if root['kind'] == 'do_counted' and 'profile' in root['args']:
            check(root, ())
    if any(id(op) not in seen for op in bounded):
        raise ValueError('bounded counted loops require a top-level counted root')
    return True
