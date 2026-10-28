"""DS-042 exact plan shape and descriptor checks, independent of compilation."""
from sas_semantics import sas_put_mixed_numeric
from .arrays import ordinary
from .values import column_type


def validate_items(items, schema=None):
    if not isinstance(items, list) or not 2 <= len(items) <= 64:
        raise ValueError('PUT mixed numeric: requires2..64 ordered plan items')
    resolved = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {'kind', 'value'}:
            raise ValueError('PUT mixed numeric: invalid plan item fields')
        kind, value = item['kind'], item['value']
        if kind == 'literal':
            resolved.append(item)
        elif kind == 'variable' and ordinary(value):
            if schema is not None:
                if value not in schema:
                    raise ValueError('PUT mixed numeric: variables must be known before PUT')
                spec = schema[value]
                if column_type(spec) != 'number' or isinstance(spec, dict) and spec.get('format'):
                    raise ValueError('PUT mixed numeric requires unformatted numeric variables')
            resolved.append({'kind': 'numeric', 'value': None})
        else:
            raise ValueError('PUT mixed numeric: requires literals and normalized ordinary variables')
    # Validate literals and the minimum record width even on empty/skipped paths.
    sas_put_mixed_numeric(resolved)
