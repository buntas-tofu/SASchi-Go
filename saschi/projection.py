"""Bounded declarative KEEP/DROP selection with explicit input/output timing."""
from copy import deepcopy
import re

from .operations import walk_operations

NAME = r'[A-Za-z_][A-Za-z0-9_]{0,31}'
RESERVED = {'_n_', '_error_', '_all_', '_numeric_', '_character_', '_temporary_',
            '_infile_', '_file_', '_ods_', '_page_', '_blankpage_'}
LIMIT = 64


def names_valid(names):
    return (isinstance(names, list) and 1 <= len(names) <= LIMIT
            and all(isinstance(n, str) and re.fullmatch(NAME, n, re.ASCII)
                    and n == n.lower() and n not in RESERVED for n in names)
            and len(set(names)) == len(names))


def name_list(text):
    """Explicit names and ascending shared-prefix unpadded numbered ranges."""
    names = []
    rest = text.strip()
    while rest:
        match = re.match(r'(' + NAME + r')(?:\s*-\s*(' + NAME + r'))?(?=\s|$)', rest, re.ASCII)
        if not match:
            raise ValueError('projection requires explicit names or ascending numbered ranges')
        first, last = (s.lower() if s else s for s in match.groups())
        if last is None:
            names.append(first)
        else:
            a = re.fullmatch(r'([a-z_][a-z0-9_]*?)([0-9]+)', first)
            b = re.fullmatch(r'([a-z_][a-z0-9_]*?)([0-9]+)', last)
            if (not a or not b or a[1] != b[1] or len(a[2]) > 2 or len(b[2]) > 2
                    or a[2].startswith('0') or b[2].startswith('0')
                    or not 1 <= int(a[2]) <= int(b[2]) <= 64):
                raise ValueError('projection ranges require shared prefixes and unpadded suffixes1..64')
            names.extend(a[1] + str(n) for n in range(int(a[2]), int(b[2]) + 1))
        if len(names) > LIMIT:
            raise ValueError('projection exceeds the64-name policy')
        rest = rest[match.end():].strip()
    if not names_valid(names):
        raise ValueError('projection requires1..64 unique ordinary names')
    return names


def declaration(text, scope='statement'):
    separator = r'\s+' if scope == 'statement' else r'\s*=\s*'
    match = re.fullmatch(r'(keep|drop)' + separator + r'(.+)', text, re.I | re.S | re.ASCII)
    if not match:
        raise ValueError('projection requires one KEEP or DROP list with complete syntax')
    return {'mode': match[1].lower(), 'names': name_list(match[2]), 'scope': scope}


def dataset(text, keyword):
    """Consume a single DATA/SET name and at most one complete projection option."""
    match = re.fullmatch(keyword + r'\s+(' + NAME + r')\s*(?:\(\s*(.*?)\s*\))?',
                         text, re.I | re.S | re.ASCII)
    if not match:
        raise ValueError('supported ' + keyword.upper() + ' syntax is one name and optional KEEP=/DROP=')
    option = declaration(match[2], 'output' if keyword == 'data' else 'input') if match[2] is not None else None
    return match[1].lower(), option


def validate_step(step, version=2):
    """Check forged declarations before descriptors, row count or branch execution."""
    roots = step['operations']
    if not any(op['kind'] == 'projection' for op in walk_operations(roots, all_containers=True)):
        return None, None
    prefix = 0
    if any(op['kind'] == 'numeric_profile' for op in walk_operations(roots, all_containers=True)):
        # The public path authorizes the prefix through the complete numeric
        # validator. That validator calls only the private context helper below.
        from .binary64 import validate_step as validate_numeric_step, ROWS_PROFILE
        from .numeric_pipeline import PROFILE as PIPELINE_PROFILE
        validate_numeric_step(step, version)
        if roots[0]['args'] not in ({'name': ROWS_PROFILE}, {'name': PIPELINE_PROFILE}):
            raise ValueError('projection numeric prefix requires the separately proved row profile')
        prefix = 1
    return _validate_step(step, version, prefix=prefix)


def _validate_step(step, version=2, *, prefix=0):
    """Projection context after the caller independently authorizes its prefix."""
    roots = step['operations']
    found = [op for op in walk_operations(roots, all_containers=True) if op['kind'] == 'projection']
    if not found:
        return None, None
    if version != 2 or step['kind'] != 'data':
        raise ValueError('projection requires a version2 DATA step')
    inputs, outputs = [], []
    for op in found:
        args = op['args']
        if (not any(op is root for root in roots) or set(op) != {'kind', 'line', 'args'}
                or not isinstance(args, dict) or set(args) != {'mode', 'names', 'scope'}
                or args['mode'] not in ('keep', 'drop') or args['scope'] not in ('statement', 'input', 'output')
                or not names_valid(args['names']) or type(op.get('line')) is not int or op['line'] < 1):
            raise ValueError('projection requires one top-level well-formed ordinary-name declaration')
        if args['scope'] == 'input':
            inputs.append(args)
            position = next(i for i, root in enumerate(roots) if root is op)
            reads = [o for o in walk_operations(roots, all_containers=True) if o['kind'] == 'read']
            if (len(step['inputs']) != 1 or step.get('by') or step.get('where')
                    or any(root['kind'] not in ('declare', 'array_declare', 'projection')
                           for root in roots[prefix:position])
                    or any(o['kind'] == 'lookup' for o in walk_operations(roots, all_containers=True))
                    or len(reads) != 1 or position + 1 >= len(roots) or roots[position + 1] is not reads[0]
                    or reads[0]['args'] != {'datasets': step['inputs']} or reads[0]['line'] != op['line']):
                raise ValueError('input projection requires one adjacent driving SET without lookup/BY/WHERE')
        else:
            outputs.append(args)
            if args['scope'] == 'output' and (roots[prefix] is not op or op['line'] != step['line']):
                raise ValueError('output option projection must be first at its DATA source line')
    if len(inputs) > 1 or len(outputs) > 1:
        raise ValueError('projection permits one input option and one output selection; conflicting lists require review')
    return (inputs[0] if inputs else None), (outputs[0] if outputs else None)


def selected_names(schema, selection):
    """Resolve against a complete descriptor without altering descriptor order."""
    if selection is None:
        return list(schema)
    if not set(selection['names']) <= set(schema):
        raise ValueError('projection list contains a variable absent from its complete schema')
    selected = set(selection['names'])
    names = [n for n in schema if (n in selected) == (selection['mode'] == 'keep')]
    if not names:
        raise ValueError('projection cannot produce an empty descriptor in this profile')
    return names


def project_table(table, selection):
    names = selected_names(table['schema'], selection)
    return {**{k: deepcopy(v) for k, v in table.items() if k not in ('schema', 'rows')},
            'schema': {n: deepcopy(table['schema'][n]) for n in names},
            'rows': [{n: deepcopy(row[n]) for n in names} for row in table['rows']]}
