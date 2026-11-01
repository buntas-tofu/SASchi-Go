"""DS-069 strict unquoted inline character/numeric physical records."""
from __future__ import annotations

from copy import deepcopy
import re

from sas_semantics import sas_input_number
from .values import coerce

PROFILE = 'character-records-v1'
KIND = 'character_data'
OPERATION = 'character_input'
STEP_KEYS = frozenset(('kind', 'name', 'line', 'inputs', 'by', 'operations',
                       'nodupkey', 'where', 'retained', 'lengths', 'display_names'))
NAME = re.compile(r'[a-z_][a-z0-9_]{0,31}\Z', re.ASCII)
SOURCE_NAME = r'[A-Za-z_][A-Za-z0-9_]{0,31}'
RESERVED = frozenset(('_null_', '_n_', '_error_', '_all_', '_numeric_', '_character_',
                      '_temporary_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_'))


def ordinary(name):
    return type(name) is str and NAME.fullmatch(name) is not None and name not in RESERVED


def refuse_legacy(value):
    """Reject hidden new operations in old shapes without recursive traversal."""
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
            if (item.get('kind') == KIND or item.get('kind') == OPERATION or
                    item.get('profile') == PROFILE):
                raise ValueError('character input requires its explicit character_data Step')
            children = item.values()
        else:
            children = item
        pending.extend((child, False) for child in children if type(child) in (dict, list, tuple))


def _columns(columns):
    if type(columns) is not list or not 1 <= len(columns) <= 32:
        raise ValueError('character INPUT requires1..32 ordered column declarations')
    schema = {}
    character = False
    for column in columns:
        if (type(column) is not dict or set(column) != {'name', 'type', 'length'} or
                not ordinary(column.get('name')) or column['name'] in schema or
                type(column.get('type')) is not str or type(column.get('length')) is not int):
            raise ValueError('character INPUT columns require exact unique ordinary declarations')
        kind, width = column['type'], column['length']
        if kind == 'character':
            if not 1 <= width <= 64:
                raise ValueError('character INPUT widths require1..64 bytes')
            character = True
        elif kind != 'number' or width != 8:
            raise ValueError('character INPUT numeric descriptors require length8')
        schema[column['name']] = {'type': kind, 'length': width}
    if not character:
        raise ValueError('character input profile requires an actual character declaration')
    return schema


def _decode(records, schema):
    if type(records) is not list or len(records) > 1000:
        raise ValueError('character INPUT permits0..1000 physical records')
    rows = []
    for record in records:
        if (type(record) is not str or len(record) > 80 or
                any(not 32 <= ord(c) <= 126 for c in record) or '"' in record or "'" in record):
            raise ValueError('character INPUT requires unquoted printableASCII records of atmost80 bytes')
        fields = record.split(',')
        if len(fields) != len(schema):
            raise ValueError('character INPUT requires exactly one complete field set per physical record')
        row = {}
        for (name, spec), field in zip(schema.items(), fields):
            value = field.strip(' ')
            if spec['type'] == 'character':
                if value == '.' or len(value) > spec['length']:
                    raise ValueError('character INPUT refuses period tokens and overwidth values')
                row[name] = coerce(value, spec, 'ascii')
            else:
                row[name] = None if value == '' else sas_input_number(value)
        rows.append(row)
    return rows


def validate_step(step, version=2):
    """Validate the complete new portable contract before any empty-row shortcut."""
    if (type(version) is not int or version != 2 or type(step) is not dict or
            set(step) != STEP_KEYS or step.get('kind') != KIND or
            not ordinary(step.get('name')) or type(step.get('line')) is not int or step['line'] < 1 or
            type(step.get('inputs')) is not list or step['inputs'] != [] or
            type(step.get('by')) is not list or step['by'] != [] or
            step.get('nodupkey') is not False or step.get('where') is not None or
            any(type(step.get(key)) is not dict or step[key] != {}
                for key in ('retained', 'lengths', 'display_names')) or
            type(step.get('operations')) is not list or len(step['operations']) != 1):
        raise ValueError('character INPUT requires its exact version2 Step defaults')
    operation = step['operations'][0]
    if (type(operation) is not dict or set(operation) != {'kind', 'line', 'args'} or
            operation.get('kind') != OPERATION or type(operation.get('line')) is not int or
            type(operation.get('args')) is not dict):
        raise ValueError('character INPUT requires one explicit input operation')
    args = operation['args']
    if set(args) != {'profile', 'columns', 'records', 'source_lines'} or args.get('profile') != PROFILE:
        raise ValueError('character INPUT requires character-records-v1 and exact operation fields')
    schema = _columns(args['columns'])
    lines = args['source_lines']
    if (type(lines) is not list or len(lines) != 6 or
            any(type(line) is not int or line < 1 for line in lines) or
            lines != sorted(lines) or lines[0] != step['line'] or lines[2] != operation['line'] or
            type(args['records']) is not list or lines[4] != lines[3] + len(args['records']) + 1 or
            lines[5] <= lines[4]):
        raise ValueError('character INPUT requires complete physical source line provenance')
    return {'schema': schema, 'rows': _decode(args['records'], schema), 'source_lines': list(lines)}


def execute_step(step, tables=None, version=2, *, trace=None):
    context = validate_step(step, version)
    if tables is None:
        tables = {}
    if (type(tables) is not dict or any(type(name) is not str for name in tables) or
            step['name'] in (name.lower() for name in tables)):
        raise ValueError('character INPUT requires a fresh output destination')
    if trace is not None:
        for index in range(len(context['rows']) + 1):
            complete = index < len(context['rows'])
            trace.append({'kind': 'character_input', 'line': step['operations'][0]['line'],
                          'attempt': index + 1, 'complete': complete})
            if complete:
                trace.append({'kind': 'character_output', 'line': step['operations'][0]['line'],
                              'observation': index + 1})
    return {'schema': deepcopy(context['schema']), 'rows': deepcopy(context['rows'])}, []


def parse_columns(text):
    if type(text) is not str or not text.isascii():
        raise ValueError('character INPUT names requireASCII before case normalization')
    match = re.fullmatch(r'input\s+(.+)', text, re.I | re.S | re.ASCII)
    if match is None:
        raise ValueError('one nonempty INPUT declaration is required')
    rest, columns = match[1], []
    item = re.compile(r'\s*(' + SOURCE_NAME + r')(?:\s*:\s*\$\s*([0-9]{1,2})\s*\.)?(?=\s|$)', re.ASCII)
    position = 0
    while position < len(rest):
        found = item.match(rest, position)
        if found is None:
            raise ValueError('INPUT permits ordinary numeric names and character colon:$w. only')
        width = found[2]
        columns.append({'name': found[1].lower(), 'type': 'character' if width else 'number',
                        'length': int(width) if width else 8})
        position = found.end()
        if rest[position:].strip() == '':
            break
    _columns(columns)
    return columns


def _parse_block(block, source):
    from .parser import Kind
    from .plan import Operation, Step
    if len(block) != 6 or not all(statement.terminated for statement in block):
        raise ValueError('character DATA requires only DATA,INFILE,INPUT,DATALINES4,payload,RUN')
    header, infile, input_statement, datalines, payload, run = block
    name = re.fullmatch(r'data\s+(' + SOURCE_NAME + r')', header.text, re.I | re.ASCII)
    if name is None or not ordinary(name[1].lower()):
        raise ValueError('character INPUT requires a fresh ordinary named DATA destination')
    if re.fullmatch(r'infile\s+datalines\s+dsd', infile.text, re.I | re.ASCII) is None:
        raise ValueError('character INPUT requires exactly INFILE DATALINES DSD')
    columns = parse_columns(input_statement.text)
    if datalines.text.lower() != 'datalines4' or run.text.lower() != 'run':
        raise ValueError('character INPUT requires DATALINES4 and explicit RUN')
    if len(payload.tokens) != 1 or payload.tokens[0].kind is not Kind.DATA:
        raise ValueError('character INPUT requires one opaque physical payload')
    raw = payload.tokens[0].text.replace('\r\n', '\n')
    parts = raw.split('\n')
    if not parts or parts[0].strip(' ') != '' or len(parts) < 2 or parts[-1] != '':
        raise ValueError('character records begin after the DATALINES4 statement line')
    records = parts[1:-1]
    terminator_line = datalines.line + raw.count('\n')
    physical = source.splitlines()
    if terminator_line > len(physical) or physical[terminator_line - 1] != ';;;;':
        raise ValueError('DATALINES4 requires exact unindented standalone four semicolons')
    lines = [header.line, infile.line, input_statement.line, datalines.line, terminator_line, run.line]
    operation = Operation(OPERATION, input_statement.line,
                          {'profile': PROFILE, 'columns': columns, 'records': records, 'source_lines': lines})
    step = Step(KIND, name[1].lower(), header.line, operations=[operation])
    from dataclasses import asdict
    validate_step(asdict(step))
    return step


def compile_program(source, legacy):
    """Compile actual new DATA blocks, delegating untouched source with line offsets."""
    from .parser import Kind, ParseError, split_statements
    from .plan import Plan, Ticket
    try:
        statements = split_statements(source)
    except ParseError:
        return None
    blocks, position = [], 0
    while position < len(statements):
        statement = statements[position]
        if (any(token.kind is Kind.DATA for token in statement.tokens) or
                re.match(r'^data\s', statement.text, re.I | re.ASCII) is None):
            position += 1
            continue
        end = position + 1
        while end < len(statements) and statements[end].text.lower() != 'run':
            if (not any(token.kind is Kind.DATA for token in statements[end].tokens) and
                    re.match(r'^(?:data|proc)\s', statements[end].text, re.I | re.ASCII)):
                break
            end += 1
        limit = end + 1 if end < len(statements) and statements[end].text.lower() == 'run' else end
        block = statements[position:limit]
        new = any(not any(token.kind is Kind.DATA for token in item.tokens) and
                  (item.text.lower() == 'datalines4' or
                   re.match(r'^infile\s+datalines\s+dsd\b', item.text, re.I | re.ASCII) or
                   re.match(r'^input\s.*:\s*\$', item.text, re.I | re.S | re.ASCII)) for item in block)
        if new:
            start = statement.tokens[0].start
            stop = statements[limit].tokens[0].start if limit < len(statements) else len(source)
            if start is None or stop is None:
                return None
            blocks.append((start, stop, block))
        position = max(position + 1, limit)
    if not blocks:
        return None
    plan, cursor = Plan(), 0
    def preceding(start, stop):
        if source[start:stop].strip():
            compiled = legacy('\n' * source[:start].count('\n') + source[start:stop])
            plan.steps.extend(compiled.steps)
            plan.tickets.extend(compiled.tickets)
            plan.matched.extend(compiled.matched)
    for start, stop, block in blocks:
        preceding(cursor, start)
        try:
            plan.steps.append(_parse_block(block, source))
            plan.matched.extend(('character-input', 'DS-069', item.line) for item in block
                                if not any(token.kind is Kind.DATA for token in item.tokens))
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            plan.tickets.append(Ticket(block[0].line, block[0].text, 'character-input', str(exc)))
        cursor = stop
    preceding(cursor, len(source))
    for step in plan.steps:
        if step.kind not in (KIND, 'sort'):
            plan.tickets.append(Ticket(step.line, step.kind, 'character-input',
                                       'character input programs compose with existing SORT only'))
    return plan
