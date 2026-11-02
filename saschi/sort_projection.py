"""Bounded PROC SORT input KEEP with separate source and portable admission."""
from copy import deepcopy
from dataclasses import asdict
import re

from sas_semantics import sas_sort_key
from .character_input import STEP_KEYS, SOURCE_NAME, ordinary
from . import sort_options as existing

KIND = 'projected_sort'
PROFILE = 'sort-input-keep-v1'


def _containers(value, refuse=False):
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
            raise ValueError('cyclic projected SORT containers are invalid')
        if identity in completed:
            continue
        if refuse and type(node) is dict and (node.get('kind') == KIND or node.get('profile') == PROFILE):
            raise ValueError('input KEEP requires its own projected_sort Step and program family')
        active.add(identity)
        pending.append((node, True))
        pending.extend((child, False) for child in (node.values() if type(node) is dict else node))


def refuse_legacy(value):
    _containers(value, True)


def _names(value, maximum):
    return (type(value) is list and 1 <= len(value) <= maximum
            and all(ordinary(name) for name in value) and len(set(value)) == len(value))


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
        raise ValueError('input KEEP requires exact version2 Step defaults and fresh explicit OUT')
    operation = step['operations'][0]
    if (type(operation) is not dict or set(operation) != {'kind', 'line', 'args'}
            or operation.get('kind') != KIND or type(operation.get('line')) is not int
            or operation['line'] != step['line'] or type(operation.get('args')) is not dict):
        raise ValueError('input KEEP requires one same-kind header-line operation')
    args = operation['args']
    if (set(args) != {'profile', 'keep', 'by', 'nodupkey', 'source_lines'}
            or type(args.get('profile')) is not str or args['profile'] != PROFILE
            or not _names(args.get('keep'), 32) or not _names(args.get('by'), 8)
            or type(args.get('nodupkey')) is not bool):
        raise ValueError('input KEEP requires its exact profile, unique literal KEEP/BY lists and boolean option')
    lines = args['source_lines']
    if (type(lines) is not list or len(lines) != 2
            or any(type(line) is not int or line < step['line'] for line in lines)
            or lines != sorted(lines)):
        raise ValueError('input KEEP requires ordered BY and RUN source lines')
    return deepcopy(args)


def _context(step, schemas, version=2):
    args = validate_step(step, version)
    source = step['inputs'][0]
    if source not in schemas or step['name'] in schemas:
        raise ValueError('input KEEP requires prior input and fresh OUT lineage')
    schema = existing._schema(schemas[source])
    if any(name not in schema for name in args['keep']):
        raise ValueError('input KEEP column is absent from the complete schema')
    selected = {name: deepcopy(spec) for name, spec in schema.items() if name in args['keep']}
    existing._schema(selected)
    if any(name not in selected for name in args['by']):
        raise ValueError('input KEEP removes a required BY column')
    return args, selected


def _project(table, schema):
    return {'schema': deepcopy(schema),
            'rows': [{name: deepcopy(row[name]) for name in schema} for row in table['rows']]}


def execute_sort(step, tables, version=2, *, trace=None):
    _containers(tables)
    if type(tables) is not dict or any(not ordinary(name) for name in tables):
        raise ValueError('input KEEP requires an ordinary named table catalog')
    schemas = {name: existing._table(table)['schema'] for name, table in tables.items()}
    if type(step) is dict and step.get('kind') == 'sort':
        refuse_legacy(step)
        if step.get('name') in schemas:
            raise ValueError('input KEEP family SORT requires a fresh OUT destination')
        return existing.execute_sort(step, tables, version, trace=trace)
    args, schema = _context(step, schemas, version)
    source = step['inputs'][0]
    table = _project(tables[source], schema)
    ordered = sorted(range(len(table['rows'])),
                     key=lambda index: tuple(sas_sort_key(table['rows'][index][name]) for name in args['by']))
    kept, previous = [], None
    for index in ordered:
        key = tuple(sas_sort_key(table['rows'][index][name]) for name in args['by'])
        if not args['nodupkey'] or not kept or key != previous:
            kept.append(index)
        previous = key
    result = {'schema': deepcopy(schema), 'rows': [deepcopy(table['rows'][index]) for index in kept]}
    if trace is not None:
        trace.append({'event': 'sort', 'line': step['line'], 'source': source,
                      'destination': step['name'], 'source_ordinals': [index + 1 for index in ordered],
                      'kept_ordinals': [index + 1 for index in kept]})
    return result


def _selected(block):
    return re.match(r'^proc\s+sort\s+data\s*=\s*' + SOURCE_NAME + r'\s*\(\s*keep\b',
                    block[0].text, re.I | re.ASCII) is not None


def parse_sort(block):
    from .plan import Operation, Step
    if (len(block) != 3 or any(statement.terminated is not True for statement in block)
            or any(not statement.text.isascii() or len(statement.text) > 16384 for statement in block)
            or block[-1].text.lower() != 'run'):
        raise ValueError('input KEEP SORT requires header,BY and explicit RUN')
    header = re.fullmatch(r'proc\s+sort\s+data\s*=\s*(' + SOURCE_NAME + r')\s*'
                          r'\(\s*keep\s*=\s*([^()]+)\)\s+out\s*=\s*(' + SOURCE_NAME + r')'
                          r'(\s+nodupkey)?', block[0].text, re.I | re.ASCII)
    by = re.fullmatch(r'by\s+(.+)', block[1].text, re.I | re.S | re.ASCII)
    if header is None or by is None:
        raise ValueError('input KEEP permits one literal input option, fresh OUT, optional NODUPKEY and ascending BY')
    keep, keys = header[2].lower().split(), by[1].lower().split()
    if (not _names(keep, 32) or not _names(keys, 8)
            or any(name in ('descending', 'notsorted') for name in keys)):
        raise ValueError('input KEEP permits literal distinct names and an ascending BY list only')
    step = Step(KIND, header[3].lower(), block[0].line, inputs=[header[1].lower()])
    args = {'profile': PROFILE, 'keep': keep, 'by': keys, 'nodupkey': bool(header[4]),
            'source_lines': [block[1].line, block[2].line]}
    step.operations = [Operation(KIND, block[0].line, args)]
    validate_step(asdict(step))
    return step


def source_steps(source, statements):
    from .formatted_program import _blocks
    from .character_input import _parse_block
    from .mixed_reports import parse_print, parse_title
    from .parser import Kind
    steps, failures, routes = [], [], {}
    producer = selected = False
    for start, end, block in _blocks(statements):
        text = block[0].text
        projected = _selected(block)
        if projected and producer:
            selected = True
        try:
            if re.match(r'^data(?:\s|$)', text, re.I | re.ASCII):
                step = _parse_block(block, source)
                producer, route = True, ('character-input', 'DS-069')
            elif re.match(r'^proc\s+sort\b', text, re.I | re.ASCII):
                step = parse_sort(block) if projected else existing.parse_sort(block)
                if step.kind != KIND and step.kind != 'sort':
                    raise ValueError('input KEEP composition with directed/ALL SORT is deferred')
                route = ('sort-input-keep', 'DS-075') if projected else ('sort', 'DS-008')
            elif re.match(r'^title(?:\s|$)', text, re.I | re.ASCII) and len(block) == 1:
                step, route = parse_title(block[0]), ('logical-title', 'ST-020')
            elif re.match(r'^proc\s+print\b', text, re.I | re.ASCII):
                step, route = parse_print(block), ('mixed-print', 'ST-019')
            else:
                raise ValueError('input KEEP family permits character DATA,SORT,TITLE and default PRINT only')
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
    plan.tickets.extend(Ticket(line, text, 'sort-input-keep', reason) for line, text, reason in failures)
    plan.matched.extend((construct, rule, statements[index].line)
                        for index, (construct, rule) in routes.items())
    try:
        validate_program(plan.to_dict())
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        plan.tickets.append(Ticket(1, 'input KEEP SORT program', 'sort-input-keep', str(error)))
    return plan


def validate_program(plan, catalog=None):
    _containers(plan)
    if type(plan) is not dict or type(plan.get('steps')) is not list:
        raise ValueError('input KEEP program requires a steps list')
    if not any(type(step) is dict and step.get('kind') == KIND for step in plan['steps']):
        refuse_legacy(plan)
        return None
    if (set(plan) != {'steps', 'tickets', 'matched', 'version'}
            or type(plan.get('version')) is not int or plan['version'] != 2
            or type(plan.get('tickets')) is not list or plan['tickets']
            or type(plan.get('matched')) is not list or len(plan['steps']) > 64):
        raise ValueError('input KEEP requires complete version2 and at most64 Steps')
    refuse_legacy(plan['matched'])
    existing.refuse_legacy(plan)
    if catalog is not None and (type(catalog) is not dict or catalog):
        raise ValueError('input KEEP program requires an empty initial catalog')
    from .character_input import validate_step as validate_character
    from .mixed_reports import validate_step as validate_report, _schema as report_schema
    tables, producers, sorts, prints, titles = {}, 0, 0, 0, 0
    for step in plan['steps']:
        if type(step) is not dict or type(step.get('kind')) is not str:
            raise ValueError('input KEEP requires typed Steps')
        kind = step['kind']
        if kind != KIND:
            refuse_legacy(step)
        if kind == 'character_data':
            context = validate_character(step, plan['version'])
            if step['name'] in tables:
                raise ValueError('input KEEP producer requires a fresh destination')
            tables[step['name']] = {'schema': context['schema'], 'rows': context['rows']}
            producers += 1
        elif kind in (KIND, 'sort'):
            if not producers:
                raise ValueError('input KEEP requires preceding character-data lineage')
            schemas = {name: existing._table(table)['schema'] for name, table in tables.items()}
            if kind == KIND:
                _, schema = _context(step, schemas, plan['version'])
                tables[step['name']] = _project(tables[step['inputs'][0]], schema)
                sorts += 1
            else:
                if step.get('name') in schemas:
                    raise ValueError('input KEEP family SORT requires a fresh OUT destination')
                existing._sort_context(step, schemas, plan['version'])
                tables[step['name']] = deepcopy(tables[step['inputs'][0]])
        elif kind in ('report_title', 'mixed_print'):
            context = validate_report(step, plan['version'])
            if kind == 'report_title':
                titles += 1
            else:
                prints += 1
                if context['input'] not in tables:
                    raise ValueError('input KEEP PRINT requires prior table lineage')
                report_schema(tables[context['input']]['schema'])
        else:
            raise ValueError('input KEEP permits character DATA,SORT,TITLE and default PRINT only')
    if not producers or not sorts or prints > 2 or titles > 32:
        raise ValueError('input KEEP requires producer,new SORT,at most2 PRINTs and32 TITLEs')
    return {'sorts': sorts, 'producers': producers, 'prints': prints, 'titles': titles}


def run_program(plan, catalog=None, *, trace=None):
    if validate_program(plan, catalog) is None:
        raise ValueError('input KEEP executor requires its explicit new family')
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
                raise ValueError('input KEEP reports cannot overwrite earlier snapshots')
            reports.update(artifacts)
    result = {'datasets': deepcopy(tables), 'log': logs}
    if reports:
        validate_reports(reports)
        result['reports'] = reports
    return result
