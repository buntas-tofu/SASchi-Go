"""DS-066..068 profile-local unary mathematics and ordered argument SUM.

Old registries, profiles, array names and exact index/control evaluators remain
unchanged. Invalid domains refuse instead of simulating SAS diagnostics.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import math

from . import binary64, numeric_pipeline
from .functions import expression_nodes

PROFILE = 'binary64-math-v1'
UNARY = frozenset({'sqrt', 'log'})
CALLS = binary64.CALLS | UNARY | {'sum'}
FUNCTIONS = binary64.FUNCTIONS | UNARY
_parsing = ContextVar('saschi_numeric_math_parser', default=False)
_strict_source = ContextVar('saschi_numeric_math_strict_source', default=False)
_parse_depth = ContextVar('saschi_numeric_math_parse_depth', default=0)


@contextmanager
def parser_scope(source=''):
    import re
    from .parser import split_statements, Kind, ParseError
    try:
        texts = ['' if any(t.kind == Kind.DATA for t in s.tokens) else
                 re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", '', s.text) for s in split_statements(source)]
    except ParseError:
        texts = []
    new, summed, rounded = False, False, False
    for text in texts:
        if re.match(r'^data\s', text, re.I):
            summed, rounded = False, False
        new = new or bool(re.search(r'\b(?:sqrt|log)\s*\(', text, re.I))
        summed = summed or bool(re.search(r'\bsum\s*\((?!\s*of\b)', text, re.I))
        rounded = rounded or '**' in text or bool(re.search(r'\b(?:constant|sin|cos|tan|arsin|arcos|atan)\s*\(', text, re.I))
        new = new or summed and rounded
    token = _parsing.set(True)
    strict_token = _strict_source.set(new)
    try:
        yield
    finally:
        _parsing.reset(token)
        _strict_source.reset(strict_token)


def strict_source():
    return _strict_source.get()


def parse_call(text, strict=False):
    from .plan import CALL, _split_args, expression
    match = CALL.fullmatch(text.strip())
    if not _parsing.get() or not match or match[1].lower() not in UNARY:
        return None
    depth = _parse_depth.get()
    if depth >= 32:
        return None
    parts = _split_args(match[2])
    if parts is None or len(parts) != 1:
        return None
    token = _parse_depth.set(depth + 1)
    try:
        arg = expression(parts[0], strict=strict)
    finally:
        _parse_depth.reset(token)
    return None if arg is None else {'kind':'call', 'name':match[1].lower(), 'args':[arg]}


def selected(operations):
    nodes = [n for n, _ in expression_nodes(operations)]
    new = any(n.get('kind') == 'call' and isinstance(n.get('name'), str) and n['name'] in UNARY for n in nodes)
    summed = any(n.get('kind') == 'call' and n.get('name') == 'sum' for n in nodes)
    rounded = any(n.get('kind') == 'arithmetic' and n.get('op') == '**' or
                  n.get('kind') == 'call' and isinstance(n.get('name'), str) and n['name'] in binary64.FUNCTIONS for n in nodes)
    return new or summed and rounded


def has_marker(step):
    pending, seen = [step], set()
    while pending:
        node = pending.pop()
        if not isinstance(node, (dict, list, tuple)):
            continue
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, dict):
            if node.get('kind') == 'numeric_profile' and node.get('args') == {'name':PROFILE}:
                return True
            pending.extend(node.values())
        else:
            pending.extend(node)
    return False


def arity(name):
    return (1, 1024) if name == 'sum' else (1, 1)


def apply(name, values):
    if not isinstance(name, str) or name not in CALLS or not isinstance(values, (list, tuple)):
        raise ValueError('numeric math call requires its supported name and argument list')
    lower, upper = arity(name)
    if not lower <= len(values) <= upper:
        raise ValueError('numeric math call has unsupported arity')
    if name == 'sum':
        return numeric_pipeline.array_sum(values)
    if name not in UNARY:
        return binary64.apply(name, values)
    value = binary64.numeric(values[0])
    if value is None:
        return None
    if name == 'sqrt' and value < 0:
        raise ValueError('numeric math SQRT requires a nonnegative argument')
    if name == 'log' and value <= 0:
        raise ValueError('numeric math LOG requires a positive argument')
    return binary64.numeric((math.sqrt if name == 'sqrt' else math.log)(value))


def validate_step(step, version=2, schema=None):
    if not has_marker(step):
        return None
    binary64._structure(step)
    if not selected(step.get('operations', [])):
        raise ValueError('numeric math requires executable SQRT/LOG or argument SUM with a rounded trigger')
    context = numeric_pipeline._validate_step(step, version, schema, profile=PROFILE,
        calls=CALLS, functions=FUNCTIONS, apply_function=apply, call_arity=arity,
        require_features=False)
    called = {n['name'] for n, _ in expression_nodes(step['operations']) if n.get('kind') == 'call' and isinstance(n.get('name'), str)}
    if called & set(context['arrays']):
        raise ValueError('numeric math calls cannot collide with a declared array name')
    context['math_profile'] = True
    return context


def reject_unmarked_calls(step):
    if not isinstance(step, dict) or has_marker(step):
        return
    for node, _ in expression_nodes(step.get('operations', [])):
        if node.get('kind') == 'call' and isinstance(node.get('name'), str) and node['name'] in UNARY:
            raise ValueError('SQRT/LOG requires the separate numeric math profile')


def evaluate(expr, row, arrays=None, current=None):
    arrays = {} if arrays is None else arrays
    kind = expr['kind']
    if kind == 'call':
        values = ([expr['args'][0]['value']] if expr['name'] == 'constant' else
                  [evaluate(arg, row, arrays, current) for arg in expr['args']])
        return apply(expr['name'], values)
    if kind == 'arithmetic':
        return binary64.arithmetic(expr['op'], evaluate(expr['left'], row, arrays, current),
                                   evaluate(expr['right'], row, arrays, current))
    return numeric_pipeline.evaluate(expr, row, arrays, current)


def array_set(args, row, arrays, current=None):
    position = numeric_pipeline.array_index(args['name'], args['index'], row, arrays, current)
    row[arrays[args['name']]['names'][position]] = evaluate(args['value'], row, arrays, current)


def array_current_set(args, row, arrays, current):
    if not isinstance(current, dict) or args['name'] not in current:
        raise ValueError('numeric math current assignment has no active binding')
    position = current[args['name']]
    if type(position) is not int or not 0 <= position < len(arrays[args['name']]['names']):
        raise ValueError('numeric math current array offset is invalid')
    row[arrays[args['name']]['names'][position]] = evaluate(args['value'], row, arrays, current)
