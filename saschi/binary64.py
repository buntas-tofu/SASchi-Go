"""DS-049..053 opt-in scalar binary64 values, selection and numeric DATA rows.

Profiles use explicit declaration operations. The original marker remains
catalog-free; the row marker admits separately proved SET/projection composition.
Earlier plans keep their exact-division/product helpers and integer-only list
output. Decimal output is a logical policy, not a SAS BEST12/DECIMALCONV claim.
"""
from __future__ import annotations

from fractions import Fraction
from copy import deepcopy
import math
import re
import sys

from sas_semantics import sas_counted_capture, sas_counted_control, sas_do_counted, sas_int
from .projection import _validate_step as validate_projection_context
from .values import descriptor, column_type


PROFILE = 'binary64-v1'
ROWS_PROFILE = 'binary64-rows-v1'
FUNCTIONS = frozenset({'constant', 'sin', 'cos', 'tan', 'arsin', 'arcos', 'atan'})
CALLS = FUNCTIONS | {'int'}
LIMIT = 2147483647
MAX_DEPTH = 32
MAX_NODES = 128
NAME = re.compile(r'[a-z_][a-z0-9_]{0,31}\Z', re.ASCII)
RESERVED = {'_n_', '_error_', '_all_', '_numeric_', '_character_', '_temporary_',
            '_infile_', '_file_', '_ods_', '_page_', '_blankpage_'}
COMPARISONS = {'=', 'eq', '^=', '~=', '<>', 'ne', '<', 'lt', '>', 'gt', '<=', 'le', '>=', 'ge'}


def ordinary(name):
    return isinstance(name, str) and NAME.fullmatch(name) is not None and name not in RESERVED


def numeric(value):
    """A finite bounded binary64 normal/zero, or ordinary missing, without coercion."""
    if value is None:
        return None
    if type(value) not in (int, float):
        raise ValueError('binary64 profile requires ordinary numeric values without coercion')
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError('binary64 profile requires finite binary64 values') from exc
    if not math.isfinite(value) or abs(value) > LIMIT:
        raise ValueError('binary64 profile exceeds the finite magnitude bound')
    if value and abs(value) < sys.float_info.min:
        raise ValueError('binary64 profile subnormals require separate evidence')
    return 0.0 if value == 0 else value


def arithmetic(op, left, right):
    """Round each reached operation to binary64, checking both operands first."""
    if op not in ('+', '-', '*', '/', '**'):
        raise ValueError('binary64 profile has an unsupported arithmetic operator')
    left, right = numeric(left), numeric(right)
    if op == '/' and right == 0:
        raise ValueError('binary64 profile zero divisor requires error-state review')
    if op == '**' and right is not None:
        if right != int(right) or not 0 <= right <= 32:
            raise ValueError('binary64 power requires an integer exponent in0..32')
        if left == 0 and right == 0:
            raise ValueError('binary64 power zero to zero requires separate evidence')
    if left is None or right is None:
        return None
    try:
        if op == '+':
            result = left + right
        elif op == '-':
            result = left - right
        elif op == '*':
            result = left * right
        elif op == '/':
            result = left / right
        else:
            result = math.pow(left, right)
    except (OverflowError, ValueError, ZeroDivisionError) as exc:
        raise ValueError('binary64 arithmetic requires a bounded finite result') from exc
    if result == 0 and left != 0 and (op == '*' and right != 0 or op in ('/', '**')):
        raise ValueError('binary64 nonzero underflow requires separate evidence')
    return numeric(result)


def apply(name, values):
    """The scoped PI/trigonometric functions and the unchanged conservative INT."""
    if not isinstance(name, str) or name not in CALLS or not isinstance(values, (list, tuple)) or len(values) != 1:
        raise ValueError('binary64 call requires one argument and a supported function')
    value = values[0]
    if name == 'constant':
        if not isinstance(value, str) or value.lower() != 'pi':
            raise ValueError("binary64 CONSTANT supports the literal name 'pi' only")
        return math.pi
    if name == 'int':
        return numeric(sas_int(value))
    value = numeric(value)
    if value is None:
        return None
    if name in ('sin', 'cos') and not -math.pi <= value <= math.pi:
        raise ValueError('binary64 SIN/COS require radians in[-pi,pi]')
    if name == 'tan' and not -math.pi / 4 <= value <= math.pi / 4:
        raise ValueError('binary64 TAN requires radians in[-pi/4,pi/4]')
    if name in ('arsin', 'arcos') and not -1 <= value <= 1:
        raise ValueError('binary64 inverse trigonometric domain is[-1,1]')
    function = {'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
                'arsin': math.asin, 'arcos': math.acos, 'atan': math.atan}[name]
    return numeric(function(value))


def evaluate(expr, row):
    """Evaluate an already validated scalar expression, with no array/control widening."""
    kind = expr['kind']
    if kind in ('number', 'missing'):
        return numeric(expr['value'])
    if kind in ('variable', 'automatic'):
        return numeric(row.get(expr['value']))
    if kind == 'arithmetic':
        return arithmetic(expr['op'], evaluate(expr['left'], row), evaluate(expr['right'], row))
    if kind == 'call':
        values = ([expr['args'][0]['value']] if expr['name'] == 'constant'
                  else [evaluate(arg, row) for arg in expr['args']])
        return apply(expr['name'], values)
    raise ValueError('binary64 expression requires a validated numeric scalar')


def render_numeric_list(values):
    """Bounded fixed-decimal logical records, with legacy integer fields preserved."""
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError('binary64 numeric PUT requires a nonempty value list')
    fields = []
    for value in values:
        if value is None:
            text = '.'
        else:
            if type(value) not in (int, float):
                raise ValueError('binary64 numeric PUT requires ordinary numeric values')
            try:
                value = float(value)
            except (OverflowError, ValueError) as exc:
                raise ValueError('binary64 numeric PUT requires finite binary64 values') from exc
            if not math.isfinite(value):
                raise ValueError('binary64 numeric PUT requires finite binary64 values')
            if value.is_integer():
                if abs(value) > 99999999999:
                    raise ValueError('binary64 integer PUT exceeds the signed BEST12 subset')
                text = str(int(value))
            else:
                if not 1e-4 <= abs(value) < 1e9:
                    raise ValueError('binary64 fractional PUT requires magnitude in[1e-4,1e9)')
                decimals = 12 - int(value < 0) - len(str(int(abs(value)))) - 1
                scale = 10 ** decimals
                exact = Fraction.from_float(abs(value))
                scaled = exact * scale
                floor = scaled.numerator // scaled.denominator
                midpoint = Fraction(2 * floor + 1, 2 * scale)
                if abs(exact - midpoint) <= 16 * Fraction.from_float(math.ulp(value)):
                    raise ValueError('binary64 decimal midpoint requires rounding-policy review')
                text = format(value, f'.{decimals}f')
                if len(text) > 12:
                    raise ValueError('binary64 decimal carry exceeds the12-column field')
                text = text.rstrip('0').rstrip('.')
                if text in ('-0', ''):
                    text = '0'
                if len(text) > 12:
                    raise ValueError('binary64 decimal carry exceeds the12-column field')
        fields.append(text + ' ')
    record = ''.join(fields)
    if len(record) > 64:
        raise ValueError('binary64 numeric PUT exceeds64 logical columns')
    return record


def _structure(value):
    """Bound and cycle-check untrusted containers before recursive validators."""
    active, count, markers = set(), 0, 0
    pending = [(value, 0, False)]
    while pending:
        node, depth, exiting = pending.pop()
        if not isinstance(node, (dict, list, tuple)):
            if type(node) not in (str, int, float, bool, type(None)):
                raise ValueError('binary64 plan requires ordinary serialized values')
            continue
        ident = id(node)
        if exiting:
            active.remove(ident)
            continue
        if ident in active:
            raise ValueError('binary64 plan has a cyclic container')
        count += 1
        if depth > 256 or count > 8192:
            raise ValueError('binary64 plan exceeds bounded structural validation')
        if isinstance(node, dict) and any(not isinstance(key, str) for key in node):
            raise ValueError('binary64 plan mapping keys must be strings')
        if isinstance(node, dict) and node.get('kind') == 'numeric_profile':
            markers += 1
        active.add(ident)
        pending.append((node, depth, True))
        pending.extend((child, depth + 1, False)
                       for child in (node.values() if isinstance(node, dict) else node))
    return markers


def _number_descriptor(name, schema):
    if schema is None:
        return
    if not isinstance(schema, dict):
        raise ValueError('binary64 schema requires a column mapping')
    spec = schema.get(name, 'number')
    if (spec if isinstance(spec, str) else spec.get('type') if isinstance(spec, dict) else None) != 'number':
        raise ValueError('binary64 expressions cannot coerce character descriptors')


def validate_input_table(table):
    """Eager selected-input numeric validation, with no mutation of its catalog."""
    if (not isinstance(table, dict) or not isinstance(table.get('schema'), dict)
            or not isinstance(table.get('rows'), list)):
        raise ValueError('binary64 SET requires a normalized numeric table')
    schema = table['schema']
    for name, spec in schema.items():
        if not ordinary(name) or column_type(descriptor(spec)) != 'number':
            raise ValueError('binary64 SET requires ordinary numeric input descriptors')
    normalized = deepcopy(table)
    for row in normalized['rows']:
        if not isinstance(row, dict) or set(row) != set(schema):
            raise ValueError('binary64 SET row must match its selected descriptor')
        for name, value in row.items():
            row[name] = numeric(value)
    return normalized


def validate_step(step, version=2, schema=None):
    """Validate the explicit profile, including literals in every inactive branch.

    Return False for an unmarked step with no new syntax. A new function/power
    without its declaration, a declaration without a trigger, or any forged
    nested/duplicate declaration refuses independently of source compilation.
    """
    from .numeric_pipeline import validate_step as validate_pipeline
    pipeline = validate_pipeline(step, version, schema)
    if pipeline is not None:
        return True
    if not isinstance(step, dict) or not isinstance(step.get('operations'), list):
        raise ValueError('binary64 validation requires a DATA-step mapping')
    markers, trigger, seen = [], False, set()
    pending = [step]
    while pending:
        node = pending.pop()
        if isinstance(node, (dict, list, tuple)):
            if id(node) in seen:
                continue
            seen.add(id(node))
        if isinstance(node, dict):
            if node.get('kind') == 'numeric_profile':
                markers.append(node)
            if (node.get('kind') == 'arithmetic' and node.get('op') == '**'
                    or node.get('kind') == 'call' and isinstance(node.get('name'), str)
                    and node.get('name') in FUNCTIONS):
                trigger = True
            pending.extend(node.values())
        elif isinstance(node, (list, tuple)):
            pending.extend(node)
    if not markers:
        if trigger:
            raise ValueError('binary64 syntax requires its explicit numeric_profile declaration')
        return False
    if _structure(step) != 1:
        raise ValueError('binary64 plan requires exactly one declaration occurrence')
    ops = step['operations']
    marker = markers[0]
    rows_profile = marker.get('args') == {'name': ROWS_PROFILE}
    if (version != 2 or len(markers) != 1 or not ops or marker is not ops[0]
            or set(marker) != {'kind', 'line', 'args'} or type(marker['line']) is not int
            or marker['line'] < 1 or marker['args'] not in ({'name': PROFILE}, {'name': ROWS_PROFILE})
            or not trigger):
        raise ValueError('binary64 requires one first top-level version2 declaration and new syntax')
    expected = {'kind', 'name', 'line', 'inputs', 'by', 'operations', 'nodupkey',
                'where', 'retained', 'lengths', 'display_names'}
    if (set(step) != expected or step['kind'] != 'data'
            or not (ordinary(step['name']) or step['name'] == '_null_')
            or type(step['line']) is not int or step['line'] < 1
            or not isinstance(step['inputs'], list) or len(step['inputs']) > (1 if rows_profile else 0)
            or any(not ordinary(name) for name in step['inputs'])
            or step['by'] != [] or step['where'] is not None
            or step['lengths'] != {} or step['nodupkey'] is not False):
        raise ValueError('binary64 row profile requires at most one scalar numeric SET without BY/WHERE'
                         if rows_profile else 'binary64 profile requires catalog-free scalar numeric DATA')
    if rows_profile and marker['line'] != step['line']:
        raise ValueError('binary64 row declaration must share its DATA source line')
    display = step['display_names']
    if (not isinstance(display, dict) or any(not (ordinary(name) or name == '_n_') or not isinstance(shown, str)
            or shown.lower() != name for name, shown in display.items())):
        raise ValueError('binary64 display metadata requires matching ordinary variable names')
    nodes, semantic_trigger = 0, False

    def expression(expr, depth=1, *, control=False):
        nonlocal nodes, semantic_trigger
        if not isinstance(expr, dict) or depth > MAX_DEPTH:
            raise ValueError('binary64 expressions require mappings within32 levels')
        kind = expr.get('kind')
        if kind in ('number', 'missing', 'variable', 'automatic'):
            if set(expr) != {'kind', 'value'}:
                raise ValueError('binary64 scalar operand has unexpected fields')
            value = expr['value']
            if kind in ('number', 'missing'):
                if kind == 'number' and value is None or kind == 'missing' and value is not None:
                    raise ValueError('binary64 numeric/missing literal has an invalid encoding')
                return True, (sas_counted_control(value) if control else numeric(value))
            if kind == 'variable' and not ordinary(value) or kind == 'automatic' and value != '_n_':
                raise ValueError('binary64 requires ordinary numeric variables or _N_')
            _number_descriptor(value, schema)
            return False, None
        if kind == 'arithmetic':
            nodes += 1
            operators = ('+', '-') if control else ('+', '-', '*', '/', '**')
            if (set(expr) != {'kind', 'op', 'left', 'right'} or expr.get('op') not in operators):
                raise ValueError('binary64 arithmetic has an unsupported shape/operator')
            semantic_trigger |= expr['op'] == '**'
            a, left = expression(expr['left'], depth + 1, control=control)
            b, right = expression(expr['right'], depth + 1, control=control)
            if not control:
                if expr['op'] == '/' and b and right == 0:
                    raise ValueError('binary64 literal divisor is zero')
                if expr['op'] == '**' and b and right is not None and (right != int(right) or not 0 <= right <= 32):
                    raise ValueError('binary64 power exponent requires an integer in0..32')
            if not (a and b):
                return False, None
            if control:
                return True, sas_counted_control(left + right if expr['op'] == '+' else left - right)
            return True, arithmetic(expr['op'], left, right)
        if kind != 'call' or control:
            raise ValueError('binary64 expressions require gated scalar numeric nodes')
        nodes += 1
        if (set(expr) != {'kind', 'name', 'args'} or not isinstance(expr.get('name'), str)
                or expr['name'] not in CALLS
                or not isinstance(expr.get('args'), list) or len(expr['args']) != 1):
            raise ValueError('binary64 call has an unsupported name/arity/shape')
        semantic_trigger |= expr['name'] in FUNCTIONS
        if expr['name'] == 'constant':
            arg = expr['args'][0]
            if (not isinstance(arg, dict) or set(arg) != {'kind', 'value'}
                    or arg.get('kind') != 'character' or depth + 1 > MAX_DEPTH):
                raise ValueError("binary64 CONSTANT requires the literal character name 'pi'")
            return True, apply('constant', [arg['value']])
        known, value = expression(expr['args'][0], depth + 1)
        return (True, apply(expr['name'], [value])) if known else (False, None)

    def predicate(test):
        if (not isinstance(test, dict) or not isinstance(test.get('op'), str)
                or test['op'] not in COMPARISONS | {'truth'}
                or set(test) != ({'left', 'op'} if test.get('op') == 'truth' else {'left', 'op', 'right'})):
            raise ValueError('binary64 predicates require supported numeric comparisons')
        expression(test['left'])
        if test['op'] != 'truth':
            expression(test['right'])

    def operation(op, depth=0, active=()):
        if (not isinstance(op, dict) or set(op) != {'kind', 'line', 'args'}
                or type(op.get('line')) is not int or op['line'] < 1
                or not isinstance(op.get('args'), dict) or depth > 32):
            raise ValueError('binary64 operation has an invalid shape or nesting depth')
        kind, args = op['kind'], op['args']
        if kind in ('assign', 'sum_statement'):
            if set(args) != {'name', 'value'} or not ordinary(args.get('name')) or args['name'] in active:
                raise ValueError('binary64 assignment requires an ordinary target outside active controls')
            _number_descriptor(args['name'], schema)
            expression(args['value'])
        elif kind == 'declare':
            if (set(args) != {'name', 'spec'} or not ordinary(args.get('name'))
                    or args['name'] in active or args['spec'] != 'number'):
                raise ValueError('binary64 supports ordinary numeric declarations only')
        elif kind == 'do_counted':
            bounded = args.get('profile') == 'bounded'
            if (set(args) != {'index', 'start', 'stop', 'by', 'body'} | ({'profile'} if bounded else set())
                    or not ordinary(args.get('index')) or args['index'] in active
                    or not isinstance(args.get('body'), list) or len(active) >= 8):
                raise ValueError('binary64 counted DO requires the existing bounded integer controls')
            if bounded:
                constants = [expression(args[key], control=True) for key in ('start', 'stop', 'by')]
                if constants[2] == (True, 0):
                    raise ValueError('binary64 counted DO BY must be nonzero')
                if all(known for known, _ in constants):
                    sas_counted_capture(*(value for _, value in constants), 0)
            else:
                sas_do_counted(args['start'], args['stop'], args['by'])
            for child in args['body']:
                operation(child, depth + 1, active + (args['index'],))
        elif kind == 'if':
            if set(args) not in ({'condition', 'operation'}, {'condition', 'operation', 'otherwise'}):
                raise ValueError('binary64 IF has unexpected fields')
            predicate(args['condition'])
            operation(args['operation'], depth + 1, active)
            if 'otherwise' in args:
                operation(args['otherwise'], depth + 1, active)
        elif kind == 'subset':
            if set(args) != {'condition'} or active:
                raise ValueError('binary64 subsetting IF requires one top-level predicate')
            predicate(args['condition'])
        elif kind == 'put_numeric_list':
            names = args.get('names')
            if (set(args) not in ({'names'}, {'names', 'discover'}) or not isinstance(names, list)
                    or not names or any(not ordinary(name) for name in names)):
                raise ValueError('binary64 numeric PUT requires ordinary numeric names')
            for name in names:
                _number_descriptor(name, schema)
            if 'discover' in args:
                found = args['discover']
                if (not isinstance(found, list) or not found or any(not ordinary(name) for name in found)
                        or len(found) != len(set(found)) or found != [name for name in dict.fromkeys(names) if name in found]):
                    raise ValueError('binary64 PUT discovery requires an ordered unique subset')
            render_numeric_list([None] * len(names))
        elif kind == 'output':
            if set(args) != {'target'} or args['target'] not in (None, step.get('name')):
                raise ValueError('binary64 OUTPUT must target the declared DATA destination')
        elif kind == 'projection' and rows_profile:
            if depth:
                raise ValueError('binary64 projection must be a top-level DATA declaration')
        elif kind == 'read' and rows_profile:
            if depth or active or set(args) != {'datasets'} or args['datasets'] != step['inputs'] or len(step['inputs']) != 1:
                raise ValueError('binary64 SET requires one matching top-level driving source')
        else:
            raise ValueError('binary64 operation requires a separately proved scalar numeric composition')

    retained = step.get('retained', {})
    if not isinstance(retained, dict):
        raise ValueError('binary64 RETAIN requires a mapping')
    for name, initial in retained.items():
        if not ordinary(name) or not isinstance(initial, dict) or initial.get('kind') not in ('number', 'missing'):
            raise ValueError('binary64 RETAIN requires ordinary numeric literal initialization')
        expression(initial)
    for op in ops[1:]:
        operation(op)
    if rows_profile:
        projections = [op for op in ops[1:] if op['kind'] == 'projection']
        reads = [op for op in ops[1:] if op['kind'] == 'read']
        if not projections and not reads:
            raise ValueError('binary64 row declaration requires projection or a driving SET')
        if len(reads) != len(step['inputs']):
            raise ValueError('binary64 SET requires exactly one read for its declared input')
        if reads:
            position = next(i for i, root in enumerate(ops) if root is reads[0])
            if any(root['kind'] not in ('declare', 'projection') for root in ops[1:position]):
                raise ValueError('binary64 driving SET must precede executable DATA actions')
        validate_projection_context(step, version, prefix=1)
    if not semantic_trigger:
        raise ValueError('binary64 declaration requires new syntax in executable expressions')
    if nodes > MAX_NODES:
        raise ValueError('binary64 expressions exceed the128-node step policy')
    return True
