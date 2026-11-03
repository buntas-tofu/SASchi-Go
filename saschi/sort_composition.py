"""Bounded input DROP and directed KEEP/DROP with separate admission."""
from copy import deepcopy
from dataclasses import asdict
import re

from .character_input import STEP_KEYS, SOURCE_NAME, ordinary
from . import sort_options as ordering
from . import sort_projection as projection

KIND = 'composed_sort'
PROFILE = 'sort-projection-composition-v1'


def _containers(value, refuse=False):
    projection._containers(value)
    if not refuse:
        return
    pending, visited = [value], set()
    while pending:
        node = pending.pop()
        if type(node) not in (dict, list, tuple) or id(node) in visited:
            continue
        visited.add(id(node))
        if type(node) is dict:
            if node.get('kind') == KIND or node.get('profile') == PROFILE:
                raise ValueError('composed SORT requires its own Step and complete family')
            pending.extend(node.values())
        else:
            pending.extend(node)


def refuse_legacy(value):
    _containers(value, True)


def validate_step(step, version=2):
    _containers(step)
    if (type(version) is not int or version != 2 or type(step) is not dict or set(step) != STEP_KEYS
            or step.get('kind') != KIND or not ordinary(step.get('name'))
            or type(step.get('line')) is not int or step['line'] < 1
            or type(step.get('inputs')) is not list or len(step['inputs']) != 1
            or not ordinary(step['inputs'][0]) or step['name'] == step['inputs'][0]
            or type(step.get('by')) is not list or step['by'] or step.get('nodupkey') is not False
            or step.get('where') is not None
            or any(type(step.get(key)) is not dict or step[key] for key in ('retained', 'lengths', 'display_names'))
            or type(step.get('operations')) is not list or len(step['operations']) != 1):
        raise ValueError('composed SORT requires exact version2 defaults and fresh explicit OUT')
    operation = step['operations'][0]
    if (type(operation) is not dict or set(operation) != {'kind', 'line', 'args'}
            or operation.get('kind') != KIND or type(operation.get('line')) is not int
            or operation['line'] != step['line'] or type(operation.get('args')) is not dict):
        raise ValueError('composed SORT requires one same-kind header-line operation')
    args = operation['args']
    if (set(args) != {'profile', 'selection', 'keys', 'nodupkey', 'source_lines'}
            or type(args.get('profile')) is not str or args['profile'] != PROFILE
            or type(args.get('selection')) is not dict or set(args['selection']) != {'mode', 'names'}
            or type(args['selection'].get('mode')) is not str or args['selection']['mode'] not in ('keep', 'drop')
            or not projection._names(args['selection'].get('names'), 32)
            or type(args.get('keys')) is not list or not 1 <= len(args['keys']) <= 8
            or type(args.get('nodupkey')) is not bool):
        raise ValueError('composed SORT requires exact selection, keys and Boolean NODUPKEY')
    names = []
    for key in args['keys']:
        if (type(key) is not dict or set(key) != {'name', 'descending'}
                or not ordinary(key.get('name')) or type(key.get('descending')) is not bool):
            raise ValueError('composed SORT requires literal unique name/direction keys')
        names.append(key['name'])
    if (len(set(names)) != len(names) or args['selection']['mode'] == 'keep'
            and not any(key['descending'] for key in args['keys'])):
        raise ValueError('composed SORT requires DROP or a directed KEEP, with distinct keys')
    lines = args['source_lines']
    if (type(lines) is not list or len(lines) != 2
            or any(type(line) is not int or line < step['line'] for line in lines)
            or lines != sorted(lines)):
        raise ValueError('composed SORT requires ordered BY and RUN source lines')
    return deepcopy(args)


def _context(step, schemas, version=2):
    args = validate_step(step, version)
    source = step['inputs'][0]
    if source not in schemas or step['name'] in schemas:
        raise ValueError('composed SORT requires prior input and fresh output lineage')
    schema = ordering._schema(schemas[source])
    selection = args['selection']
    if any(name not in schema for name in selection['names']):
        raise ValueError('composed SORT selection names must exist in the full source schema')
    selected = {name: deepcopy(spec) for name, spec in schema.items()
                if (name in selection['names']) == (selection['mode'] == 'keep')}
    ordering._schema(selected)
    if any(key['name'] not in selected for key in args['keys']):
        raise ValueError('composed SORT removes a required BY column')
    return args, selected


def execute_sort(step, tables, version=2, *, trace=None):
    _containers(tables)
    if type(tables) is not dict or any(not ordinary(name) for name in tables):
        raise ValueError('composed SORT requires an ordinary named table catalog')
    schemas = {name: ordering._table(table)['schema'] for name, table in tables.items()}
    if type(step) is not dict:
        raise ValueError('composed SORT requires a typed Step')
    if step.get('kind') != KIND:
        refuse_legacy(step)
        if step.get('name') in schemas:
            raise ValueError('composed SORT joins require a fresh OUT')
        if step.get('kind') == projection.KIND:
            return projection.execute_sort(step, tables, version, trace=trace)
        if step.get('kind') == ordering.KIND:
            context = ordering.validate_step(step, version)
            if context['profile'] != ordering.DIRECTED_PROFILE:
                raise ValueError('BY_ALL joins are outside composed SORT')
        return ordering.execute_sort(step, tables, version, trace=trace)
    args, schema = _context(step, schemas, version)
    source = step['inputs'][0]
    selected = projection._project(tables[source], schema)
    # Reuse the established sort engine after separate projection admission.
    primitive = deepcopy(step)
    if any(key['descending'] for key in args['keys']):
        primitive['kind'] = ordering.KIND
        primitive['operations'][0]['kind'] = ordering.KIND
        primitive['operations'][0]['args'] = {
            'profile': ordering.DIRECTED_PROFILE, 'keys': args['keys'],
            'nodupkey': args['nodupkey'], 'source_lines': args['source_lines']}
    else:
        primitive.update(kind='sort', by=[key['name'] for key in args['keys']],
                         nodupkey=args['nodupkey'], operations=[])
    events = None if trace is None else []
    result = ordering.execute_sort(primitive, {source: selected}, version, trace=events)
    if trace is not None:
        event = events[0]
        trace.append({'event': 'sort_composition', 'line': step['line'], 'source': source,
                      'destination': step['name'], 'selection': args['selection'], 'keys': args['keys'],
                      'source_ordinals': event['source_ordinals'], 'kept_ordinals': event['kept_ordinals']})
    return result


def _selected(block):
    header = re.match(r'^proc\s+sort\s+data\s*=\s*' + SOURCE_NAME + r'\s*\(\s*(keep|drop)\b',
                      block[0].text, re.I | re.ASCII)
    return header is not None and (header[1].lower() == 'drop' or any(
        re.match(r'^by\s', statement.text, re.I | re.ASCII)
        and re.search(r'\bdescending\b', statement.text, re.I | re.ASCII) for statement in block[1:]))


def parse_sort(block):
    from .plan import Operation, Step
    if (len(block) != 3 or any(statement.terminated is not True for statement in block)
            or any(not statement.text.isascii() or len(statement.text) > 16384 for statement in block)
            or block[-1].text.lower() != 'run'):
        raise ValueError('composed SORT requires header,BY and explicit RUN')
    header = re.fullmatch(r'proc\s+sort\s+data\s*=\s*(' + SOURCE_NAME + r')\s*'
                          r'\(\s*(keep|drop)\s*=\s*([^()]+)\)\s+out\s*=\s*(' + SOURCE_NAME + r')'
                          r'(\s+nodupkey)?', block[0].text, re.I | re.ASCII)
    by = re.fullmatch(r'by\s+(.+)', block[1].text, re.I | re.S | re.ASCII)
    if header is None or by is None:
        raise ValueError('composed SORT permits one literal input option,fresh OUT,NODUPKEY and BY only')
    words, keys, position = by[1].lower().split(), [], 0
    while position < len(words):
        descending = words[position] == 'descending'
        if descending:
            position += 1
        if position >= len(words) or words[position] in ('descending', 'notsorted'):
            raise ValueError('DESCENDING requires one immediately following ordinary key')
        keys.append({'name': words[position], 'descending': descending})
        position += 1
    step = Step(KIND, header[4].lower(), block[0].line, inputs=[header[1].lower()])
    step.operations = [Operation(KIND, block[0].line, {
        'profile': PROFILE, 'selection': {'mode': header[2].lower(), 'names': header[3].lower().split()},
        'keys': keys, 'nodupkey': bool(header[5]), 'source_lines': [block[1].line, block[2].line]})]
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
        novel = _selected(block)
        if novel and producer:
            selected = True
        try:
            if re.match(r'^data(?:\s|$)', text, re.I | re.ASCII):
                step = _parse_block(block, source)
                producer, route = True, ('character-input', 'DS-069')
            elif re.match(r'^proc\s+sort\b', text, re.I | re.ASCII):
                if novel:
                    step = parse_sort(block)
                    directed = any(key['descending'] for key in step.operations[0].args['keys'])
                    route = ('sort-directed-projection', 'DS-079') if directed else ('sort-input-drop', 'DS-078')
                elif projection._selected(block):
                    step, route = projection.parse_sort(block), ('sort-input-keep', 'DS-075')
                else:
                    step = ordering.parse_sort(block)
                    if step.kind == ordering.KIND and step.operations[0].args['profile'] != ordering.DIRECTED_PROFILE:
                        raise ValueError('composed SORT excludes BY_ALL')
                    route = ('directed-sort', 'DS-073') if step.kind == ordering.KIND else ('sort', 'DS-008')
            elif re.match(r'^title(?:\s|$)', text, re.I | re.ASCII) and len(block) == 1:
                step, route = parse_title(block[0]), ('logical-title', 'ST-020')
            elif re.match(r'^proc\s+print\b', text, re.I | re.ASCII):
                step, route = parse_print(block), ('mixed-print', 'ST-019')
            else:
                raise ValueError('composed SORT permits character DATA,SORT,TITLE and default PRINT only')
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
    plan.tickets.extend(Ticket(line, text, 'sort-composition', reason) for line, text, reason in failures)
    plan.matched.extend((construct, rule, statements[index].line) for index, (construct, rule) in routes.items())
    try:
        validate_program(plan.to_dict())
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        plan.tickets.append(Ticket(1, 'composed SORT program', 'sort-composition', str(error)))
    return plan


def validate_program(plan, catalog=None):
    _containers(plan)
    if type(plan) is not dict or type(plan.get('steps')) is not list:
        raise ValueError('composed SORT program requires a steps list')
    if not any(type(step) is dict and step.get('kind') == KIND for step in plan['steps']):
        refuse_legacy(plan)
        return None
    if (set(plan) != {'steps', 'tickets', 'matched', 'version'}
            or type(plan.get('version')) is not int or plan['version'] != 2
            or type(plan.get('tickets')) is not list or plan['tickets']
            or type(plan.get('matched')) is not list or len(plan['steps']) > 64):
        raise ValueError('composed SORT requires complete version2 and at most64 Steps')
    refuse_legacy(plan['matched'])
    if catalog is not None and (type(catalog) is not dict or catalog):
        raise ValueError('composed SORT requires an empty initial catalog')
    from .character_input import validate_step as validate_character
    from .mixed_reports import validate_step as validate_report, _schema as report_schema
    from .sort_duplicates import refuse_legacy as refuse_duplicates
    refuse_duplicates(plan)
    tables, producers, sorts, prints, titles = {}, 0, 0, 0, 0
    for step in plan['steps']:
        if type(step) is not dict or type(step.get('kind')) is not str:
            raise ValueError('composed SORT requires typed Steps')
        kind = step['kind']
        if kind != KIND:
            refuse_legacy(step)
        if kind == 'character_data':
            context = validate_character(step, plan['version'])
            if step['name'] in tables:
                raise ValueError('composed SORT producer requires a fresh destination')
            tables[step['name']] = {'schema': context['schema'], 'rows': context['rows']}
            producers += 1
        elif kind in (KIND, projection.KIND, ordering.KIND, 'sort'):
            if not producers:
                raise ValueError('composed SORT requires preceding genuine character lineage')
            schemas = {name: ordering._table(table)['schema'] for name, table in tables.items()}
            if kind == KIND:
                _, schema = _context(step, schemas, plan['version'])
                sorts += 1
            elif kind == projection.KIND:
                _, schema = projection._context(step, schemas, plan['version'])
            else:
                if step.get('name') in schemas:
                    raise ValueError('composed SORT joins require fresh OUT destinations')
                ordering._sort_context(step, schemas, plan['version'])
                if kind == ordering.KIND and step['operations'][0]['args']['profile'] != ordering.DIRECTED_PROFILE:
                    raise ValueError('composed SORT excludes BY_ALL')
                schema = schemas[step['inputs'][0]]
            # Propagation validates source and projected cells without sorting.
            tables[step['name']] = projection._project(tables[step['inputs'][0]], schema)
        elif kind in ('report_title', 'mixed_print'):
            context = validate_report(step, plan['version'])
            if kind == 'report_title':
                titles += 1
            else:
                prints += 1
                if context['input'] not in tables:
                    raise ValueError('composed SORT PRINT requires prior table lineage')
                report_schema(tables[context['input']]['schema'])
        else:
            raise ValueError('composed SORT has an unadmitted Step')
    if not producers or not sorts or prints > 2 or titles > 32:
        raise ValueError('composed SORT requires producer,new SORT,at most2 PRINTs and32 TITLEs')
    return {'sorts': sorts, 'producers': producers, 'prints': prints, 'titles': titles}


def run_program(plan, catalog=None, *, trace=None):
    if validate_program(plan, catalog) is None:
        raise ValueError('composed SORT executor requires its explicit new family')
    from .character_input import execute_step
    from .mixed_reports import execute_title, execute_print, validate_reports
    tables, reports, logs, title, ordinal = {}, {}, [], None, 0
    for step in plan['steps']:
        kind = step['kind']
        if kind == 'character_data':
            table, messages = execute_step(step, tables, plan['version'], trace=trace)
            tables[step['name']] = table
            logs.extend(messages)
        elif kind in (KIND, projection.KIND, ordering.KIND, 'sort'):
            tables[step['name']] = execute_sort(step, tables, plan['version'], trace=trace)
        elif kind == 'report_title':
            title = execute_title(step, plan['version'], trace=trace)
        else:
            ordinal += 1
            artifacts = execute_print(step, tables, title, ordinal, plan['version'], trace=trace)
            if reports.keys() & artifacts.keys():
                raise ValueError('composed SORT cannot overwrite earlier reports')
            reports.update(artifacts)
    result = {'datasets': deepcopy(tables), 'log': logs}
    if reports:
        validate_reports(reports)
        result['reports'] = reports
    return result
