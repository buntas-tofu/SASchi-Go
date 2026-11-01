"""DS-070 explicit finite uint32 scalar diagnostic record, at most67 bytes."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import math
import re

from sas_semantics import SAS_BITWISE_ARITY, sas_bitwise, sas_bitwise_integer

PROFILE = 'bitwise-put-all-67-v1'
KIND = 'bitwise_data'
OPERATION = 'put_all_67'
STEP_KEYS = frozenset(('kind', 'name', 'line', 'inputs', 'by', 'operations', 'nodupkey',
                       'where', 'retained', 'lengths', 'display_names'))
NAME = re.compile(r'[a-z_][a-z0-9_]{0,31}\Z', re.ASCII)
SOURCE_NAME = r'[A-Za-z_][A-Za-z0-9_]{0,31}'
NUMBER = r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'
RESERVED = frozenset(('_null_', '_n_', '_error_', '_all_', '_numeric_', '_character_',
                      '_temporary_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_'))
TAIL = '_ERROR_=0 _N_=1 '


def ordinary(value):
    return type(value) is str and NAME.fullmatch(value) is not None and value not in RESERVED


def refuse_legacy(value):
    """Keep the explicit family out of old trees, with linear DAG traversal."""
    pending, active, completed = [(value, False)], set(), set()
    while pending:
        item, leaving = pending.pop()
        if type(item) not in (dict, list, tuple):
            continue
        identity = id(item)
        if leaving:
            active.remove(identity); completed.add(identity)
            continue
        if identity in completed:
            continue
        if identity in active:
            raise ValueError('cyclic portable containers are invalid')
        active.add(identity); pending.append((item, True))
        if type(item) is dict:
            if item.get('kind') == KIND or item.get('kind') == OPERATION or item.get('profile') == PROFILE:
                raise ValueError('bitwise67 output requires its explicit bitwise_data family')
            children = item.values()
        else:
            children = item
        pending.extend((child, False) for child in children if type(child) in (dict, list, tuple))


def uint32(value):
    if type(value) not in (int, float) or not 0 <= value <= 4294967295:
        raise ValueError('bitwise67 values require finite numeric uint32, not missing/bool/text')
    return float(sas_bitwise_integer(value))


def literal(token):
    if type(token) is not str or len(token) > 32 or re.fullmatch(NUMBER, token, re.ASCII) is None:
        raise ValueError('bitwise67 source requires bounded ordinary decimal uint32 literals')
    exponent = re.split('[eE]', token)
    if len(exponent) == 2 and abs(int(exponent[1])) > 32:
        raise ValueError('bitwise67 literal exponent exceeds the bounded32 policy')
    try:
        exact = Decimal(token)
        if not exact.is_finite() or exact < 0 or exact > 4294967295 or exact != exact.to_integral_value():
            raise ValueError('bitwise67 source literals require exact uint32 values')
    except InvalidOperation as error:
        raise ValueError('invalid bitwise67 numeric literal') from error
    return float(exact)


def render(row, display):
    pieces = []
    for name, value in row.items():
        shown = display[name]
        pieces.append(shown + '=' + str(int(uint32(value))) + ' ')
    record = ''.join(pieces) + TAIL
    if len(record.encode('ascii')) > 67:
        raise ValueError('bitwise67 output beyond67 columns is outside the explicit policy')
    return record


def validate_step(step, version=2):
    if (type(version) is not int or version != 2 or type(step) is not dict or set(step) != STEP_KEYS or
            step.get('kind') != KIND or step.get('name') != '_null_' or type(step.get('line')) is not int or step['line'] < 1 or
            type(step.get('inputs')) is not list or step['inputs'] != [] or type(step.get('by')) is not list or step['by'] != [] or
            step.get('nodupkey') is not False or step.get('where') is not None or
            any(type(step.get(key)) is not dict or step[key] != {} for key in ('retained', 'lengths')) or
            type(step.get('display_names')) is not dict or type(step.get('operations')) is not list or not 2 <= len(step['operations']) <= 65):
        raise ValueError('bitwise67 requires exact version2 scalar DATA_NULL Step defaults')
    ops = step['operations']; row = {}; schema = {}; events = []; statistics = {'nodes': 0, 'calls': 0}
    active = set()
    def expression(node, depth=0):
        if type(node) is not dict or type(node.get('kind')) is not str or depth > 32:
            raise ValueError('bitwise67 expression shape/depth exceeds the bounded profile')
        statistics['nodes'] += 1
        if statistics['nodes'] > 128:
            raise ValueError('bitwise67 expressions exceed128 nodes')
        if id(node) in active:
            raise ValueError('cyclic bitwise67 expression')
        active.add(id(node))
        try:
            kind = node['kind']
            if kind == 'number' and set(node) == {'kind', 'value'}:
                return uint32(node['value'])
            if kind == 'variable' and set(node) == {'kind', 'value'} and ordinary(node['value']):
                if node['value'] not in row:
                    raise ValueError('bitwise67 variables must be assigned before use')
                return row[node['value']]
            if (kind == 'call' and set(node) == {'kind', 'name', 'args'} and type(node['name']) is str and
                    node['name'] in SAS_BITWISE_ARITY and type(node['args']) is list and len(node['args']) == SAS_BITWISE_ARITY[node['name']]):
                values = [expression(child, depth + 1) for child in node['args']]
                statistics['calls'] += 1
                return uint32(sas_bitwise(node['name'], *values))
            raise ValueError('bitwise67 permits only uint32 numbers,prior variables and existing bitwise calls')
        finally:
            active.remove(id(node))
    previous = step['line']
    for index, operation in enumerate(ops):
        if (type(operation) is not dict or set(operation) != {'kind', 'line', 'args'} or
                type(operation.get('line')) is not int or operation['line'] < previous or type(operation.get('args')) is not dict):
            raise ValueError('bitwise67 operations require exact ordered source shapes')
        previous = operation['line']; args = operation['args']
        if index == len(ops) - 1:
            if operation['kind'] != OPERATION or args != {'profile': PROFILE}:
                raise ValueError('bitwise67 requires exactly one final explicitly profiled output')
        else:
            if operation['kind'] != 'assign' or set(args) != {'name', 'value'} or not ordinary(args.get('name')):
                raise ValueError('bitwise67 requires only ordinary scalar assignments before final output')
            value = expression(args['value']); name = args['name']
            if name not in row:
                schema[name] = 'number'
            row[name] = value
            if len(row) > 16:
                raise ValueError('bitwise67 permits at most16 scalar variables')
            events.append({'kind': 'assign', 'line': operation['line'], 'name': name, 'value': value})
    if statistics['calls'] < 1:
        raise ValueError('bitwise67 requires an actual existing bitwise call')
    display = step['display_names']
    if (list(display) != list(row) or any(type(shown) is not str or not shown.isascii() or
            re.fullmatch(SOURCE_NAME, shown, re.ASCII) is None or shown.lower() != name for name, shown in display.items())):
        raise ValueError('bitwise67 display names must be complete first-source spellings in PDV order')
    record = render(row, display)
    fields = [{'name': display[name], 'kind': 'number', 'value': value} for name, value in row.items()]
    events.append({'kind': OPERATION, 'line': ops[-1]['line'], 'record': record, 'fields': fields})
    return {'schema': schema, 'display_names': deepcopy(display), 'row': row, 'record': record,
            'assignments': len(ops) - 1, 'bitwise_calls': statistics['calls'], 'events': events}


def execute_step(step, tables=None, version=2, trace=None):
    context = validate_step(step, version)
    if tables is not None and (type(tables) is not dict or tables):
        raise ValueError('bitwise67 requires an empty initial catalog')
    if trace is not None:
        if type(trace) is not list:
            raise ValueError('bitwise67 trace requires a list')
        trace.extend(deepcopy(context['events']))
    return {'datasets': {}, 'log': [context['record']]}


def source_guard(statements):
    from .parser import Kind
    if (not 4 <= len(statements) <= 67 or not all(st.terminated for st in statements) or
            re.fullmatch(r'data\s+_null_', statements[0].text, re.I | re.ASCII) is None or
            statements[-1].text.lower() != 'run' or
            re.fullmatch(r'put\s+_all_', statements[-2].text, re.I | re.ASCII) is None):
        raise ValueError('bitwise67 source requires one complete DATA_NULL,assignments,final PUT_ALL and RUN')
    tokenizer = re.compile(r'\s*(?:(' + NUMBER + r')|(' + SOURCE_NAME + r')|([(),]))', re.ASCII)
    for statement in statements[1:-2]:
        if any(token.kind in (Kind.STRING, Kind.DATA) for token in statement.tokens) or not statement.text.isascii():
            raise ValueError('bitwise67 source requires ASCII scalar numeric expressions')
        assignment = re.fullmatch(r'(' + SOURCE_NAME + r')\s*=\s*(.+)', statement.text, re.ASCII | re.S)
        if assignment is None or not ordinary(assignment[1].lower()):
            raise ValueError('bitwise67 source body permits ordinary assignments only')
        expression = assignment[2]; position = 0; depth = 0
        while position < len(expression):
            match = tokenizer.match(expression, position)
            if match is None:
                if expression[position:].strip() == '': break
                raise ValueError('bitwise67 source has an unsupported expression token')
            if match[1] is not None: literal(match[1])
            if match[3] == '(': depth += 1
            elif match[3] == ')': depth -= 1
            if not 0 <= depth <= 32:
                raise ValueError('bitwise67 source call nesting exceeds32 levels')
            position = match.end()
        if depth != 0:
            raise ValueError('bitwise67 source parentheses are incomplete')


def compile_program(source, legacy):
    """Explicit opt-in compilation only; never selects itself from old syntax."""
    from .parser import ParseError, split_statements
    from .plan import Plan, Ticket
    try:
        statements = split_statements(source)
        source_guard(statements)
        plan = legacy(source)
        if plan.blocked:
            return plan
        if len(plan.steps) != 1 or plan.steps[0].kind != 'data' or plan.steps[0].name != '_null_':
            raise ValueError('bitwise67 requires one scalar DATA_NULL source step')
        step = plan.steps[0]
        if not step.operations or step.operations[-1].kind != 'put_all':
            raise ValueError('bitwise67 requires one final PUT_ALL')
        step.kind = KIND
        step.operations[-1].kind = OPERATION
        step.operations[-1].args = {'profile': PROFILE}
        names = list(dict.fromkeys(op.args['name'] for op in step.operations[:-1] if op.kind == 'assign'))
        step.display_names = {name: step.display_names.get(name, name) for name in names}
        validate_step(asdict(step), plan.version)
        plan.matched = [entry for entry in plan.matched if entry[:2] != ('put-all', 'DS-025')]
        plan.matched.append(('bitwise-output', 'DS-070', step.operations[-1].line))
        return plan
    except (ValueError, TypeError, KeyError, IndexError, RecursionError, ParseError) as error:
        return Plan(tickets=[Ticket(getattr(error, 'line', 1), 'bitwise-put-all-67-v1', 'bitwise-output', str(error))])
