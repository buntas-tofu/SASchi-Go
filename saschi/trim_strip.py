"""DS-043 expression/context validation, independent of execution and receipts."""
import re

from sas_semantics import sas_trim
from .operations import walk_operations

NAMES = {'trim', 'strip'}
RESERVED = {'_n_', '_error_', '_all_', '_numeric_', '_character_', '_infile_',
            '_file_', '_ods_', '_page_', '_blankpage_'}


def is_call(value):
    return (isinstance(value, dict) and value.get('kind') == 'call'
            and isinstance(value.get('name'), str) and value['name'] in NAMES)


def contains(value):
    """Find actual calls without interpreting strings or recursing into deep plans."""
    pending, seen = [value], set()
    while pending:
        node = pending.pop()
        if is_call(node):
            return True
        if isinstance(node, (dict, list, tuple)) and id(node) not in seen:
            seen.add(id(node))
            pending.extend(node.values() if isinstance(node, dict) else node)
    return False


def argument_width(arg, schema=None):
    """Only ordinary literal/variable character arguments, with static widths."""
    if not isinstance(arg, dict) or set(arg) != {'kind', 'value'}:
        raise ValueError('TRIM/STRIP requires one character literal or variable')
    kind, value = arg['kind'], arg['value']
    if kind == 'character':
        sas_trim(value)
        return len(value)
    if (kind != 'variable' or not isinstance(value, str) or
            not re.fullmatch(r'[a-z_][a-z0-9_]{0,31}', value) or value in RESERVED):
        raise ValueError('TRIM/STRIP requires an ordinary character literal or variable')
    if schema is None:
        return None
    spec = schema.get(value)
    if (not isinstance(spec, dict) or spec.get('type') != 'character' or
            type(spec.get('length')) is not int or not 1 <= spec['length'] <= 32767):
        raise ValueError('TRIM/STRIP requires a preceding character descriptor, width 1..32767')
    return spec['length']


def call_width(expr, schema=None):
    if not is_call(expr) or set(expr) != {'kind', 'name', 'args'}:
        raise ValueError('TRIM/STRIP requires an exact call shape')
    args = expr['args']
    if not isinstance(args, list) or len(args) != 1:
        raise ValueError('TRIM/STRIP requires exactly one character argument')
    return argument_width(args[0], schema)


def validate_expression(value, schema=None, *, context='other'):
    if not contains(value):
        return
    if context != 'assignment' or not isinstance(value, dict):
        raise ValueError('TRIM/STRIP temporary consumers require review; assignment or concatenation RHS only')
    if is_call(value):
        call_width(value, schema)
        return
    if value.get('kind') != 'concat' or set(value) != {'kind', 'args'}:
        raise ValueError('TRIM/STRIP requires direct assignment or a character concatenation RHS')
    args = value['args']
    if not isinstance(args, list) or not 2 <= len(args) <= 32:
        raise ValueError('TRIM/STRIP concatenation requires 2..32 operands')
    widths = [call_width(arg, schema) if is_call(arg) else argument_width(arg, schema)
              for arg in args]
    if schema is not None and sum(widths) > 32767:
        raise ValueError('TRIM/STRIP concatenation declared width exceeds 32767 bytes')


def validate_step(step, version=2):
    """Same structural and container refusals for source and serialized plans."""
    if not contains(step):
        return
    if version != 2 or step.get('kind') != 'data':
        raise ValueError('TRIM/STRIP requires version2 DATA execution')
    validate_expression(step.get('where'))
    validate_expression(step.get('retained'))
    flat = list(walk_operations(step['operations']))
    if any(op['kind'] == 'put_all' for op in flat):
        raise ValueError('TRIM/STRIP with PUT _ALL_ requires error-state review')
    for op in flat:
        args, kind = op['args'], op['kind']
        if kind in ('do_until', 'do_while', 'do_over') and contains(args):
            raise ValueError('TRIM/STRIP is gated in counted bodies only; other loop families require review')
        payloads = [(args.get('value'), 'assignment')] if kind == 'assign' else [
            (value, 'other') for key, value in args.items()
            if key not in ('body', 'operation', 'otherwise')]
        for value, context in payloads:
            validate_expression(value, context=context)
