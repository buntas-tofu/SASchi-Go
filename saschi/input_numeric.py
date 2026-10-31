"""DS-058/059 separately marked bounded comma and numbered-list input."""
from copy import deepcopy
import re

from sas_semantics import sas_input_number
from .input_list import names_valid
from .operations import walk_operations
from .values import descriptor, column_type

PROFILE = 'numeric-inline-v1'
NAME = r'[a-z_][a-z0-9_]{0,31}'
FIELDS = {'profile', 'terms', 'names', 'delimiter', 'firstobs', 'infile_line', 'records', 'data_line'}


def expand_terms(terms):
    """Expand bounded canonical terms before uniqueness and allocation checks."""
    if not isinstance(terms, list) or not 1 <= len(terms) <= 32:
        raise ValueError('numeric INPUT requires1..32 canonical terms')
    names = []
    for term in terms:
        if not isinstance(term, str) or not re.fullmatch(NAME + r'(?:-' + NAME + r')?', term, re.ASCII):
            raise ValueError('numeric INPUT terms require lowercase names or one numbered range')
        if '-' not in term:
            names.append(term)
        else:
            first, last = term.split('-')
            a = re.fullmatch(r'([a-z_][a-z0-9_]*?)([0-9]+)', first, re.ASCII)
            b = re.fullmatch(r'([a-z_][a-z0-9_]*?)([0-9]+)', last, re.ASCII)
            if (not a or not b or a[1] != b[1] or len(a[2]) > 2 or len(b[2]) > 2
                    or a[2].startswith('0') or b[2].startswith('0')
                    or not 1 <= int(a[2]) <= int(b[2]) <= 64):
                raise ValueError('numeric INPUT ranges require a common prefix and unpadded suffixes1..64')
            if len(names) + int(b[2]) - int(a[2]) + 1 > 32:
                raise ValueError('numeric INPUT expansion exceeds32 names')
            names.extend(a[1] + str(i) for i in range(int(a[2]), int(b[2]) + 1))
        if len(names) > 32:
            raise ValueError('numeric INPUT expansion exceeds32 names')
    if not names_valid(names):
        raise ValueError('numeric INPUT expansion requires1..32 unique ordinary names')
    return names


def parse_terms(text):
    if not isinstance(text, str) or not text.isascii():
        raise ValueError('numeric INPUT source names require ASCII before normalization')
    terms, rest = [], text.strip().lower()
    while rest:
        match = re.match(r'(' + NAME + r')(?:\s*-\s*(' + NAME + r'))?(?=\s|$)', rest, re.ASCII)
        if not match:
            raise ValueError('numeric INPUT requires fully consumed names or numbered ranges')
        terms.append(match[1] + ('-' + match[2] if match[2] else ''))
        if len(terms) > 32:
            raise ValueError('numeric INPUT exceeds32 terms')
        rest = rest[match.end():].strip()
    return terms, expand_terms(terms)


def parse_infile(text):
    head = re.match(r'infile\s+(?:datalines|cards)\s+', text, re.I | re.ASCII)
    if not head:
        raise ValueError('numeric INFILE requires inline DATALINES or CARDS and comma DLM')
    options, rest = {}, text[head.end():]
    while rest:
        match = re.match(r'''(?:(dlm)\s*=\s*(['"]),(?:\2)|(firstobs)\s*=\s*([1-9][0-9]{0,4}))(?=\s|$)''', rest, re.I | re.ASCII)
        if not match:
            raise ValueError('numeric INFILE supports only comma DLM and FIRSTOBS')
        key = (match[1] or match[3]).lower()
        if key in options:
            raise ValueError('numeric INFILE options cannot repeat')
        options[key] = ',' if key == 'dlm' else int(match[4])
        rest = rest[match.end():].strip()
    if options.get('dlm') != ',' or not 1 <= options.get('firstobs', 1) <= 10001:
        raise ValueError('numeric INFILE requires comma DLM and FIRSTOBS in1..10001')
    return {'delimiter': ',', 'firstobs': options.get('firstobs', 1)}


def decode(records, width, delimiter, firstobs):
    """Validate every physical record, then convert only consumed numeric fields."""
    # FIRSTOBS skips conversion, never the physical-record bounds.
    if type(firstobs) is not int or not 1 <= firstobs <= 10001 or delimiter not in (' ', ','):
        raise ValueError('numeric input options require a supported delimiter and FIRSTOBS')
    if type(width) is not int or not 1 <= width <= 32:
        raise ValueError('numeric input requires1..32 fields')
    if not isinstance(records, list) or len(records) > 10000:
        raise ValueError('numeric input requires at most10000 physical records')
    for record in records:
        if (not isinstance(record, str) or len(record) > 80 or ';' in record
                or any(not 32 <= ord(c) <= 126 for c in record)):
            raise ValueError('numeric input requires printable ASCII records up to80 bytes without semicolons')
    rows, pending = [], []
    for record in records[firstobs - 1:]:
        if not record.strip(' '):
            continue
        for field in record.split(delimiter):
            if not field:
                continue
            token = field.strip(' ') if delimiter == ',' else field
            if not token:
                raise ValueError('consumed blank-only comma fields require separate SAS characterization')
            pending.append(sas_input_number(token))
            if len(pending) == width:
                rows.append(pending)
                pending = []
                break
    return rows


def validate_step(step, version=2):
    """Return decoded observations only for a complete new-profile step."""
    from .binary64 import _structure
    # Old plans keep their previous validators and shapes. Inspect containers
    # safely before operation traversal when any new operation is present.
    pending, seen, found = [step], set(), False
    while pending:
        node = pending.pop()
        if isinstance(node, (dict, list, tuple)):
            if id(node) in seen:
                continue
            seen.add(id(node))
            if isinstance(node, dict) and node.get('kind') == 'input_numeric':
                found = True
            pending.extend(node.values() if isinstance(node, dict) else node)
    if not found:
        return None
    _structure(step)
    expected = {'kind', 'name', 'line', 'inputs', 'by', 'operations', 'nodupkey',
                'where', 'retained', 'lengths', 'display_names'}
    if (type(version) is not int or version != 2 or set(step) != expected
            or step['kind'] != 'data' or not isinstance(step['name'], str)
            or not re.fullmatch(NAME, step['name'], re.ASCII)
            or type(step['inputs']) is not list or step['inputs'] != []
            or type(step['by']) is not list or step['by'] != []
            or step['where'] is not None or step['nodupkey'] is not False
            or type(step.get('line')) is not int or step['line'] < 1
            or not isinstance(step['operations'], list) or not isinstance(step['lengths'], dict)
            or not isinstance(step['display_names'], dict) or not isinstance(step['retained'], dict)):
        raise ValueError('numeric inline profile requires a version2 DATA step without SET/BY/WHERE')
    if any(not names_valid([name]) for name in step['retained']):
        raise ValueError('numeric inline retained targets require ordinary names')
    for name, width in step['lengths'].items():
        if not names_valid([name]) or type(width) is not int or not 1 <= width <= 32767:
            raise ValueError('numeric inline LENGTH metadata requires ordinary names and integer widths')
    for name, shown in step['display_names'].items():
        if (not (names_valid([name]) or name == '_n_') or not isinstance(shown, str)
                or not shown.isascii() or shown.lower() != name):
            raise ValueError('numeric inline display metadata must preserve ordinary names')
    flat = list(walk_operations(step['operations'], all_containers=True))
    if any(type(o.get('line')) is not int or o['line'] < step['line'] for o in flat):
        raise ValueError('numeric inline operations require integer source lines')
    declared_widths = {}
    for action in flat:
        if action['kind'] in ('declare', 'assign', 'round', 'sum_statement') and not names_valid([action['args'].get('name')]):
            raise ValueError('numeric inline scalar targets require ordinary names')
        if action['kind'] == 'declare':
            spec = descriptor(action['args'].get('spec'))
            if column_type(spec) == 'character':
                if action['args']['name'] in declared_widths:
                    raise ValueError('numeric inline character declarations cannot repeat a LENGTH name')
                declared_widths[action['args']['name']] = spec['length']
    if step['lengths'] != declared_widths:
        raise ValueError('numeric inline LENGTH metadata must match its character declarations')
    from .functions import expression_nodes
    for expr, _ in expression_nodes(step):
        if expr.get('kind') == 'variable' and not names_valid([expr.get('value')]):
            raise ValueError('numeric inline references require ordinary names')
    inputs = [o for o in flat if o['kind'] == 'input_numeric']
    if len(inputs) != 1:
        raise ValueError('numeric inline profile requires exactly one input source')
    op = inputs[0]
    if not any(op is root for root in step['operations']):
        raise ValueError('numeric inline INPUT must be top-level')
    args = op['args']
    if (set(args) != FIELDS or args.get('profile') != PROFILE
            or type(op.get('line')) is not int or op['line'] < step['line']
            or type(args.get('data_line')) is not int or args['data_line'] <= op['line']
            or args.get('delimiter') not in (' ', ',') or type(args.get('firstobs')) is not int
            or not 1 <= args['firstobs'] <= 10001):
        raise ValueError('numeric inline INPUT requires exact profile, fields and source metadata')
    if any(o['line'] >= args['data_line'] for o in flat):
        raise ValueError('numeric inline actions must precede the physical data block')
    names = expand_terms(args['terms'])
    if args['names'] != names or not names_valid(args['names']):
        raise ValueError('numeric inline INPUT names must match its canonical term expansion')
    if args['delimiter'] == ',':
        if type(args['infile_line']) is not int or not step['line'] <= args['infile_line'] <= op['line']:
            raise ValueError('comma INPUT requires preceding inline INFILE source metadata')
    elif args['infile_line'] is not None or args['firstobs'] != 1 or not any('-' in t for t in args['terms']):
        raise ValueError('ordinary range INPUT requires a range trigger without INFILE options')
    shadow = deepcopy(step)
    copied = next(o for o in shadow['operations'] if o['kind'] == 'input_numeric')
    copied.update(kind='input_list', args={'names': names, 'records': [], 'data_line': args['data_line']})
    from .input_list import validate_step as validate_legacy
    from .runtime import validate_inline_types
    validate_legacy(shadow, version)
    allowed_args = {'declare': ({'name', 'spec'},), 'projection': ({'mode', 'names', 'scope'},),
                    'input_list': ({'names', 'records', 'data_line'},),
                    'assign': ({'name', 'value'},), 'round': ({'name', 'value', 'unit'},),
                    'sum_statement': ({'name', 'value'},),
                    'if': ({'condition', 'operation'}, {'condition', 'operation', 'otherwise'}),
                    'subset': ({'condition'},), 'put': ({'names'},),
                    'put_literal': ({'literals'},), 'put_numeric_list': ({'names'}, {'names', 'discover'}),
                    'put_mixed_numeric': ({'items'},), 'output': ({'target'},)}
    for action in walk_operations(shadow['operations'], all_containers=True):
        if set(action['args']) not in allowed_args[action['kind']]:
            raise ValueError('numeric inline scalar action has unexpected arguments')
    from .projection import validate_step as validate_projection
    validate_projection(shadow, version)
    validate_inline_types(list(walk_operations(shadow['operations'])), None, shadow.get('retained', {}))
    values = decode(args['records'], len(names), args['delimiter'], args['firstobs'])
    return [dict(zip(names, row)) for row in values]
