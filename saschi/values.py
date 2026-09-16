"""Typed catalog boundary and finite character assignment contract."""
from copy import deepcopy
import math
import re
from sas_semantics import sas_fixed_character, sas_numeric_order


def column_type(descriptor):
    return descriptor if isinstance(descriptor, str) else descriptor['type']


def missing(value):
    return value is None or isinstance(value, dict)


def descriptor(value):
    if value == 'number':
        return value
    if not isinstance(value, dict) or value.get('type') not in ('number', 'character'):
        raise ValueError('schema requires number or a typed column descriptor')
    if set(value) - {'type', 'length', 'label', 'format'}:
        raise ValueError('unsupported column metadata')
    for key in ('label', 'format'):
        if key in value and not isinstance(value[key], str):
            raise ValueError('label and format metadata must be text')
    width = value.get('length', 8)
    if isinstance(width, bool) or not isinstance(width, int):
        raise ValueError('column length must be an integer')
    if value['type'] == 'number' and width != 8:
        raise ValueError('numeric storage lengths other than 8 are unsupported')
    if value['type'] == 'character' and ('length' not in value or not 1 <= width <= 32767):
        raise ValueError('character schema requires a byte length 1..32767')
    return deepcopy(value)


def coerce(value, spec, encoding):
    if column_type(spec) == 'character':
        return sas_fixed_character(value, spec['length'], encoding)
    sas_numeric_order(value)
    if missing(value):
        return deepcopy(value)
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError('numeric input exceeds binary64 range') from exc
    if not math.isfinite(result):
        raise ValueError('non-finite inputs must be represented as null')
    return result


def normalize_catalog(catalog):
    if not isinstance(catalog, dict):
        raise ValueError('catalog must be an object of named tables')
    result = {}
    for raw_name, table in catalog.items():
        if not isinstance(raw_name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,31}', raw_name):
            raise ValueError('invalid dataset name')
        if not isinstance(table, dict) or not isinstance(table.get('schema'), dict) or not isinstance(table.get('rows'), list):
            raise ValueError('table requires a schema object and a rows array')
        if any(not isinstance(k, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,31}', k) for k in table['schema']):
            raise ValueError('invalid column name')
        name = raw_name.lower()
        if name in result:
            raise ValueError(f'duplicate dataset name: {raw_name}')
        if set(table) - {'schema', 'rows', 'encoding', 'label'}:
            raise ValueError('unsupported table metadata')
        encoding = table.get('encoding', 'utf-8')
        if encoding not in ('utf-8', 'ascii', 'latin-1'):
            raise ValueError('supported encodings are utf-8, ascii, latin-1')
        if 'label' in table and not isinstance(table['label'], str):
            raise ValueError('table label must be text')
        schema = {k.lower(): descriptor(v) for k, v in table['schema'].items()}
        if set(schema) & {'_n_', '_error_'}:
            raise ValueError('automatic variable names cannot be input columns')
        if len(schema) != len(table['schema']):
            raise ValueError('duplicate column name')
        rows = []
        for raw_row in table['rows']:
            if not isinstance(raw_row, dict) or any(not isinstance(k, str) for k in raw_row):
                raise ValueError('each row must be an object with column names')
            row = {k.lower(): v for k, v in raw_row.items()}
            if len(row) != len(raw_row) or set(row) != set(schema):
                raise ValueError(f'row does not match schema in {name}')
            # Imported values must fit; truncation is an assignment operation.
            for key, value in row.items():
                if column_type(schema[key]) == 'character' and isinstance(value, str):
                    if len(value.encode(encoding)) > schema[key]['length']:
                        raise ValueError(f'input exceeds declared character length: {name}.{key}')
                row[key] = coerce(value, schema[key], encoding)
            rows.append(row)
        result[name] = {**deepcopy(table), 'schema': schema, 'rows': rows}
    return result


def order(value):
    return (2, value) if isinstance(value, str) else sas_numeric_order(value)
