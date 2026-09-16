"""Execute bounded DATA events with typed catalogs; version 1 plans remain readable."""
from __future__ import annotations
import math
from collections import Counter
from copy import deepcopy
from sas_semantics import sas_round, sas_merge_by
from .values import normalize_catalog, column_type, coerce, missing, order


def number(expr, row):
    kind = expr['kind']
    if kind in ('variable', 'automatic'):
        return row.get(expr['value'])
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


def run_plan(plan, catalog=None, *, allow_partial=False):
    if plan['version'] not in (1, 2):
        raise ValueError('unsupported plan version')
    if plan['tickets'] and not allow_partial:
        raise RuntimeError('saschi: blocked translation. Nothing from this program was executed.')
    tables, logs = normalize_catalog({} if catalog is None else catalog), []
    for step in plan['steps']:
        inputs, keys, ops = step['inputs'], step['by'], step['operations']
        flat = list(operations(ops))
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
                    spec = 'number'
                if args['name'] in schema and column_type(schema[args['name']]) != column_type(spec):
                    raise ValueError('implicit assignment type conversion is unsupported')
                schema.setdefault(args['name'], spec)
                for value in expressions(args):
                    add_reference(value)
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
        for name in retained:
            schema.setdefault(name, 'number')
            if column_type(schema[name]) != 'number':
                raise ValueError('RETAIN initializers in this slice must be numeric')
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
                    row[args['name']] = coerce(number(args['value'], row), schema[args['name']], encoding)
                elif kind == 'round':
                    row[args['name']] = round_value(number(args['value'], row), number(args['unit'], row))
                elif kind == 'if':
                    if condition(args['condition'], row):
                        return perform(args['operation'])
                elif kind == 'subset':
                    return condition(args['condition'], row)
                elif kind == 'output':
                    snapshot()
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
