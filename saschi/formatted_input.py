"""DS-071/072 finite job-local numeric informats and physical pointer INPUT.

Repository bounds are explicit. This module does not implement a SAS catalog,
invalid-data recovery, FLOWOVER, arbitrary informats or general INPUT syntax.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import re

from sas_semantics import sas_input_number

DEFINITION_KIND = 'informat_definition'
DEFINITION_OPERATION = 'numeric_invalue'
DEFINITION_PROFILE = 'numeric-invalue-literals-v1'
DATA_KIND = 'formatted_data'
DATA_OPERATION = 'formatted_input'
DATA_PROFILE = 'formatted-records-v1'
KINDS = frozenset((DEFINITION_KIND, DEFINITION_OPERATION, DATA_KIND, DATA_OPERATION))
PROFILES = frozenset((DEFINITION_PROFILE, DATA_PROFILE))
STEP_KEYS = frozenset(('kind', 'name', 'line', 'inputs', 'by', 'operations',
                       'nodupkey', 'where', 'retained', 'lengths', 'display_names'))
SOURCE_NAME = r'[A-Za-z_][A-Za-z0-9_]{0,31}'
NAME = re.compile(r'[a-z_][a-z0-9_]{0,31}\Z', re.ASCII)
RESERVED = frozenset(('_null_', '_n_', '_error_', '_all_', '_numeric_', '_character_',
                      '_temporary_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_'))


def ordinary(name):
    return type(name) is str and NAME.fullmatch(name) is not None and name not in RESERVED


def custom_name(name):
    return (ordinary(name) and len(name) <= 31 and not name[-1].isdigit()
            and (name == 'eval' or name.startswith('usr_')))


def refuse_legacy(value):
    """Reject hidden new shapes, with linear work for shared container DAGs."""
    pending = [(value, False)]
    active, completed = set(), set()
    while pending:
        item, leaving = pending.pop()
        if type(item) not in (dict, list, tuple):
            continue
        identity = id(item)
        if leaving:
            active.remove(identity)
            completed.add(identity)
            continue
        if identity in completed:
            continue
        if identity in active:
            raise ValueError('cyclic portable containers are invalid')
        active.add(identity)
        pending.append((item, True))
        if type(item) is dict:
            kind, profile = item.get('kind'), item.get('profile')
            if ((type(kind) is str and kind in KINDS)
                    or (type(profile) is str and profile in PROFILES)):
                raise ValueError('formatted INPUT requires its explicit new Step family')
            children = item.values()
        else:
            children = item
        pending.extend((child, False) for child in children if type(child) in (dict, list, tuple))


def _base(step, kind, operation, version):
    if (type(version) is not int or version != 2 or type(step) is not dict
            or set(step) != STEP_KEYS or step.get('kind') != kind
            or not ordinary(step.get('name')) or type(step.get('line')) is not int or step['line'] < 1
            or type(step.get('inputs')) is not list or step['inputs']
            or type(step.get('by')) is not list or step['by'] or step.get('nodupkey') is not False
            or step.get('where') is not None
            or any(type(step.get(key)) is not dict or step[key]
                   for key in ('retained', 'lengths', 'display_names'))
            or type(step.get('operations')) is not list or len(step['operations']) != 1):
        raise ValueError('formatted INPUT requires exact version2 Step defaults')
    op = step['operations'][0]
    if (type(op) is not dict or set(op) != {'kind', 'line', 'args'} or op.get('kind') != operation
            or type(op.get('line')) is not int or op['line'] < step['line']
            or type(op.get('args')) is not dict):
        raise ValueError('formatted INPUT requires one exact operation')
    return op


def _entries(entries):
    if type(entries) is not list or not 1 <= len(entries) <= 32:
        raise ValueError('numeric INVALUE requires1..32 literal entries')
    mapping = {}
    for entry in entries:
        if type(entry) is not dict or set(entry) != {'raw', 'value'}:
            raise ValueError('numeric INVALUE entries require exact raw/value fields')
        raw, value = entry['raw'], entry['value']
        if (type(raw) is not str or not 1 <= len(raw) <= 32 or raw != raw.strip(' ')
                or any(not 32 <= ord(c) <= 126 for c in raw) or any(c in raw for c in "'\"&%")
                or raw in mapping or type(value) is not int or not -1000 <= value <= 1000):
            raise ValueError('numeric INVALUE requires unique bounded exact-case literals and integer results')
        mapping[raw] = value
    return mapping


def validate_definition_step(step, version=2):
    op = _base(step, DEFINITION_KIND, DEFINITION_OPERATION, version)
    args = op['args']
    if set(args) != {'profile', 'entries', 'source_lines'} or args.get('profile') != DEFINITION_PROFILE:
        raise ValueError('numeric INVALUE requires its exact explicit profile')
    lines = args['source_lines']
    if (not custom_name(step['name']) or type(lines) is not list or len(lines) != 2
            or any(type(line) is not int or line < 1 for line in lines)
            or lines != sorted(lines) or lines[0] != op['line']):
        raise ValueError('numeric INVALUE requires a bounded custom name and complete source lines')
    mapping = _entries(args['entries'])
    return {'name': step['name'], 'width': max(map(len, mapping)), 'mapping': deepcopy(mapping),
            'entries': deepcopy(args['entries']), 'source_lines': list(lines)}


def _registry(registry):
    if type(registry) is not dict or len(registry) > 8:
        raise ValueError('numeric INVALUE registry requires at most8 definitions')
    result = {}
    for name, context in registry.items():
        if (not custom_name(name) or type(context) is not dict
                or set(context) != {'name', 'width', 'mapping', 'entries', 'source_lines'}
                or context['name'] != name):
            raise ValueError('numeric INVALUE registry requires validated definition contexts')
        mapping = _entries(context['entries'])
        lines = context['source_lines']
        if (type(context['width']) is not int or context['width'] != max(map(len, mapping))
                or type(context['mapping']) is not dict
                or list(context['mapping'].items()) != list(mapping.items())
                or any(type(value) is not int for value in context['mapping'].values())
                or type(lines) is not list or len(lines) != 2
                or any(type(line) is not int or line < 1 for line in lines) or lines != sorted(lines)):
            raise ValueError('numeric INVALUE registry derived state differs from its literals')
        result[name] = {'name': name, 'width': context['width'], 'mapping': mapping,
                        'entries': deepcopy(context['entries']), 'source_lines': list(lines)}
    return result


def _fields(fields, registry):
    if type(fields) is not list or not 2 <= len(fields) <= 32:
        raise ValueError('formatted INPUT requires2..32 fields including a custom numeric read')
    schema, reads, custom = {}, [], False
    for index, field in enumerate(fields):
        if type(field) is not dict or not ordinary(field.get('name')) or field['name'] in schema:
            raise ValueError('formatted INPUT requires unique ordinary field names')
        name, read = field['name'], field.get('read')
        if index == 0:
            if set(field) != {'name', 'read'} or read != 'list_character':
                raise ValueError('formatted INPUT first field is simple-list character storage8')
            spec = {'type': 'character', 'length': 8}
            reads.append({'name': name, 'read': read})
        else:
            column = field.get('column')
            if type(column) is not int or not 1 <= column <= 80:
                raise ValueError('formatted INPUT requires literal columns1..80')
            if read == 'character' and set(field) == {'name', 'read', 'column', 'width'}:
                width = field['width']
                if type(width) is not int or not 1 <= width <= 32:
                    raise ValueError('formatted character widths require1..32')
                spec = {'type': 'character', 'length': width}
                reads.append(dict(field))
            elif read == 'numeric_informat' and set(field) == {'name', 'read', 'column', 'informat'}:
                informat = field['informat']
                if not custom_name(informat) or informat not in registry:
                    raise ValueError('formatted INPUT requires a prior numeric INVALUE definition')
                width = registry[informat]['width']
                spec = {'type': 'number', 'length': 8}
                reads.append({**field, 'width': width})
                custom = True
            else:
                raise ValueError('formatted INPUT requires exact character or custom numeric fields')
            if column + width - 1 > 80:
                raise ValueError('formatted INPUT fixed spans must fit within80 physical columns')
        schema[name] = spec
    if not custom:
        raise ValueError('formatted INPUT requires an actual custom numeric informat read')
    return schema, reads


def apply_informat(raw, context):
    """Right-padding comparison, then the unchanged exact numeric converter."""
    token = raw.rstrip(' ')
    if not token or token.strip(' ') == '.' or re.fullmatch(r'\.[A-Za-z_]', token.strip(' ')):
        raise ValueError('blank and missing custom-numeric fields are outside this profile')
    if token in context['mapping']:
        return float(context['mapping'][token])
    value = sas_input_number(token.strip(' '))
    if value is None or not value.is_integer() or not -1000 <= value <= 1000:
        raise ValueError('numeric INVALUE fallback requires an exact integer within1000')
    return value


def validate_data_step(step, registry, version=2):
    op = _base(step, DATA_KIND, DATA_OPERATION, version)
    args = op['args']
    if set(args) != {'profile', 'fields', 'records', 'source_lines'} or args.get('profile') != DATA_PROFILE:
        raise ValueError('formatted INPUT requires its exact explicit profile')
    definitions = _registry(registry)
    schema, reads = _fields(args['fields'], definitions)
    lines, records = args['source_lines'], args['records']
    if (type(lines) is not list or len(lines) != 5
            or any(type(line) is not int or line < 1 for line in lines)
            or lines != sorted(lines) or lines[0] != step['line'] or lines[1] != op['line']
            or type(records) is not list or len(records) > 1000
            or lines[3] != lines[2] + len(records) + 1 or lines[4] <= lines[3]):
        raise ValueError('formatted INPUT requires complete physical source provenance')
    rows = []
    for record in records:
        if (type(record) is not str or len(record) > 80
                or any(not 32 <= ord(c) <= 126 for c in record)
                or any(c in record for c in "'\";")):
            raise ValueError('formatted INPUT records require unquoted ASCII without semicolons,at most80 bytes')
        first = re.match(r' *([^ ]+)', record)
        if first is None or len(first[1]) > 8 or first[1] == '.':
            raise ValueError('formatted INPUT first character token requires1..8 bytes')
        token = first[1]
        row = {reads[0]['name']: token.ljust(8)}
        for field in reads[1:]:
            start, width = field['column'] - 1, field['width']
            if start + width > len(record):
                raise ValueError('formatted INPUT refuses incomplete physical spans')
            raw = record[start:start + width]
            if field['read'] == 'character':
                value = raw.lstrip(' ')
                if value.rstrip(' ') == '.':
                    value = ''
                row[field['name']] = value.ljust(width)
            else:
                row[field['name']] = apply_informat(raw, definitions[field['informat']])
        rows.append(row)
    return {'schema': deepcopy(schema), 'rows': rows, 'source_lines': list(lines)}


def execute_data(step, registry, tables=None, version=2, trace=None):
    context = validate_data_step(step, registry, version)
    if tables is None:
        tables = {}
    if (type(tables) is not dict or any(type(name) is not str for name in tables)
            or step['name'] in (name.lower() for name in tables)):
        raise ValueError('formatted INPUT requires a fresh output dataset')
    if trace is not None:
        for index in range(len(context['rows']) + 1):
            complete = index < len(context['rows'])
            trace.append({'kind': 'formatted_input', 'line': step['operations'][0]['line'],
                          'attempt': index + 1, 'complete': complete})
            if complete:
                trace.append({'kind': 'formatted_output', 'line': step['operations'][0]['line'],
                              'observation': index + 1})
    return {'schema': deepcopy(context['schema']), 'rows': deepcopy(context['rows'])}, []


def _texts(block, count):
    if len(block) != count or any(statement.terminated is not True for statement in block):
        raise ValueError('formatted source requires every exact statement and semicolon')
    if any(type(statement.text) is not str or not statement.text.isascii() for statement in block):
        raise ValueError('formatted source requires ASCII before normalization')
    return [statement.text for statement in block]


def compile_definition(block):
    from .plan import Operation, Step
    texts = _texts(block, 3)
    if re.fullmatch(r'proc\s+format', texts[0], re.I | re.ASCII) is None or texts[2].lower() != 'run':
        raise ValueError('numeric INVALUE requires bare PROC FORMAT,one definition and RUN')
    match = re.fullmatch(r'invalue\s+(' + SOURCE_NAME + r')\s+(.+)', texts[1], re.I | re.S | re.ASCII)
    if match is None or not custom_name(match[1].lower()):
        raise ValueError('numeric INVALUE requires eval or a bounded usr_ custom name')
    entries, position = [], 0
    entry = re.compile(r'''\s*(['"])([^'"&%]*)\1\s*=\s*([+-]?[0-9]+)(?=\s|$)''', re.ASCII)
    while position < len(match[2]):
        found = entry.match(match[2], position)
        if found is None:
            raise ValueError('numeric INVALUE supports fully consumed quoted literal/integer pairs only')
        digits = found[3].lstrip('+-').lstrip('0') or '0'
        if len(digits) > 4:
            raise ValueError('numeric INVALUE integer literal is outside the bounded domain')
        value = int(digits) * (-1 if found[3].startswith('-') else 1)
        entries.append({'raw': found[2], 'value': value})
        position = found.end()
        if not match[2][position:].strip():
            break
    step = Step(DEFINITION_KIND, match[1].lower(), block[0].line,
                operations=[Operation(DEFINITION_OPERATION, block[1].line,
                    {'profile': DEFINITION_PROFILE, 'entries': entries,
                     'source_lines': [block[1].line, block[2].line]})])
    validate_definition_step(asdict(step))
    return step


def parse_fields(text):
    if type(text) is not str or not text.isascii():
        raise ValueError('formatted INPUT names require ASCII before normalization')
    first = re.match(r'input\s+(' + SOURCE_NAME + r')\s+\$(?=\s|$)', text, re.I | re.ASCII)
    if first is None:
        raise ValueError('formatted INPUT starts with one simple character name $')
    fields, position = [{'name': first[1].lower(), 'read': 'list_character'}], first.end()
    item = re.compile(r'\s+@\s*([0-9]{1,2})\s+(' + SOURCE_NAME
                      + r')\s+(?:\$\s*([0-9]{1,2})\s*\.|(' + SOURCE_NAME + r')\s*\.)', re.ASCII)
    while position < len(text):
        found = item.match(text, position)
        if found is None:
            raise ValueError('formatted INPUT requires literal absolute pointer before every later field')
        field = {'name': found[2].lower(), 'read': 'character' if found[3] else 'numeric_informat',
                 'column': int(found[1])}
        field['width' if found[3] else 'informat'] = int(found[3]) if found[3] else found[4].lower()
        fields.append(field)
        position = found.end()
        if not text[position:].strip():
            break
    return fields


def compile_data(block, source, registry):
    from .parser import Kind
    from .plan import Operation, Step
    texts = _texts(block, 5)
    header, input_statement, datalines, payload, run = block
    name = re.fullmatch(r'data\s+(' + SOURCE_NAME + r')', texts[0], re.I | re.ASCII)
    if name is None or not ordinary(name[1].lower()) or texts[2].lower() != 'datalines' or texts[4].lower() != 'run':
        raise ValueError('formatted DATA requires named DATA,INPUT,DATALINES,payload,RUN only')
    if len(payload.tokens) != 1 or payload.tokens[0].kind is not Kind.DATA:
        raise ValueError('formatted DATA requires one opaque physical payload')
    raw = payload.tokens[0].text.replace('\r\n', '\n')
    parts = raw.split('\n')
    if len(parts) < 2 or parts[0].strip(' ') or parts[-1] != '':
        raise ValueError('formatted records begin after the DATALINES statement line')
    records = parts[1:-1]
    terminator = datalines.line + raw.count('\n')
    physical = source.splitlines()
    if terminator > len(physical) or physical[terminator - 1] != ';':
        raise ValueError('DATALINES requires an exact standalone unindented semicolon')
    step = Step(DATA_KIND, name[1].lower(), header.line,
                operations=[Operation(DATA_OPERATION, input_statement.line,
                    {'profile': DATA_PROFILE, 'fields': parse_fields(input_statement.text),
                     'records': records, 'source_lines': [header.line, input_statement.line,
                                                        datalines.line, terminator, run.line]})])
    validate_data_step(asdict(step), registry)
    return step
