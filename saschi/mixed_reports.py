"""Separate bounded mixed PRINT and literal TITLE logical-report policies."""
from copy import deepcopy
import json
import math
import re

from sas_semantics import sas_put_numeric_list
from .procedures import STEP_KEYS, ordinary

TITLE_PROFILE = 'logical-title-v1'
PRINT_PROFILE = 'mixed-print-v1'
REPORT_CONTRACT = 'ascii-titled-mixed-integer-v1'
KINDS = frozenset(('report_title', 'mixed_print'))
MAX_ROWS = 1000
MAX_COLUMNS = 32
MAX_STEPS = 64
MAX_TITLES = 32
MAX_PRINTS = 2
MAX_REPORT_BYTES = 417056
MAX_HEADER_BYTES = 1055
MAX_ROW_BYTES = 415
MAX_INTEGER = 2147483647


def _title(value):
    if value is not None and (type(value) is not str or not 1 <= len(value) <= 128
            or any(not 32 <= ord(c) <= 126 for c in value) or not value.strip(' ')
            or '&' in value or '%' in value):
        raise ValueError('TITLE requires reset or1..128 nonmacro printableASCII characters with a nonspace')
    return value


def validate_step(step, version=2):
    """Validate the new shapes without relying on compiler or input row counts."""
    if (type(version) is not int or version != 2 or type(step) is not dict
            or set(step) != STEP_KEYS or type(step.get('kind')) is not str or step['kind'] not in KINDS
            or type(step.get('line')) is not int or step['line'] < 1
            or type(step.get('inputs')) is not list or type(step.get('by')) is not list or step['by']
            or step.get('nodupkey') is not False or step.get('where') is not None
            or any(type(step.get(key)) is not dict or step[key] for key in ('retained','lengths','display_names'))
            or type(step.get('operations')) is not list or len(step['operations']) != 1):
        raise ValueError('mixed report requires exact version2 Step defaults')
    operation = step['operations'][0]
    if (type(operation) is not dict or set(operation) != {'kind','line','args'}
            or operation.get('kind') != step['kind'] or type(operation.get('line')) is not int
            or operation['line'] != step['line'] or type(operation.get('args')) is not dict):
        raise ValueError('mixed report requires one same-kind header-line operation')
    args = operation['args']
    if step['kind'] == 'report_title':
        if (step['name'] != '_null_' or step['inputs'] or set(args) != {'profile','text'}
                or args.get('profile') != TITLE_PROFILE):
            raise ValueError('TITLE requires logical-title-v1 and its exact reset/literal shape')
        return {'kind':'report_title','text':_title(args['text'])}
    lines = args.get('source_lines')
    if (not ordinary(step.get('name')) or step['inputs'] != [step['name']]
            or set(args) != {'profile','source_lines'} or args.get('profile') != PRINT_PROFILE
            or type(lines) is not list or len(lines) != 1 or type(lines[0]) is not int
            or lines[0] < step['line']):
        raise ValueError('mixed PRINT requires default columns,one input and explicit RUN provenance')
    return {'kind':'mixed_print','input':step['name']}


def refuse_legacy(value):
    """Cycle-aware hidden-op detection without imposing new legacy resource caps."""
    active = set()
    completed = set()
    pending = [(value,False)]
    while pending:
        node, leaving = pending.pop()
        if type(node) not in (dict,list,tuple):
            continue
        identity = id(node)
        if leaving:
            active.remove(identity)
            completed.add(identity)
            continue
        if identity in active:
            raise ValueError('cyclic portable mixed-report structure')
        if identity in completed:
            continue
        if type(node) is dict:
            kind = node.get('kind')
            if type(kind) is str and kind in KINDS:
                raise ValueError('mixed report operations require their own new Step kinds')
            profile = node.get('profile')
            if type(profile) is str and profile in (TITLE_PROFILE,PRINT_PROFILE):
                raise ValueError('mixed report profiles cannot hide inside legacy structures')
        active.add(identity)
        pending.append((node,True))
        pending.extend((child,False) for child in (node.values() if type(node) is dict else node))


def _schema(schema):
    if type(schema) is not dict or not 1 <= len(schema) <= MAX_COLUMNS:
        raise ValueError('mixed PRINT requires1..32 ordered columns')
    characters = 0
    for name, spec in schema.items():
        if not ordinary(name) or name == 'obs':
            raise ValueError('mixed PRINT requires ordinary normalized names outside obs')
        if (type(spec) is not dict or set(spec) != {'type','length'} or type(spec['length']) is not int):
            raise ValueError('mixed PRINT requires plain typed length descriptors without labels/formats')
        if spec['type'] == 'character' and 1 <= spec['length'] <= 64:
            characters += 1
        elif spec['type'] != 'number' or spec['length'] != 8:
            raise ValueError('mixed PRINT requires characterswidth1..64 or numericlength8')
    if not characters:
        raise ValueError('mixed PRINT requires at least one character field')
    if len('obs ' + ' '.join(schema)) > MAX_HEADER_BYTES:
        raise ValueError('mixed PRINT header exceeds1055 rendered bytes')
    return schema


def _table(table):
    if type(table) is not dict or set(table) != {'schema','rows'} or type(table.get('rows')) is not list:
        raise ValueError('mixed PRINT requires a plain schema/rows table')
    schema = _schema(table['schema'])
    if len(table['rows']) > MAX_ROWS:
        raise ValueError('mixed PRINT exceeds1000 rows')
    for row in table['rows']:
        if type(row) is not dict or set(row) != set(schema):
            raise ValueError('mixed PRINT row must match its full schema')
        for name, spec in schema.items():
            value = row[name]
            if spec['type'] == 'character':
                if (type(value) is not str or len(value) != spec['length']
                        or any(not 32 <= ord(c) <= 126 for c in value)):
                    raise ValueError('mixed PRINT characters require exact padded printableASCII width')
            elif value is not None and (type(value) not in (int,float) or abs(value) > MAX_INTEGER
                    or not math.isfinite(value) or value != int(value)):
                raise ValueError('mixed PRINT numbers require ordinarymissing or bounded exact integers')
    return table


def _sort_schema(step, schemas):
    if (set(step) != STEP_KEYS or not ordinary(step.get('name'))
            or type(step.get('line')) is not int or step['line'] < 1
            or type(step.get('inputs')) is not list or len(step['inputs']) != 1
            or not ordinary(step['inputs'][0]) or step['inputs'][0] not in schemas
            or type(step.get('by')) is not list or not step['by']
            or any(not ordinary(name) or name not in schemas[step['inputs'][0]] for name in step['by'])
            or type(step.get('nodupkey')) is not bool or step.get('where') is not None
            or type(step.get('operations')) is not list or step['operations']
            or any(type(step.get(key)) is not dict or step[key] for key in ('retained','lengths','display_names'))):
        raise ValueError('mixed report program requires the existing plain ascending SORT shape and lineage')
    return deepcopy(schemas[step['inputs'][0]])


def validate_program(plan, catalog=None):
    """Return new-family context,or None after preserving legacy admission guards."""
    if type(plan) is not dict or type(plan.get('steps')) is not list:
        raise ValueError('portable program requires a steps list')
    selected = any(type(step) is dict and type(step.get('kind')) is str and step['kind'] in (KINDS | {'character_data'})
                   for step in plan['steps'])
    if not selected:
        refuse_legacy(plan)
        return None
    if type(plan.get('version')) is not int or plan['version'] != 2:
        raise ValueError('mixed report program requires exact version2')
    if catalog is not None and (type(catalog) is not dict or catalog):
        raise ValueError('mixed report program requires an empty initial catalog')
    if len(plan['steps']) > MAX_STEPS:
        raise ValueError('mixed report program exceeds64 top-level Steps')
    from .character_input import validate_step as validate_character
    schemas = {}
    producers = printed = titled = 0
    for step in plan['steps']:
        if type(step) is not dict or type(step.get('kind')) is not str:
            raise ValueError('mixed report program requires typed Step objects')
        kind = step['kind']
        if kind == 'character_data':
            context = validate_character(step,plan['version'])
            if step['name'] in schemas:
                raise ValueError('character input requires a fresh destination')
            schemas[step['name']] = deepcopy(context['schema'])
            producers += 1
        elif kind == 'sort':
            schemas[step['name']] = _sort_schema(step,schemas)
        elif kind in KINDS:
            context = validate_step(step,plan['version'])
            if kind == 'report_title':
                titled += 1
            else:
                printed += 1
                if context['input'] not in schemas:
                    raise ValueError('mixed PRINT input requires preceding character-data lineage')
                _schema(schemas[context['input']])
        else:
            refuse_legacy(step)
            raise ValueError('mixed report family permits only character_data,SORT,TITLE and mixed PRINT')
    if not producers or printed > MAX_PRINTS or titled > MAX_TITLES:
        raise ValueError('mixed report family requires a valid character producer,at most2PRINTs and32TITLEs')
    return {'profile':REPORT_CONTRACT,'prints':printed,'titles':titled,'producers':producers}


def execute_title(step, version=2, *, trace=None):
    context = validate_step(step,version)
    if context['kind'] != 'report_title':
        raise ValueError('TITLE executor requires report_title')
    text = context['text']
    if trace is not None:
        trace.append('title|reset' if text is None else 'title|set|' + text.encode('ascii').hex())
    return text


def _validate_text(text):
    if (type(text) is not str or not text.endswith('\n') or len(text) > MAX_REPORT_BYTES
            or any(c != '\n' and not 32 <= ord(c) <= 126 for c in text)):
        raise ValueError('mixed PRINT requires bounded printableASCII LF records')
    records = text[:-1].split('\n')
    if records and records[0].startswith('TITLE: '):
        _title(records[0][7:])
        records = records[1:]
    if not records or not 1 <= len(records) <= MAX_ROWS + 1 or len(records[0]) > MAX_HEADER_BYTES:
        raise ValueError('mixed PRINT exceeds header or row-count limits')
    header = records[0].split(' ')
    if (header[0] != 'obs' or not 2 <= len(header) <= MAX_COLUMNS + 1
            or any(not ordinary(name) or name == 'obs' for name in header[1:])
            or len(set(header[1:])) != len(header[1:])):
        raise ValueError('mixed PRINT requires canonical obs/default-column header')
    for ordinal, record in enumerate(records[1:],1):
        if (not record.startswith(str(ordinal) + ' ') or len(record) > MAX_ROW_BYTES
                or record != record.strip(' ')):
            raise ValueError('mixed PRINT exceeds415 rendered row bytes or observation order')
    return text


def validate_reports(reports):
    names = ['print_01.txt','print_02.txt']
    if (type(reports) is not dict or not 1 <= len(reports) <= 2
            or list(reports) != names[:len(reports)]):
        raise ValueError('mixed PRINT requires ordered print_01/print_02 artifacts')
    for text in reports.values():
        _validate_text(text)
    return reports


def execute_print(step, tables, title=None, ordinal=1, version=2, *, trace=None):
    context = validate_step(step,version)
    if context['kind'] != 'mixed_print' or type(ordinal) is not int or ordinal not in (1,2):
        raise ValueError('mixed PRINT requires its Step and runtime ordinal1or2')
    _title(title)
    source = context['input']
    if type(tables) is not dict or source not in tables:
        raise ValueError('mixed PRINT input dataset is missing')
    # Inspect original cells before generic normalization could coerce bool to1.
    table = _table(tables[source])
    schema = table['schema']
    records = [] if title is None else ['TITLE: ' + title]
    header = 'obs ' + ' '.join(schema)
    records.append(header)
    if trace is not None:
        trace.append('mixed-print|input|' + source + '|' + str(len(table['rows'])))
        if title is not None: trace.append('mixed-print|title|' + records[0].encode('ascii').hex())
        trace.append('mixed-print|header|' + header.encode('ascii').hex())
    for observation, row in enumerate(table['rows'],1):
        fields = [str(observation)]
        for name, spec in schema.items():
            value = row[name]
            fields.append(json.dumps(value.rstrip(' '),ensure_ascii=True) if spec['type'] == 'character'
                          else sas_put_numeric_list([value])[:-1])
        record = ' '.join(fields)
        if len(record) > MAX_ROW_BYTES:
            raise ValueError('mixed PRINT exceeds415 rendered row bytes')
        records.append(record)
        if trace is not None: trace.append('mixed-print|row|' + record.encode('ascii').hex())
    text = _validate_text('\n'.join(records) + '\n')
    name = 'print_' + str(ordinal).zfill(2) + '.txt'
    if trace is not None: trace.append('mixed-print|output|' + name + '|' + str(len(text)))
    return {name:text}


def _name(text):
    if not text.isascii() or not ordinary(text.lower()):
        raise ValueError('mixed report requires an ordinary ASCII name before normalization')
    return text.lower()


def parse_title(statement):
    from .plan import Operation, Step, atom
    if statement.terminated is not True or not statement.text.isascii() or len(statement.text) > 16384:
        raise ValueError('TITLE requires bounded ASCII source and an explicit semicolon')
    matched = re.fullmatch(r'title(?:\s+(.+))?',statement.text,re.I|re.ASCII|re.S)
    if matched is None:
        raise ValueError('TITLE requires reset or one literal')
    value = None
    if matched[1] is not None:
        argument = atom(matched[1])
        if argument is None or argument['kind'] != 'character':
            raise ValueError('TITLE requires exactly one quoted literal')
        value = argument['value']
    _title(value)
    step = Step('report_title','_null_',statement.line)
    step.operations = [Operation(step.kind,step.line,{'profile':TITLE_PROFILE,'text':value})]
    validate_step(step.__dict__ | {'operations':[op.__dict__ for op in step.operations]})
    return step


def parse_print(block):
    from .plan import Operation, Step
    if (len(block) != 2 or any(statement.terminated is not True for statement in block)
            or any(not statement.text.isascii() or len(statement.text) > 16384 for statement in block)
            or block[-1].text.lower() != 'run'):
        raise ValueError('mixed PRINT requires PROC PRINT DATA=name and explicit RUN only')
    match = re.fullmatch(r'proc\s+print\s+data\s*=\s*([A-Za-z_][A-Za-z0-9_]{0,31})',block[0].text,re.I|re.ASCII)
    if match is None:
        raise ValueError('mixed PRINT requires default columns and observation IDs without options')
    name = _name(match[1])
    step = Step('mixed_print',name,block[0].line,inputs=[name])
    step.operations = [Operation(step.kind,step.line,{'profile':PRINT_PROFILE,'source_lines':[block[-1].line]})]
    validate_step(step.__dict__ | {'operations':[op.__dict__ for op in step.operations]})
    return step


def compile_program(source, legacy):
    from .parser import Kind, ParseError, split_statements
    from .plan import Plan, Ticket
    from .character_input import validate_step as validate_character
    baseline = legacy(source)
    producers = [step for step in baseline.steps if step.kind == 'character_data']
    eligible = False
    for step in producers:
        try:
            validate_character(step.__dict__ | {'operations':[op.__dict__ for op in step.operations]})
            eligible = True
        except (ValueError,TypeError,KeyError):
            pass
    if not eligible:
        return baseline
    try:
        statements = split_statements(source)
    except ParseError:
        return baseline
    blocks = []
    position = 0
    active = None
    while position < len(statements):
        statement = statements[position]
        if any(token.kind is Kind.DATA for token in statement.tokens):
            position += 1
            continue
        text = statement.text
        if active is None and re.match(r'^title(?:\s|$)',text,re.I|re.ASCII):
            end = position + 1
        elif active is None and re.match(r'^proc\s+print\b',text,re.I|re.ASCII):
            end = position + 1
            while end < len(statements) and statements[end].text.lower() != 'run':
                if re.match(r'^(?:data|proc)(?:\s|$)',statements[end].text,re.I|re.ASCII):
                    break
                end += 1
            if end < len(statements) and statements[end].text.lower() == 'run':
                end += 1
        else:
            if re.match(r'^(?:data|proc)(?:\s|$)',text,re.I|re.ASCII): active = 'step'
            if text.lower() in ('run','quit'): active = None
            position += 1
            continue
        start = statement.tokens[0].start
        stop = statements[end].tokens[0].start if end < len(statements) else len(source)
        if start is None or stop is None:
            return baseline
        blocks.append((start,stop,statements[position:end]))
        position = end
    if not blocks:
        return baseline
    plan = Plan()
    cursor = 0
    def preceding(start,stop):
        if source[start:stop].strip():
            compiled = legacy('\n' * source[:start].count('\n') + source[start:stop])
            plan.steps.extend(compiled.steps)
            plan.tickets.extend(compiled.tickets)
            plan.matched.extend(compiled.matched)
    for start,stop,block in blocks:
        preceding(cursor,start)
        try:
            step = parse_title(block[0]) if block[0].text.lower().startswith('title') else parse_print(block)
            plan.steps.append(step)
            construct, rule = ('logical-title','ST-020') if step.kind == 'report_title' else ('mixed-print','ST-019')
            plan.matched.extend((construct,rule,statement.line) for statement in block)
        except (ValueError,TypeError,KeyError) as error:
            plan.tickets.append(Ticket(block[0].line,block[0].text,'mixed-report',str(error)))
        cursor = stop
    preceding(cursor,len(source))
    try:
        validate_program(plan.to_dict())
    except (ValueError,TypeError,KeyError,RecursionError) as error:
        plan.tickets.append(Ticket(1,'mixed-report program','mixed-report',str(error)))
    return plan
