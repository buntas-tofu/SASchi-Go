"""Execute bounded DATA events with typed catalogs; version 1 plans remain readable."""
from __future__ import annotations
import math
from collections import Counter
from copy import deepcopy
from sas_semantics import sas_round, sas_merge_by, sas_put_literals, sas_put_character_list, sas_put_all
from .functions import apply as apply_function, assign_spec
from .values import normalize_catalog, column_type, coerce, missing, order


def evaluate(expr, row):
    """Value of one wired function call."""
    return apply_function(expr['name'], [argument(arg, row) for arg in expr['args']])


def argument(expr, row):
    """One call argument: a format token passes through, everything else is a value."""
    return expr if expr['kind'] == 'format' else number(expr, row)


def number(expr, row):
    kind = expr['kind']
    if kind in ('variable', 'automatic'):
        return row.get(expr['value'])
    if kind == 'call':
        return evaluate(expr, row)
    if kind == 'arithmetic':
        left, right = number(expr['left'], row), number(expr['right'], row)
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


def condition(expr, row):
    left = number(expr['left'], row)
    op = expr['op']
    if op == 'truth':
        if isinstance(left, str):
            raise ValueError('numeric truth predicate required')
        return not missing(left) and left != 0
    right = number(expr['right'], row)
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


def operations(ops):
    for op in ops:
        yield op
        if op['kind'] == 'if':
            yield from operations([op['args']['operation']])


def put_all_value(expr, row):
    """Error-free scalar expressions for the DS-025 _ERROR_=0 contract."""
    if expr['kind'] == 'call':
        name = expr['name']
        if name not in ('length', 'lengthn', 'lengthc', 'substr'):
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
        flat = list(operations(ops))
        put_all = any(op['kind'] == 'put_all' for op in flat)
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
                    if isinstance(schema[col], dict) and not schema[col].get('format'):
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
            if any(e['kind'] == 'automatic' or e['value'] not in tables[inputs[0]]['schema'] for e in expressions(where)):
                raise ValueError('WHERE can reference only driving input columns')
            rows = [r for r in rows if condition(where, r)]
        if keys and any(key(a) > key(b) for a, b in zip(rows, rows[1:])):
            raise ValueError('SET BY requires ascending sorted rows after WHERE')
        retained = step.get('retained', {})
        legacy_schema = schema
        schema = {} if plan['version'] == 2 else schema

        def add_input(name):
            for col, spec in tables[name]['schema'].items():
                if col in schema and column_type(schema[col]) != column_type(spec):
                    raise ValueError('incompatible input column types')
                schema.setdefault(col, deepcopy(spec))
                # LENGTH sets width without removing an inherited format.
                if isinstance(spec, dict) and spec.get('format'):
                    if isinstance(schema[col], dict) and not schema[col].get('format'):
                        schema[col]['format'] = spec['format']

        def add_reference(expr):
            if expr['kind'] == 'automatic':
                if expr['value'] != '_n_' and expr['value'].split('.', 1)[1] not in keys:
                    raise ValueError('FIRST/LAST requires the corresponding BY key')
            else:
                schema.setdefault(expr['value'], 'number')

        for op in flat:
            args, kind = op['args'], op['kind']
            if kind == 'declare':
                name, spec = args['name'], args['spec']
                if name in schema and column_type(schema[name]) != column_type(spec):
                    raise ValueError('incompatible declaration types')
                schema.setdefault(name, deepcopy(spec))
            elif kind == 'read':
                for name in args['datasets']:
                    add_input(name)
            elif kind == 'lookup':
                add_input(args['dataset'])
            elif kind in ('assign', 'round'):
                expr = args['value']
                if kind == 'assign' and expr['kind'] == 'character':
                    spec = {'type': 'character', 'length': max(1, len(expr['value'].encode(encoding)))}
                elif kind == 'assign' and expr['kind'] == 'variable':
                    # An assigned copy gets type/width, not the source label/format.
                    origin = schema.get(expr['value'], 'number')
                    spec = {'type': 'character', 'length': origin['length']} if column_type(origin) == 'character' else 'number'
                else:
                    spec = (assign_spec(expr) if kind == 'assign' else None) or 'number'
                if args['name'] in schema and column_type(schema[args['name']]) != column_type(spec):
                    raise ValueError('implicit assignment type conversion is unsupported')
                schema.setdefault(args['name'], spec)
                for value in expressions(args):
                    add_reference(value)
            elif kind == 'put_literal':
                sas_put_literals(args['literals'])
            elif kind == 'put_all':
                if args:
                    raise ValueError('PUT _ALL_: unexpected plan arguments')
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
                for value in expressions(args['condition']):
                    add_reference(value)
            elif kind == 'output':
                if args['target'] not in (None, step['name']):
                    raise ValueError('OUTPUT target must be the declared DATA destination')
            else:
                raise ValueError(f'unsupported operation: {kind}')
        # Descriptors must be checked even for empty SET inputs or filtered
        # rows. Formats change PUT output and cannot silently be discarded.
        for op in flat:
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
            row['_n_'] = float(index + 1)
            for pos, name in enumerate(keys):
                prefix = lambda r: key(r)[:pos+1]
                row['first.' + name] = float(index == 0 or prefix(rows[index-1]) != prefix(input_row))
                row['last.' + name] = float(index == len(rows)-1 or prefix(rows[index+1]) != prefix(input_row))

            def snapshot():
                output.append({n: deepcopy(row[n]) for n in schema})

            def perform(op):
                args, kind = op['args'], op['kind']
                if kind == 'assign':
                    value = put_all_value(args['value'], row) if put_all else number(args['value'], row)
                    row[args['name']] = coerce(value, schema[args['name']], encoding)
                elif kind == 'round':
                    row[args['name']] = round_value(number(args['value'], row), number(args['unit'], row))
                elif kind == 'if':
                    if condition(args['condition'], row):
                        return perform(args['operation'])
                elif kind == 'subset':
                    return condition(args['condition'], row)
                elif kind == 'output':
                    snapshot()
                elif kind == 'put_literal':
                    logs.append(sas_put_literals(args['literals']))
                elif kind == 'put_all':
                    logs.append(sas_put_all([{'name': display.get(n, n), 'kind': column_type(s), 'value': row[n]}
                                             for n, s in schema.items()]))
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
                elif kind not in ('lookup', 'read', 'declare'):
                    raise ValueError(f'unsupported operation: {kind}')
                return True

            completed = all(perform(op) for op in ops)
            retained_values = {n: deepcopy(row[n]) for n in input_vars | set(retained)}
            if completed and not explicit:
                snapshot()
        if step['name'] != '_null_':
            tables[step['name']] = {**metadata, 'schema': schema, 'rows': output}
    return {'datasets': tables, 'log': logs}
