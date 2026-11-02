"""Additive bounded directed SORT and descriptor-order BY _ALL_ profiles."""
from copy import deepcopy
from dataclasses import asdict
import math
import re

from sas_semantics import sas_input_number, sas_sort_key
from .character_input import STEP_KEYS, ordinary

KIND = 'bounded_sort'
DIRECTED_PROFILE = 'directed-sort-v1'
ALL_PROFILE = 'descriptor-sort-all-v1'
PROFILES = frozenset((DIRECTED_PROFILE, ALL_PROFILE))
SOURCE_NAME = r'[A-Za-z_][A-Za-z0-9_]{0,31}'


def _containers(value, refuse=False):
    """Detect cycles and hidden new markers without recursive legacy limits."""
    active, completed = set(), set()
    pending = [(value, False)]
    while pending:
        node, leaving = pending.pop()
        if type(node) not in (dict, list, tuple):
            continue
        identity = id(node)
        if leaving:
            active.remove(identity)
            completed.add(identity)
            continue
        if identity in active:
            raise ValueError('cyclic portable SORT containers are invalid')
        if identity in completed:
            continue
        if refuse and type(node) is dict:
            if node.get('kind') == KIND or (type(node.get('profile')) is str and node['profile'] in PROFILES):
                raise ValueError('bounded SORT requires its own explicit Step and program family')
        active.add(identity)
        pending.append((node, True))
        pending.extend((child, False) for child in (node.values() if type(node) is dict else node))


def refuse_legacy(value):
    _containers(value, True)


def _schema(schema):
    if type(schema) is not dict or not 1 <= len(schema) <= 32:
        raise ValueError('bounded SORT requires1..32 ordered columns')
    character = False
    for name, spec in schema.items():
        if (not ordinary(name) or type(spec) is not dict or set(spec) != {'type', 'length'}
                or type(spec['type']) is not str or type(spec['length']) is not int):
            raise ValueError('bounded SORT requires ordinary names and exact plain descriptors')
        if spec['type'] == 'character' and 1 <= spec['length'] <= 64:
            character = True
        elif spec['type'] != 'number' or spec['length'] != 8:
            raise ValueError('bounded SORT requires characterwidth1..64 or numericlength8')
    if not character:
        raise ValueError('bounded SORT requires genuine character-data lineage')
    return schema


def _table(table):
    if type(table) is not dict or set(table) != {'schema', 'rows'} or type(table.get('rows')) is not list:
        raise ValueError('bounded SORT requires a plain schema/rows table')
    schema = _schema(table['schema'])
    if len(table['rows']) > 1000:
        raise ValueError('bounded SORT exceeds1000 rows')
    for row in table['rows']:
        if type(row) is not dict or set(row) != set(schema):
            raise ValueError('bounded SORT row must match its entire ordered schema')
        for name, spec in schema.items():
            value = row[name]
            if spec['type'] == 'character':
                if (type(value) is not str or len(value) != spec['length']
                        or any(not 32 <= ord(c) <= 126 for c in value)):
                    raise ValueError('bounded SORT requires exact padded printableASCII characters')
            elif value is not None:
                if type(value) not in (int, float) or abs(value) > 2147483647 or not math.isfinite(value):
                    raise ValueError('bounded SORT numbers require the ordinary exact INPUT domain')
                if sas_input_number(str(value)) != value:
                    raise ValueError('bounded SORT numbers require the unchanged exact INPUT converter')
    return table


def validate_step(step, version=2):
    _containers(step)
    if (type(version) is not int or version != 2 or type(step) is not dict or set(step) != STEP_KEYS
            or step.get('kind') != KIND or not ordinary(step.get('name'))
            or type(step.get('line')) is not int or step['line'] < 1
            or type(step.get('inputs')) is not list or len(step['inputs']) != 1
            or not ordinary(step['inputs'][0]) or step['name'] == step['inputs'][0]
            or type(step.get('by')) is not list or step['by']
            or step.get('nodupkey') is not False or step.get('where') is not None
            or any(type(step.get(key)) is not dict or step[key] for key in ('retained', 'lengths', 'display_names'))
            or type(step.get('operations')) is not list or len(step['operations']) != 1):
        raise ValueError('bounded SORT requires exact version2 Step defaults and fresh explicit OUT')
    operation = step['operations'][0]
    if (type(operation) is not dict or set(operation) != {'kind', 'line', 'args'}
            or operation.get('kind') != KIND or type(operation.get('line')) is not int
            or operation['line'] != step['line'] or type(operation.get('args')) is not dict):
        raise ValueError('bounded SORT requires one same-kind header-line operation')
    args = operation['args']
    if (set(args) != {'profile', 'keys', 'nodupkey', 'source_lines'}
            or type(args.get('profile')) is not str or args['profile'] not in PROFILES
            or type(args.get('keys')) is not list or type(args.get('nodupkey')) is not bool):
        raise ValueError('bounded SORT requires its exact profile and option fields')
    lines = args['source_lines']
    if (type(lines) is not list or len(lines) != 2
            or any(type(line) is not int or line < step['line'] for line in lines)
            or lines != sorted(lines)):
        raise ValueError('bounded SORT requires ordered BY and RUN source lines')
    keys = args['keys']
    if args['profile'] == ALL_PROFILE:
        if keys or args['nodupkey'] is not True:
            raise ValueError('descriptor SORT requires sole BY _ALL_ and NODUPKEY')
    else:
        if not 1 <= len(keys) <= 8:
            raise ValueError('directed SORT requires1..8 unique keys')
        names = []
        for key in keys:
            if (type(key) is not dict or set(key) != {'name', 'descending'}
                    or not ordinary(key.get('name')) or type(key.get('descending')) is not bool):
                raise ValueError('directed SORT requires exact normalized name/direction keys')
            names.append(key['name'])
        if len(names) != len(set(names)) or not any(key['descending'] for key in keys):
            raise ValueError('directed SORT requires distinct keys and at least one DESCENDING')
    return deepcopy(args)


def _sort_context(step, schemas, version=2):
    if type(version) is not int or version != 2 or type(step) is not dict:
        raise ValueError('SORT requires a typed version2 Step')
    if step.get('kind') == KIND:
        context = validate_step(step, version)
        source = step['inputs'][0]
        if source not in schemas or step['name'] in schemas:
            raise ValueError('bounded SORT requires preceding input and fresh OUT lineage')
        schema = _schema(schemas[source])
        keys = context['keys'] if context['profile'] == DIRECTED_PROFILE else [
            {'name': name, 'descending': False} for name in schema]
        if any(key['name'] not in schema for key in keys):
            raise ValueError('bounded SORT BY column is missing from its schema')
        return keys, context['nodupkey']
    if step.get('kind') != 'sort':
        raise ValueError('SORT executor requires bounded_sort or legacy sort')
    refuse_legacy(step)
    from .mixed_reports import _sort_schema
    _sort_schema(step, schemas)
    if len(step['by']) != len(set(step['by'])) or len(step['by']) > 32:
        raise ValueError('legacy SORT retains its distinct ascending BY keys')
    return [{'name': name, 'descending': False} for name in step['by']], step['nodupkey']


def execute_sort(step, tables, version=2, *, trace=None):
    _containers(tables)
    if type(tables) is not dict or any(not ordinary(name) for name in tables):
        raise ValueError('SORT requires an ordinary named table catalog')
    schemas = {name: _table(table)['schema'] for name, table in tables.items()}
    keys, nodupkey = _sort_context(step, schemas, version)
    source = step['inputs'][0]
    table = tables[source]
    ordered = list(range(len(table['rows'])))
    for key in reversed(keys):
        ordered.sort(key=lambda index: sas_sort_key(table['rows'][index][key['name']]),
                     reverse=key['descending'])
    kept = ordered
    if nodupkey:
        kept = []
        previous = None
        for index in ordered:
            current = tuple(sas_sort_key(table['rows'][index][key['name']]) for key in keys)
            if not kept or current != previous:
                kept.append(index)
            previous = current
    result = {'schema': deepcopy(table['schema']), 'rows': [deepcopy(table['rows'][index]) for index in kept]}
    if trace is not None:
        trace.append({'event': 'sort', 'line': step['line'], 'source': source,
                      'destination': step['name'], 'source_ordinals': [index + 1 for index in ordered],
                      'kept_ordinals': [index + 1 for index in kept]})
    return result


def _novel(block):
    from .parser import Kind
    return any(re.match(r'^by\b', statement.text, re.I | re.ASCII)
               and any(token.kind is Kind.WORD and token.text.lower() in ('descending', '_all_')
                       for token in statement.tokens) for statement in block)


def parse_sort(block):
    from .plan import Operation, Step
    if (len(block) != 3 or any(statement.terminated is not True for statement in block)
            or any(not statement.text.isascii() or len(statement.text) > 16384 for statement in block)
            or block[-1].text.lower() != 'run'):
        raise ValueError('SORT requires exact header,BY and explicit RUN statements')
    header = re.fullmatch(r'proc\s+sort\s+data\s*=\s*(' + SOURCE_NAME + r')'
                          r'(?:\s+out\s*=\s*(' + SOURCE_NAME + r'))?(\s+nodupkey)?',
                          block[0].text, re.I | re.ASCII)
    by = re.fullmatch(r'by\s+(.+)', block[1].text, re.I | re.S | re.ASCII)
    if header is None or by is None:
        raise ValueError('SORT permits explicit DATA,OUT,NODUPKEY and one BY list only')
    source, destination = header[1].lower(), (header[2] or header[1]).lower()
    if not ordinary(source) or not ordinary(destination):
        raise ValueError('SORT source and destination require ordinary ASCII names')
    words = by[1].split()
    novel = _novel(block)
    if not novel:
        names = [word.lower() for word in words]
        if (not names or any(not ordinary(name) or name == 'notsorted' for name in names)
                or len(names) != len(set(names))):
            raise ValueError('legacy SORT permits one unique ascending BY list')
        return Step('sort', destination, block[0].line, inputs=[source], by=names, nodupkey=bool(header[3]))
    if header[2] is None:
        raise ValueError('bounded SORT requires an explicit fresh OUT destination')
    if [word.lower() for word in words] == ['_all_']:
        profile, keys = ALL_PROFILE, []
    else:
        profile, keys, position = DIRECTED_PROFILE, [], 0
        while position < len(words):
            descending = words[position].lower() == 'descending'
            position += int(descending)
            if position >= len(words):
                raise ValueError('DESCENDING must immediately precede one BY variable')
            name = words[position].lower()
            if not ordinary(name) or name in ('descending', 'notsorted'):
                raise ValueError('directed SORT requires ordinary distinct BY variable names')
            keys.append({'name': name, 'descending': descending})
            position += 1
    args = {'profile': profile, 'keys': keys, 'nodupkey': bool(header[3]),
            'source_lines': [block[1].line, block[2].line]}
    step = Step(KIND, destination, block[0].line, inputs=[source],
                operations=[Operation(KIND, block[0].line, args)])
    validate_step(asdict(step))
    return step


def source_steps(source, statements):
    """Recognize only genuine prior character producers and actual new BY syntax."""
    from .formatted_program import _blocks
    from .character_input import _parse_block
    from .mixed_reports import parse_print, parse_title
    from .parser import Kind
    steps, failures, routes = [], [], {}
    producer = selected = False
    for start, end, block in _blocks(statements):
        text = block[0].text
        if re.match(r'^proc\s+sort\b', text, re.I | re.ASCII) and producer and _novel(block):
            selected = True
        try:
            if re.match(r'^data(?:\s|$)', text, re.I | re.ASCII):
                step = _parse_block(block, source)
                producer = True
                route = ('character-input', 'DS-069')
            elif re.match(r'^proc\s+sort\b', text, re.I | re.ASCII):
                step = parse_sort(block)
                route = ('sort', 'DS-008') if step.kind == 'sort' else (
                    ('directed-sort', 'DS-073') if step.operations[0].args['profile'] == DIRECTED_PROFILE
                    else ('descriptor-sort-all', 'DS-074'))
            elif re.match(r'^title(?:\s|$)', text, re.I | re.ASCII) and len(block) == 1:
                step, route = parse_title(block[0]), ('logical-title', 'ST-020')
            elif re.match(r'^proc\s+print\b', text, re.I | re.ASCII):
                step, route = parse_print(block), ('mixed-print', 'ST-019')
            else:
                raise ValueError('bounded SORT family permits character DATA,SORT,TITLE and default PRINT only')
            steps.append(step)
            for index in (range(start, start + 1) if step.kind == 'sort' else range(start, end)):
                if not any(token.kind is Kind.DATA for token in statements[index].tokens):
                    routes[index] = route
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            failures.append((block[0].line, text, str(error)))
    return steps, failures, routes, selected


def compile_program(source, legacy):
    from .parser import ParseError, split_statements
    from .plan import Plan, Ticket
    try:
        statements = split_statements(source)
    except ParseError:
        return legacy(source)
    steps, failures, routes, selected = source_steps(source, statements)
    if not selected:
        return legacy(source)
    plan = Plan(steps=steps)
    plan.tickets.extend(Ticket(line, text, 'sort-options', reason) for line, text, reason in failures)
    plan.matched.extend((construct, rule, statements[index].line)
                        for index, (construct, rule) in routes.items())
    try:
        validate_program(plan.to_dict())
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        plan.tickets.append(Ticket(1, 'bounded SORT program', 'sort-options', str(error)))
    return plan


def validate_program(plan, catalog=None):
    _containers(plan)
    if type(plan) is not dict or type(plan.get('steps')) is not list:
        raise ValueError('portable SORT program requires a steps list')
    if not any(type(step) is dict and step.get('kind') == KIND for step in plan['steps']):
        refuse_legacy(plan)
        return None
    if (set(plan) != {'steps', 'tickets', 'matched', 'version'}
            or type(plan.get('version')) is not int or plan['version'] != 2
            or type(plan.get('tickets')) is not list or plan['tickets']
            or type(plan.get('matched')) is not list or len(plan['steps']) > 64):
        raise ValueError('bounded SORT program requires complete version2 and at most64 Steps')
    refuse_legacy(plan['matched'])
    if catalog is not None and (type(catalog) is not dict or catalog):
        raise ValueError('bounded SORT program requires an empty initial catalog')
    from .character_input import validate_step as validate_character
    from .mixed_reports import validate_step as validate_report, _schema as report_schema
    tables, producers, sorts, prints, titles = {}, 0, 0, 0, 0
    for step in plan['steps']:
        if type(step) is not dict or type(step.get('kind')) is not str:
            raise ValueError('bounded SORT family requires typed Steps')
        kind = step['kind']
        if kind != KIND:
            refuse_legacy(step)
        if kind == 'character_data':
            context = validate_character(step, plan['version'])
            if step['name'] in tables:
                raise ValueError('bounded SORT producer requires a fresh destination')
            tables[step['name']] = {'schema': context['schema'], 'rows': context['rows']}
            producers += 1
        elif kind in (KIND, 'sort'):
            if not producers:
                raise ValueError('bounded SORT requires preceding character-data lineage')
            schemas = {name: _table(table)['schema'] for name, table in tables.items()}
            _sort_context(step, schemas, plan['version'])
            # Preflight propagates descriptors and values without executing a SORT.
            # Ordering and duplicate removal cannot introduce new values or rows.
            tables[step['name']] = deepcopy(tables[step['inputs'][0]])
            sorts += kind == KIND
        elif kind in ('report_title', 'mixed_print'):
            context = validate_report(step, plan['version'])
            if kind == 'report_title':
                titles += 1
            else:
                prints += 1
                if context['input'] not in tables:
                    raise ValueError('bounded SORT PRINT requires preceding table lineage')
                report_schema(tables[context['input']]['schema'])
        else:
            raise ValueError('bounded SORT family permits character DATA,SORT,TITLE and default PRINT only')
    if not producers or not sorts or prints > 2 or titles > 32:
        raise ValueError('bounded SORT family requires producer,new SORT,at most2 PRINTs and32 TITLEs')
    return {'sorts': sorts, 'producers': producers, 'prints': prints, 'titles': titles}


def run_program(plan, catalog=None, *, trace=None):
    if validate_program(plan, catalog) is None:
        raise ValueError('bounded SORT executor requires its explicit new family')
    from .character_input import execute_step
    from .mixed_reports import execute_title, execute_print, validate_reports
    tables, reports, logs, title, ordinal = {}, {}, [], None, 0
    for step in plan['steps']:
        kind = step['kind']
        if kind == 'character_data':
            table, messages = execute_step(step, tables, plan['version'], trace=trace)
            tables[step['name']] = table
            logs.extend(messages)
        elif kind in (KIND, 'sort'):
            tables[step['name']] = execute_sort(step, tables, plan['version'], trace=trace)
        elif kind == 'report_title':
            title = execute_title(step, plan['version'], trace=trace)
        else:
            ordinal += 1
            artifacts = execute_print(step, tables, title, ordinal, plan['version'], trace=trace)
            if reports.keys() & artifacts.keys():
                raise ValueError('bounded SORT reports cannot overwrite prior snapshots')
            reports.update(artifacts)
    result = {'datasets': deepcopy(tables), 'log': logs}
    if reports:
        validate_reports(reports)
        result['reports'] = reports
    return result
