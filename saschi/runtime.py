"""Execute bounded DATA events with typed catalogs; version 1 plans remain readable."""
from __future__ import annotations
import math
import re
from collections import Counter
from copy import deepcopy
from sas_semantics import sas_round, sas_merge_by, sas_put_literals, sas_put_character_list, sas_put_numeric_list, sas_put_all, sas_do_counted, sas_concat, SasNumericLagQueue
from .functions import apply as apply_function, assign_spec, character_width, validate_reverse_calls, validate_string_expressions, expression_nodes, validate_substr_calls, substr_context_errors, validate_bitwise_calls, SAS_BITWISE_ARITY, LAG_FUNCTIONS, validate_lag_calls
from .operations import walk_operations as operations
from .values import normalize_catalog, column_type, coerce, missing, order
from .functions import validate_calendar_calls, validate_sum_expression, validate_numeric_composition
from sas_semantics import sas_sum_statement, sas_do_until, sas_do_while, sas_divide
from sas_semantics import sas_numeric_array_value, sas_numeric_array_index, sas_do_over
from .arrays import validate_step as validate_array_step, contains_array, value as array_value
from .counted import validate_step as validate_counted_step, evaluate_control
from sas_semantics import sas_counted_capture
from sas_semantics import sas_put_mixed_numeric
from .put_mixed import validate_items as validate_mixed_put_items


def evaluate(expr, row, schema=None, arrays=None, current=None):
    """Value of one wired function call with optional static descriptors."""
    values = [argument(arg, row, schema, arrays, current) for arg in expr['args']]
    if expr['name'] == 'reverse':
        width = character_width(expr['args'][0], schema)
        if isinstance(values[0], str):
            if len(values[0]) > width:
                raise ValueError('REVERSE argument exceeds its declared width')
            values[0] = values[0].ljust(width)
    return apply_function(expr['name'], values)


def argument(expr, row, schema=None, arrays=None, current=None):
    """One call argument: a format token passes through, everything else is a value."""
    return expr if expr['kind'] == 'format' else number(expr, row, schema, arrays, current)


def number(expr, row, schema=None, arrays=None, current=None):
    if arrays and contains_array(expr):
        return array_value(expr, row, arrays, current)
    kind = expr['kind']
    if kind in ('variable', 'automatic'):
        return row.get(expr['value'])
    if kind == 'call':
        return evaluate(expr, row, schema, arrays, current)
    if kind == 'concat':
        values = []
        for arg in expr['args']:
            value = number(arg, row, schema, arrays, current)
            width = character_width(arg, schema)
            if not isinstance(value, str) or width is None:
                raise ValueError('character concatenation requires character operands')
            values.append(value.ljust(width)[:width])
        return sas_concat(values)
    if kind == 'arithmetic':
        left, right = number(expr['left'], row, schema, arrays, current), number(expr['right'], row, schema, arrays, current)
        if expr['op'] == '/':
            return sas_divide(left, right)
        if isinstance(left, str) or isinstance(right, str):
            raise ValueError('implicit character to numeric conversion is unsupported')
        if missing(left) or missing(right):
            return None
        value = left + right if expr['op'] == '+' else left - right
        return value if math.isfinite(value) else None
    return expr['value']


def round_value(value, unit):
    if isinstance(value, str) or isinstance(unit, str):
        raise ValueError('ROUND requires numeric operands')
    if missing(value) or missing(unit) or unit <= 0:
        return None
    try:
        result = sas_round(value, unit)
        return result if math.isfinite(result) else None
    except (OverflowError, ValueError):
        return None


def condition(expr, row, schema=None, arrays=None, current=None):
    left = number(expr['left'], row, schema, arrays, current)
    op = expr['op']
    if op == 'truth':
        if isinstance(left, str):
            raise ValueError('numeric truth predicate required')
        return not missing(left) and left != 0
    right = number(expr['right'], row, schema, arrays, current)
    if isinstance(left, str) != isinstance(right, str):
        raise ValueError('implicit comparison conversion is unsupported')
    if isinstance(left, str):
        width = max(len(left), len(right))
        left, right = left.ljust(width), right.ljust(width)
    a, b = order(left), order(right)
    if op in ('=', 'eq'): return a == b
    if op in ('^=', '~=', '<>', 'ne'): return a != b
    if op in ('<', 'lt'): return a < b
    if op in ('>', 'gt'): return a > b
    if op in ('<=', 'le'): return a <= b
    if op in ('>=', 'ge'): return a >= b
    raise ValueError('unsupported comparison operator')


def expressions(value):
    if isinstance(value, dict):
        if value.get('kind') in ('variable', 'automatic'):
            yield value
        for child in value.values():
            yield from expressions(child)
    elif isinstance(value, list):
        for child in value:
            yield from expressions(child)


def put_all_value(expr, row):
    """Error-free scalar expressions for the DS-025 _ERROR_=0 contract."""
    if expr['kind'] == 'call':
        name = expr['name']
        if name not in ('length', 'lengthn', 'lengthc', 'substr') and name not in SAS_BITWISE_ARITY:
            raise ValueError('PUT _ALL_: function requires error-flag review')
        values = [put_all_value(arg, row) for arg in expr['args']]
        if name == 'substr':
            text, position, width = values
            if (not isinstance(text, str) or any(isinstance(v, bool) or not isinstance(v, (int, float))
                    or not math.isfinite(v) or v != int(v) or v < 1 for v in (position, width))
                    or position + width - 1 > len(text)):
                raise ValueError('PUT _ALL_: SUBSTR bounds/type require error-flag review')
        return apply_function(name, values)
    if expr['kind'] not in ('number', 'missing', 'tagged_missing', 'character', 'variable', 'automatic'):
        raise ValueError('PUT _ALL_: expression requires error-flag review')
    if expr['kind'] == 'automatic' and expr['value'] != '_n_':
        raise ValueError('PUT _ALL_: only the scalar _N_ automatic reference is gated')
    value = number(expr, row)
    if expr['kind'] == 'character' and value == '':
        raise ValueError('PUT _ALL_: empty character literals require source-blank review')
    if isinstance(value, str) and any(not 32 <= ord(c) <= 126 for c in value):
        raise ValueError('PUT _ALL_: printable ASCII expressions required')
    return value


def run_plan(plan, catalog=None, *, allow_partial=False):
    if plan['version'] not in (1, 2):
        raise ValueError('unsupported plan version')
    if plan['tickets'] and not allow_partial:
        raise RuntimeError('saschi: blocked translation. Nothing from this program was executed.')
    tables, logs = normalize_catalog({} if catalog is None else catalog), []
    for step in plan['steps']:
        inputs, keys, ops = step['inputs'], step['by'], step['operations']
        # Reject malformed mixed-output plans before other expression walkers or input work.
        for op in operations(ops):
            if op['kind'] == 'put_mixed_numeric':
                args = op['args']
                if (plan['version'] != 2 or step['kind'] != 'data' or not isinstance(args, dict)
                        or set(args) != {'items'} or type(op.get('line')) is not int or op['line'] < 1):
                    raise ValueError('PUT mixed numeric requires version2 DATA, items only and a positive source line')
                validate_mixed_put_items(args['items'])
        bounded_counted = validate_counted_step(step)
        if bounded_counted and plan['version'] != 2:
            raise ValueError('bounded counted loops require a version2 plan')
        arrays = validate_array_step(step)
        if arrays and plan['version'] != 2:
            raise ValueError('numeric arrays require a version2 DATA plan')
        array_members = {n for a in arrays.values() for n in a['names']}
        nodes = [node for node, _ in expression_nodes(step)]
        if any(node.get('kind') == 'arithmetic' and node.get('op') == '/'
               or node.get('kind') == 'call' and node.get('name') == 'int' for node in nodes):
            if sum(node.get('kind') in ('arithmetic', 'call') for node in nodes) > 128:
                raise ValueError('numeric composition exceeds the128-node step policy')
        lag_queues = {}  # Per-step/run state, keyed by structural execution position.
        lag_present = any(node.get('kind') == 'call' and node.get('name') in LAG_FUNCTIONS
                          for node, _ in expression_nodes(step))
        if lag_present and step['kind'] not in ('data', 'merge'):
            raise ValueError('LAG/DIF requires a DATA-step execution scope')
        flat = list(operations(ops))
        if (step['name'] == '_null_' and any(op['kind'] in ('do_counted', 'do_until', 'do_while', 'do_over') for op in flat)
                and any(op['kind'] == 'output' for op in flat)):
            label = 'DO OVER' if any(op['kind'] == 'do_over' for op in flat) else 'DO UNTIL' if any(op['kind'] == 'do_until' for op in flat) else 'DO WHILE' if any(op['kind'] == 'do_while' for op in flat) else 'counted DO'
            raise ValueError('explicit OUTPUT in DATA _NULL_ ' + label + ' steps is deferred')
        put_all = any(op['kind'] == 'put_all' for op in flat)
        if put_all and lag_present:
            raise ValueError('LAG/DIF with PUT _ALL_ requires error-state review')
        if put_all and (step['kind'] != 'data' or inputs or keys or step.get('retained') or step.get('where') or
                        (step['name'] == '_null_' and any(op['kind'] == 'output' for op in flat)) or
                        any(op['kind'] not in ('declare', 'assign', 'put_all', 'output') for op in flat)):
            raise ValueError('PUT _ALL_: only scalar declarations, safe assignments, and named-destination OUTPUT are gated')
        lookups = [op['args']['dataset'] for op in flat if op['kind'] == 'lookup']
        for name in inputs + lookups:
            if name not in tables:
                raise ValueError(f'input dataset is missing: {name}')
        key = lambda row: tuple(order(row[k]) for k in keys)
        if step['kind'] == 'sort':
            table = deepcopy(tables[inputs[0]])
            if not set(keys) <= set(table['schema']):
                raise ValueError('BY column missing from schema')
            rows = sorted(table['rows'], key=key)
            if step['nodupkey']:
                rows = [r for i, r in enumerate(rows) if i == 0 or key(r) != key(rows[i-1])]
            table['rows'] = rows
            tables[step['name']] = table
            continue
        schema = {n: {'type': 'character', 'length': w} for n, w in step.get('lengths', {}).items()}
        metadata = {k: deepcopy(v) for k, v in tables[inputs[0]].items() if k not in ('schema', 'rows')} if inputs else {}
        encoding = metadata.get('encoding', 'utf-8')
        for name in lookups + inputs:
            if tables[name].get('encoding', 'utf-8') != encoding:
                raise ValueError('mixed source encodings require explicit transcoding')
            for col, spec in tables[name]['schema'].items():
                if col in schema and column_type(schema[col]) != column_type(spec):
                    raise ValueError('incompatible input column types')
                schema.setdefault(col, deepcopy(spec))
                if isinstance(spec, dict) and spec.get('format'):
                    if not isinstance(schema[col], dict):
                        schema[col] = {'type': schema[col]}
                    if not schema[col].get('format'):
                        schema[col]['format'] = spec['format']
        if not set(keys) <= set(schema):
            raise ValueError('BY column missing from schema')
        if step['kind'] == 'merge':
            # The existing MERGE witness covers ordinary numeric rows only.
            if lookups or step.get('where') or step.get('retained') or any(column_type(v) != 'number' for v in schema.values()):
                raise ValueError('MERGE remains restricted to numeric, unfiltered inputs')
            sides = [tables[n]['rows'] for n in inputs]
            if any(isinstance(v, dict) for side in sides for row in side for v in row.values()):
                raise ValueError('tagged missing MERGE is outside this slice')
            for side in sides:
                if any(key(a) > key(b) for a, b in zip(side, side[1:])):
                    raise ValueError('MERGE requires ascending BY-sorted inputs')
            counts = [Counter(key(row) for row in side) for side in sides]
            if any(n > 1 and counts[1][k] > 1 for k, n in counts[0].items()):
                raise ValueError('DS-003: many-to-many MERGE requires human review')
            rows, _, _ = sas_merge_by(*sides, keys)
            rows = [{n: r.get(n) for n in schema} for r in rows]
        else:
            rows = deepcopy(tables[inputs[0]]['rows']) if inputs else [{}]
        where = step.get('where')
        if where:
            if not inputs or step['kind'] != 'data':
                raise ValueError('WHERE requires one driving SET')
            # WHERE sees driving input descriptors before PDV LENGTH changes.
            where_schema = tables[inputs[0]]['schema']
            validate_string_expressions(where, where_schema)
            if any(e['kind'] == 'automatic' or e['value'] not in tables[inputs[0]]['schema'] for e in expressions(where)):
                raise ValueError('WHERE can reference only driving input columns')
            validate_reverse_calls(where, where_schema)
            context_error = next(substr_context_errors(where), None)
            if context_error:
                raise ValueError(context_error)
            validate_substr_calls(where, where_schema)
            validate_bitwise_calls(where, where_schema)
            validate_calendar_calls(where, where_schema)
            validate_numeric_composition(where, where_schema)
            validate_lag_calls(where, where_schema)
            rows = [r for r in rows if condition(where, r, where_schema)]
        if keys and any(key(a) > key(b) for a, b in zip(rows, rows[1:])):
            raise ValueError('SET BY requires ascending sorted rows after WHERE')
        retained = deepcopy(step.get('retained', {}))
        for op in flat:
            if op['kind'] == 'sum_statement':
                args = op['args']
                name = args.get('name')
                if (set(args) != {'name', 'value'} or not isinstance(name, str)
                        or not re.fullmatch(r'[a-z_][a-z0-9_]{0,31}', name)
                        or name in ('_n_', '_error_', '_all_', '_numeric_', '_character_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_')
                        or step['kind'] != 'data' or name in keys):
                    raise ValueError('sum statement requires an ordinary DATA numeric target outside BY keys')
                retained.setdefault(name, {'kind': 'number', 'value': 0.0})
                initial = retained[name]
                if not isinstance(initial, dict) or initial.get('kind') not in ('number', 'missing'):
                    raise ValueError('sum statement RETAIN initializer must be numeric or ordinary missing')
                validate_sum_expression(initial, {})
        legacy_schema = schema
        schema = {} if plan['version'] == 2 else schema

        def add_input(name):
            for col, spec in tables[name]['schema'].items():
                if col in schema and column_type(schema[col]) != column_type(spec):
                    raise ValueError('incompatible input column types')
                schema.setdefault(col, deepcopy(spec))
                # LENGTH sets width without removing an inherited format.
                if isinstance(spec, dict) and spec.get('format'):
                    if not isinstance(schema[col], dict):
                        schema[col] = {'type': schema[col]}
                    if not schema[col].get('format'):
                        schema[col]['format'] = spec['format']

        def add_reference(expr):
            if expr['kind'] == 'automatic':
                if expr['value'] != '_n_' and expr['value'].split('.', 1)[1] not in keys:
                    raise ValueError('FIRST/LAST requires the corresponding BY key')
            else:
                schema.setdefault(expr['value'], 'number')

        for op in flat:
            args, kind = op['args'], op['kind']
            payloads = [(args.get('value'), 'assignment')] if kind == 'assign' else [
                (value, 'other') for key, value in args.items() if key not in ('body', 'operation', 'otherwise')]
            for payload, context in payloads:
                context_error = next(substr_context_errors(payload, context), None)
                if context_error:
                    raise ValueError(context_error)
                validate_substr_calls(payload, schema)
                validate_bitwise_calls(payload, schema)
                validate_lag_calls(payload, schema, direct=context == 'assignment')
            if kind == 'declare':
                name, spec = args['name'], args['spec']
                if name in schema and column_type(schema[name]) != column_type(spec):
                    raise ValueError('incompatible declaration types')
                schema.setdefault(name, deepcopy(spec))
            elif kind == 'array_declare':
                for name in args['names']:
                    schema.setdefault(name, deepcopy(legacy_schema.get(name, 'number')))
            elif kind in ('array_set', 'array_current_set'):
                for expr in expressions(args):
                    add_reference(expr)
            elif kind == 'read':
                for name in args['datasets']:
                    add_input(name)
            elif kind == 'lookup':
                add_input(args['dataset'])
            elif kind in ('assign', 'round', 'sum_statement'):
                expr = args['value']
                validate_string_expressions(expr, schema, direct_catx=kind == 'assign')
                if kind == 'assign' and expr['kind'] == 'character':
                    spec = {'type': 'character', 'length': max(1, len(expr['value'].encode(encoding)))}
                elif kind == 'assign' and expr['kind'] == 'variable':
                    # An assigned copy gets type/width, not the source label/format.
                    origin = schema.get(expr['value'], 'number')
                    spec = {'type': 'character', 'length': origin['length']} if column_type(origin) == 'character' else 'number'
                else:
                    spec = (assign_spec(expr, schema) if kind == 'assign' else None) or 'number'
                if args['name'] in schema and column_type(schema[args['name']]) != column_type(spec):
                    raise ValueError('implicit assignment type conversion is unsupported')
                schema.setdefault(args['name'], spec)
                for value in expressions(args):
                    add_reference(value)
            elif kind == 'do_over':
                pass  # Independent array validation checks shape, binding and body.
            elif kind == 'do_counted':
                bounded = args.get('profile') == 'bounded'
                expected = {'index', 'start', 'stop', 'by', 'body'} | ({'profile'} if bounded else set())
                if set(args) != expected:
                    raise ValueError('counted DO has unexpected plan arguments')
                name = args['index']
                if (not isinstance(name, str) or not re.fullmatch(r'[a-z_][a-z0-9_]{0,31}', name)
                        or name in ('_n_', '_error_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_')
                        or step['kind'] != 'data'):
                    raise ValueError('counted DO requires a numeric DATA-step index')
                if not bounded:
                    sas_do_counted(args['start'], args['stop'], args['by'])
                else:
                    for key in ('start', 'stop', 'by'):
                        for value in expressions(args[key]):
                            add_reference(value)
                if name not in schema or column_type(schema[name]) != 'number':
                    raise ValueError('counted DO index requires a preceding numeric declaration')
                allowed = {'assign', 'array_set', 'round', 'sum_statement', 'if', 'put', 'put_literal', 'put_character_list', 'put_numeric_list', 'put_mixed_numeric', 'output'}
                if bounded:
                    allowed |= {'declare', 'do_counted'}
                for child in operations(args['body']):
                    if (child['kind'] not in allowed or
                            child['kind'] in ('assign', 'round', 'sum_statement') and child['args']['name'] == name):
                        raise ValueError('counted DO body operation is outside the bounded contract')
                    if child['kind'] == 'output' and step['name'] == '_null_':
                        raise ValueError('explicit OUTPUT in DATA _NULL_ counted DO is deferred')
            elif kind in ('do_until', 'do_while'):
                label = 'DO UNTIL' if kind == 'do_until' else 'DO WHILE'
                if (set(args) != {'condition', 'body'} or not isinstance(args['body'], list)
                        or step['kind'] != 'data'):
                    raise ValueError(label + ' requires condition/body only in a DATA step')
                test = args['condition']
                comparisons = {'=', 'eq', '^=', '~=', '<>', 'ne', '<', 'lt', '>', 'gt', '<=', 'le', '>=', 'ge'}
                if (not isinstance(test, dict) or test.get('op') not in comparisons | {'truth'} or
                        set(test) != ({'left', 'op'} if test.get('op') == 'truth' else {'left', 'op', 'right'})):
                    raise ValueError(label + ' requires a supported numeric predicate')
                allowed = {'assign', 'array_set', 'round', 'sum_statement', 'if', 'put', 'put_literal', 'put_character_list', 'put_numeric_list', 'output'}
                if any(child['kind'] not in allowed for child in operations(args['body'])):
                    raise ValueError(label + ' body requires single-level simple actions')
                if any(node.get('kind') == 'call' and node.get('name') in LAG_FUNCTIONS
                       for node, _ in expression_nodes(args)):
                    raise ValueError(label + ' queue scheduling requires review')
                for value in expressions(test):
                    add_reference(value)
            elif kind == 'put_literal':
                sas_put_literals(args['literals'])
            elif kind == 'put_all':
                if args:
                    raise ValueError('PUT _ALL_: unexpected plan arguments')
            elif kind == 'put_numeric_list':
                names = args.get('names')
                if (set(args) != {'names'} or not isinstance(names, list) or not names or
                        any(not isinstance(name, str) or not re.fullmatch(r'[a-z_][a-z0-9_]{0,31}', name)
                            or name in ('_n_', '_error_', '_all_', '_numeric_', '_character_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_')
                            for name in names)):
                    raise ValueError('PUT numeric list: nonempty normalized ordinary variable names required')
                if any(name not in schema for name in names):
                    raise ValueError('PUT numeric list: variables must be known before PUT')
            elif kind == 'put_mixed_numeric':
                try:
                    validate_mixed_put_items(args['items'], schema)
                except ValueError as error:
                    raise ValueError(f"SAS line {op['line']}: {error}") from error
            elif kind == 'put_character_list':
                if not isinstance(args.get('items'), list) or not args['items']:
                    raise ValueError('PUT character list: nonempty plan items required')
                for item in args['items']:
                    if not isinstance(item, dict) or set(item) != {'kind', 'value'} or not isinstance(item['value'], str):
                        raise ValueError('PUT character list: invalid plan item')
                    if item['kind'] == 'variable':
                        schema.setdefault(item['value'], 'number')
                    elif item['kind'] != 'literal':
                        raise ValueError('PUT character list: unsupported plan item')
            elif kind == 'put':
                for name in args['names']:
                    if name != '_n_':
                        schema.setdefault(name, 'number')
            elif kind in ('if', 'subset'):
                if kind == 'if':
                    if set(args) not in ({'condition', 'operation'}, {'condition', 'operation', 'otherwise'}):
                        raise ValueError('IF has unexpected plan arguments')
                    leaves = {'assign', 'array_set', 'array_current_set', 'sum_statement', 'output', 'put', 'put_literal', 'put_character_list', 'put_numeric_list', 'put_mixed_numeric'}
                    true_branch = args['operation']
                    false_branch = args.get('otherwise')
                    if (not isinstance(true_branch, dict) or true_branch.get('kind') not in leaves or
                            false_branch is not None and (not isinstance(false_branch, dict) or
                                false_branch.get('kind') not in leaves | {'if'})):
                        raise ValueError('IF branches require simple actions or an ELSE IF chain')
                    test = args['condition']
                    comparisons = {'=', 'eq', '^=', '~=', '<>', 'ne', '<', 'lt', '>', 'gt', '<=', 'le', '>=', 'ge'}
                    if (not isinstance(test, dict) or test.get('op') not in comparisons | {'truth'} or
                            set(test) != ({'left', 'op'} if test.get('op') == 'truth' else {'left', 'op', 'right'}) or
                            not isinstance(test['left'], dict) or
                            test.get('op') != 'truth' and not isinstance(test['right'], dict)):
                        raise ValueError('IF requires a supported predicate')
                validate_string_expressions(args['condition'], schema)
                for value in expressions(args['condition']):
                    add_reference(value)
            elif kind == 'output':
                if args['target'] not in (None, step['name']):
                    raise ValueError('OUTPUT target must be the declared DATA destination')
            else:
                raise ValueError(f'unsupported operation: {kind}')
        validate_array_step(step, schema)
        validate_counted_step(step, schema)
        for op in flat:
            validate_reverse_calls(op['args'], schema)
            validate_calendar_calls(op['args'], schema)
            validate_numeric_composition(op['args'], schema)
            if op['kind'] == 'sum_statement':
                validate_sum_expression(op['args']['value'], schema)
                if column_type(schema[op['args']['name']]) != 'number':
                    raise ValueError('sum statement requires a numeric target')
            elif op['kind'] in ('do_until', 'do_while'):
                for side in ('left', 'right'):
                    if side in op['args']['condition']:
                        validate_sum_expression(op['args']['condition'][side], schema)
        # Descriptors must be checked even for empty SET inputs or filtered
        # rows. Formats change PUT output and cannot silently be discarded.
        for op in flat:
            if op['kind'] == 'put_mixed_numeric':
                try:
                    validate_mixed_put_items(op['args']['items'], schema)
                except ValueError as exc:
                    raise ValueError(f"SAS line {op['line']}: {exc}") from exc
            if op['kind'] == 'put_character_list':
                resolved = []
                for item in op['args']['items']:
                    if item['kind'] == 'literal':
                        resolved.append(item)
                    else:
                        spec = schema[item['value']]
                        if column_type(spec) != 'character' or spec.get('format'):
                            raise ValueError(f"SAS line {op['line']}: PUT character list requires unformatted character variables")
                        resolved.append({'kind': 'character', 'value': 'x'})
                sas_put_character_list(resolved)
            elif op['kind'] == 'put_numeric_list':
                for name in op['args']['names']:
                    spec = schema[name]
                    if column_type(spec) != 'number' or isinstance(spec, dict) and spec.get('format'):
                        raise ValueError(f"SAS line {op['line']}: PUT numeric list requires unformatted numeric variables")
                sas_put_numeric_list([None] * len(op['args']['names']))
        for name in retained:
            schema.setdefault(name, 'number')
            if column_type(schema[name]) != 'number':
                raise ValueError('RETAIN initializers in this slice must be numeric')
        if put_all:
            display = step.get('display_names', {})
            for name, spec in schema.items():
                shown = display.get(name, name)
                if not isinstance(shown, str) or shown.lower() != name:
                    raise ValueError('PUT _ALL_: display name must match its PDV variable')
                if isinstance(spec, dict) and spec.get('format'):
                    raise ValueError('PUT _ALL_: attached formats require review')
            sas_put_all([{'name': display.get(n, n), 'kind': column_type(s),
                          'value': 'x' if column_type(s) == 'character' else None}
                         for n, s in schema.items()])
        if inputs and step['kind'] == 'data' and any(
                column_type(schema[k]) == 'character' and schema[k]['length'] != tables[inputs[0]]['schema'][k]['length'] for k in keys):
            raise ValueError('BY key width changes require review')
        if step['kind'] == 'merge' and any(op['kind'] in ('assign', 'round') and op['args']['name'] in legacy_schema for op in flat):
            raise ValueError('MERGE input-variable reassignment requires PDV merge-event review')
        if any(schema[k] != legacy_schema[k] for k in keys):
            raise ValueError('BY key descriptor changes require review')
        # An OUTPUT anywhere in the step disables implicit output, even if skipped.
        explicit = any(op['kind'] == 'output' for op in flat)
        output, retained_values = [], {n: number(v, {}) for n, v in retained.items()}
        input_vars = {col for n in inputs + lookups for col in tables[n]['schema']}
        if lookups and (not inputs or step['kind'] != 'data'):
            raise ValueError('initial lookup requires one driving SET')
        if lookups and not tables[lookups[0]]['rows']:
            rows = []  # SET EOF stops this DATA step before it can output.
        for index, input_row in enumerate(rows):
            row = {n: (' ' * spec['length'] if column_type(spec) == 'character' else None) for n, spec in schema.items()}
            row.update(deepcopy(retained_values))
            # The scoped lookup statement precedes the driving SET in source.
            if index == 0 and lookups:
                row.update(deepcopy(tables[lookups[0]]['rows'][0]))
            row.update(deepcopy(input_row))
            row = {n: coerce(v, schema[n], encoding) for n, v in row.items()}
            for name in array_members:
                row[name] = sas_numeric_array_value(row[name])
            row['_n_'] = float(index + 1)
            for pos, name in enumerate(keys):
                prefix = lambda r: key(r)[:pos+1]
                row['first.' + name] = float(index == 0 or prefix(rows[index-1]) != prefix(input_row))
                row['last.' + name] = float(index == len(rows)-1 or prefix(rows[index+1]) != prefix(input_row))

            def snapshot():
                output.append({n: deepcopy(row[n]) for n in schema})

            current = {}  # Internal per-row DO OVER bindings; never part of schema.
            counted_spent = 0  # Shared by A2 loops in this DATA iteration only.

            def sum_value(expr):
                """Check every numeric operand before arithmetic can hide a tag/overflow."""
                if arrays and contains_array(expr):
                    return array_value(expr, row, arrays, current)
                kind = expr['kind']
                if kind == 'arithmetic':
                    a, b = sum_value(expr['left']), sum_value(expr['right'])
                    value = sas_divide(a, b) if expr['op'] == '/' else None if a is None or b is None else sas_sum_statement(a, b if expr['op'] == '+' else -b)
                elif kind == 'call':
                    value = apply_function(expr['name'], [sum_value(arg) for arg in expr['args']])
                else:
                    value = number(expr, row, schema, arrays, current)
                sas_sum_statement(None, value)
                return value

            def perform(op, path):
                nonlocal counted_spent
                args, kind = op['args'], op['kind']
                if kind == 'assign':
                    expression = args['value']
                    name = expression.get('name') if expression.get('kind') == 'call' else None
                    if name in LAG_FUNCTIONS:
                        family, depth = LAG_FUNCTIONS[name]
                        if path not in lag_queues:
                            lag_queues[path] = SasNumericLagQueue(depth)
                        queue = lag_queues[path]
                        value = queue.invoke(number(expression['args'][0], row, schema), difference=family == 'dif')
                    else:
                        try:
                            value = put_all_value(expression, row) if put_all else number(expression, row, schema, arrays, current)
                        except ValueError as exc:
                            if arrays and contains_array(expression):
                                raise ValueError(f"SAS line {op['line']}: {exc}") from exc
                            raise
                    if args['value'].get('kind') == 'call' and args['value'].get('name') == 'catx':
                        if len(value) > schema[args['name']]['length']:
                            raise ValueError('CATX destination is too short; buffer/error-flag review required')
                    row[args['name']] = coerce(value, schema[args['name']], encoding)
                    if args['name'] in array_members:
                        row[args['name']] = sas_numeric_array_value(row[args['name']])
                elif kind == 'array_current_set':
                    name = args['name']
                    row[arrays[name]['names'][current[name]]] = array_value(args['value'], row, arrays, current)
                elif kind == 'array_set':
                    try:
                        a = arrays[args['name']]
                        index = sas_numeric_array_index(array_value(args['index'], row, arrays, current), a['lower'], len(a['names']))
                        row[a['names'][index]] = array_value(args['value'], row, arrays, current)
                    except ValueError as exc:
                        raise ValueError(f"SAS line {op['line']}: {exc}") from exc
                elif kind == 'round':
                    row[args['name']] = round_value(number(args['value'], row, schema, arrays, current), number(args['unit'], row, schema, arrays, current))
                    if args['name'] in array_members:
                        row[args['name']] = sas_numeric_array_value(row[args['name']])
                elif kind == 'sum_statement':
                    row[args['name']] = sas_sum_statement(row[args['name']], sum_value(args['value']))
                elif kind == 'do_over':
                    name = args['name']
                    def body(offset):
                        current[name] = offset
                        for child_index, child in enumerate(args['body']):
                            perform(child, path + ('body', child_index))
                    try:
                        sas_do_over(len(arrays[name]['names']), body)
                    finally:
                        current.pop(name, None)
                elif kind == 'do_counted':
                    if args.get('profile') == 'bounded':
                        try:
                            controls = [evaluate_control(args[k], row) for k in ('start', 'stop', 'by')]
                            values, final, counted_spent = sas_counted_capture(*controls, counted_spent)
                        except ValueError as exc:
                            raise ValueError(f"SAS line {op['line']}: {exc}") from exc
                    else:
                        values, final = sas_do_counted(args['start'], args['stop'], args['by'])
                    for value in values:
                        row[args['index']] = float(value)
                        for child_index, child in enumerate(args['body']):
                            perform(child, path + ('body', child_index))
                    row[args['index']] = float(final)
                elif kind in ('do_until', 'do_while'):
                    def body():
                        for child_index, child in enumerate(args['body']):
                            perform(child, path + ('body', child_index))
                    def stop():
                        test = args['condition']
                        resolved = {side: {'kind': 'number', 'value': sum_value(test[side])}
                                    for side in ('left', 'right') if side in test}
                        return condition({'op': test['op'], **resolved}, row, schema)
                    (sas_do_until if kind == 'do_until' else sas_do_while)(body, stop)
                elif kind == 'if':
                    if condition(args['condition'], row, schema, arrays, current):
                        return perform(args['operation'], path + ('operation',))
                    if 'otherwise' in args:
                        return perform(args['otherwise'], path + ('otherwise',))
                elif kind == 'subset':
                    return condition(args['condition'], row, schema, arrays, current)
                elif kind == 'output':
                    snapshot()
                elif kind == 'put_literal':
                    logs.append(sas_put_literals(args['literals']))
                elif kind == 'put_all':
                    logs.append(sas_put_all([{'name': display.get(n, n), 'kind': column_type(s), 'value': row[n]}
                                             for n, s in schema.items()]))
                elif kind == 'put_numeric_list':
                    try:
                        logs.append(sas_put_numeric_list([row[name] for name in args['names']]))
                    except ValueError as exc:
                        raise ValueError(f"SAS line {op['line']}: {exc}") from exc
                elif kind == 'put_mixed_numeric':
                    resolved = [item if item['kind'] == 'literal' else
                                {'kind': 'numeric', 'value': row[item['value']]}
                                for item in args['items']]
                    try:
                        logs.append(sas_put_mixed_numeric(resolved))
                    except ValueError as exc:
                        raise ValueError(f"SAS line {op['line']}: {exc}") from exc
                elif kind == 'put_character_list':
                    resolved = [item if item['kind'] == 'literal' else
                                {'kind': 'character', 'value': row[item['value']]}
                                for item in args['items']]
                    try:
                        logs.append(sas_put_character_list(resolved))
                    except ValueError as exc:
                        raise ValueError(f"SAS line {op['line']}: {exc}") from exc
                elif kind == 'put':
                    def render(v):
                        if v is None: return '.'
                        if isinstance(v, dict): return '.' + v['missing']
                        if isinstance(v, str): return v.rstrip(' ')
                        return format(v, '.17g')
                    logs.append(' '.join(n + '=' + render(row.get(n)) for n in args['names']))
                elif kind not in ('lookup', 'read', 'declare', 'array_declare'):
                    raise ValueError(f'unsupported operation: {kind}')
                return True

            if arrays:
                raw_perform = perform
                def perform(op, path):
                    try:
                        return raw_perform(op, path)
                    except ValueError as exc:
                        if str(exc).startswith('SAS line '):
                            raise
                        raise ValueError(f"SAS line {op['line']}: {exc}") from exc
            completed = all(perform(op, (position,)) for position, op in enumerate(ops))
            retained_values = {n: deepcopy(row[n]) for n in input_vars | set(retained)}
            if completed and not explicit:
                snapshot()
        if step['name'] != '_null_':
            tables[step['name']] = {**metadata, 'schema': schema, 'rows': output}
    return {'datasets': tables, 'log': logs}
