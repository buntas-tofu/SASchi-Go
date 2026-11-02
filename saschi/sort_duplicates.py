"""Finite dual-output SORT, owned replacement and three logical reports.

Removed observations use an explicit stable sorted-stream repository policy.
This module does not claim native SAS duplicate-stream or physical output order.
"""
from copy import deepcopy
from dataclasses import asdict
import re

from sas_semantics import sas_sort_key
from .character_input import STEP_KEYS, SOURCE_NAME, ordinary
from . import sort_options as existing
from . import mixed_reports

KIND = 'duplicate_sort'
PROFILE = 'sort-dupout-v1'
PRINT_KIND = 'duplicate_print'
PRINT_PROFILE = 'sort-dupout-print-v1'
REPORT_CONTRACT = 'ascii-dupout-mixed-integer-v1'
KINDS = frozenset((KIND, PRINT_KIND))
PROFILES = frozenset((PROFILE, PRINT_PROFILE))


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
            raise ValueError('cyclic dual-output SORT containers are invalid')
        if identity in completed:
            continue
        if refuse and type(node) is dict:
            kind, profile = node.get('kind'), node.get('profile')
            if (type(kind) is str and kind in KINDS or
                    type(profile) is str and profile in PROFILES):
                raise ValueError('dual-output SORT markers require their explicit program family')
        active.add(identity)
        pending.append((node, True))
        pending.extend((child, False) for child in (node.values() if type(node) is dict else node))


def refuse_legacy(value):
    _containers(value, True)


def validate_step(step, version=2):
    _containers(step)
    if (type(version) is not int or version != 2 or type(step) is not dict or set(step) != STEP_KEYS
            or type(step.get('kind')) is not str or step['kind'] not in KINDS
            or not ordinary(step.get('name')) or type(step.get('line')) is not int or step['line'] < 1
            or type(step.get('inputs')) is not list or len(step['inputs']) != 1
            or not ordinary(step['inputs'][0]) or type(step.get('by')) is not list or step['by']
            or step.get('nodupkey') is not False or step.get('where') is not None
            or any(type(step.get(key)) is not dict or step[key] for key in ('retained', 'lengths', 'display_names'))
            or type(step.get('operations')) is not list or len(step['operations']) != 1):
        raise ValueError('dual-output SORT requires exact version2 Step defaults')
    operation = step['operations'][0]
    if (type(operation) is not dict or set(operation) != {'kind', 'line', 'args'}
            or operation.get('kind') != step['kind'] or type(operation.get('line')) is not int
            or operation['line'] != step['line'] or type(operation.get('args')) is not dict):
        raise ValueError('dual-output SORT requires one same-kind header-line operation')
    args = operation['args']
    if step['kind'] == PRINT_KIND:
        if (set(args) != {'profile', 'source_lines'} or args.get('profile') != PRINT_PROFILE
                or step['inputs'] != [step['name']]):
            raise ValueError('three-report PRINT requires its exact input/profile')
        lines, length = args['source_lines'], 1
    else:
        if (set(args) != {'profile', 'by', 'dupout', 'replace', 'source_lines'}
                or args.get('profile') != PROFILE or type(args.get('by')) is not list
                or not 1 <= len(args['by']) <= 8 or any(not ordinary(n) for n in args['by'])
                or len(set(args['by'])) != len(args['by']) or not ordinary(args.get('dupout'))
                or type(args.get('replace')) is not bool
                or (step['name'] == step['inputs'][0]) != args['replace']
                or args['dupout'] in (step['name'], step['inputs'][0])):
            raise ValueError('DUPOUT requires ascending unique keys, two distinct destinations and exact replacement flag')
        lines, length = args['source_lines'], 2
    if (type(lines) is not list or len(lines) != length
            or any(type(line) is not int or line < step['line'] for line in lines)
            or lines != sorted(lines)):
        raise ValueError('dual-output SORT requires ordered exact source provenance')
    return deepcopy(args)


def _context(step, schemas, version=2, owners=None):
    args = validate_step(step, version)
    if step['kind'] != KIND:
        raise ValueError('partition executor requires duplicate_sort')
    source = step['inputs'][0]
    if source not in schemas or args['dupout'] in schemas:
        raise ValueError('DUPOUT requires a preceding source and fresh duplicate destination')
    if args['replace']:
        if owners is not None and source not in owners:
            raise ValueError('replacement requires a prior SORT survivor destination')
    elif step['name'] in schemas:
        raise ValueError('explicit survivor OUT must be fresh')
    schema = existing._schema(schemas[source])
    if any(name not in schema for name in args['by']):
        raise ValueError('DUPOUT BY variable is absent from the complete schema')
    return args


def execute_partition(step, tables, version=2, *, trace=None):
    """Return two independent tables; program admission proves replacement ownership."""
    _containers(tables)
    if type(tables) is not dict or any(not ordinary(name) for name in tables):
        raise ValueError('DUPOUT requires an ordinary named table catalog')
    schemas = {name: existing._table(table)['schema'] for name, table in tables.items()}
    args = _context(step, schemas, version)
    source = step['inputs'][0]
    table = tables[source]
    ordered = sorted(range(len(table['rows'])), key=lambda i: tuple(
        sas_sort_key(table['rows'][i][name]) for name in args['by']))
    kept, removed, previous = [], [], None
    for index in ordered:
        key = tuple(sas_sort_key(table['rows'][index][name]) for name in args['by'])
        (kept if not kept or key != previous else removed).append(index)
        previous = key
    def output(indices):
        return {'schema': deepcopy(table['schema']),
                'rows': [deepcopy(table['rows'][index]) for index in indices]}
    result = {step['name']: output(kept), args['dupout']: output(removed)}
    if trace is not None:
        trace.append({'event': 'sort_dupout', 'line': step['line'], 'source': source,
                      'destination': step['name'], 'duplicate_destination': args['dupout'],
                      'replace': args['replace'], 'source_ordinals': [i + 1 for i in ordered],
                      'kept_ordinals': [i + 1 for i in kept], 'removed_ordinals': [i + 1 for i in removed]})
    return result


def _legacy_print(step, version=2):
    validate_step(step, version)
    if step['kind'] != PRINT_KIND:
        raise ValueError('three-report renderer requires duplicate_print')
    # The pure logical renderer retains its old two-report public contract.
    # Only this separately admitted wrapper selects a third artifact basename.
    legacy = deepcopy(step)
    legacy['kind'] = legacy['operations'][0]['kind'] = 'mixed_print'
    legacy['operations'][0]['args']['profile'] = mixed_reports.PRINT_PROFILE
    return legacy


def execute_print(step, tables, title=None, ordinal=1, version=2, *, trace=None):
    if type(ordinal) is not int or ordinal not in (1, 2, 3):
        raise ValueError('three-report PRINT requires ordinal1..3')
    legacy = _legacy_print(step, version)
    observed = [] if trace is not None else None
    rendered = mixed_reports.execute_print(legacy, tables, title, 1, version, trace=observed)
    text = rendered['print_01.txt']
    name = 'print_' + str(ordinal).zfill(2) + '.txt'
    if trace is not None:
        observed[-1] = 'mixed-print|output|' + name + '|' + str(len(text))
        trace.extend(observed)
    return {name: text}


def validate_reports(reports):
    names = ['print_01.txt', 'print_02.txt', 'print_03.txt']
    if (type(reports) is not dict or not 1 <= len(reports) <= 3
            or list(reports) != names[:len(reports)]):
        raise ValueError('three-report SORT requires ordered print_01 through print_03 artifacts')
    for text in reports.values():
        mixed_reports._validate_text(text)
    return reports


def _selected(block):
    from .parser import Kind
    words = ' '.join(token.text for token in block[0].tokens if token.kind is Kind.WORD)
    return re.search(r'(?:^|\s)dupout\s*=', words, re.I | re.ASCII) is not None


def parse_sort(block):
    from .plan import Operation, Step
    if (len(block) != 3 or any(statement.terminated is not True for statement in block)
            or any(not s.text.isascii() or len(s.text) > 16384 for s in block)
            or block[-1].text.lower() != 'run'):
        raise ValueError('DUPOUT requires header,BY and explicit RUN')
    header = re.fullmatch(r'proc\s+sort\s+data\s*=\s*(' + SOURCE_NAME + r')'
                          r'(?:\s+out\s*=\s*(' + SOURCE_NAME + r'))?\s+dupout\s*=\s*('
                          + SOURCE_NAME + r')\s+nodupkey', block[0].text, re.I | re.ASCII)
    by = re.fullmatch(r'by\s+(.+)', block[1].text, re.I | re.S | re.ASCII)
    if header is None or by is None:
        raise ValueError('DUPOUT permits DATA,[fresh OUT],fresh DUPOUT,NODUPKEY and ascending BY only')
    names = by[1].lower().split()
    if any(name in ('descending', 'notsorted') for name in names):
        raise ValueError('DUPOUT requires an ascending literal BY list')
    source, destination = header[1].lower(), (header[2] or header[1]).lower()
    step = Step(KIND, destination, block[0].line, inputs=[source])
    args = {'profile': PROFILE, 'by': names, 'dupout': header[3].lower(),
            'replace': header[2] is None, 'source_lines': [block[1].line, block[2].line]}
    step.operations = [Operation(KIND, step.line, args)]
    validate_step(asdict(step))
    return step


def parse_print(block):
    step = mixed_reports.parse_print(block)
    step.kind = step.operations[0].kind = PRINT_KIND
    step.operations[0].args['profile'] = PRINT_PROFILE
    validate_step(asdict(step))
    return step


def source_steps(source, statements):
    from .formatted_program import _blocks
    from .character_input import _parse_block
    from .parser import Kind
    steps, failures, routes = [], [], {}
    producer = selected = False
    for start, end, block in _blocks(statements):
        text = block[0].text
        duplicate = bool(re.match(r'^proc\s+sort\b', text, re.I | re.ASCII)) and _selected(block)
        if duplicate and producer:
            selected = True
        try:
            if re.match(r'^data(?:\s|$)', text, re.I | re.ASCII):
                step, route = _parse_block(block, source), ('character-input', 'DS-069')
                producer = True
            elif re.match(r'^proc\s+sort\b', text, re.I | re.ASCII):
                step = parse_sort(block) if duplicate else existing.parse_sort(block)
                if duplicate:
                    route = ('sort-replacement', 'DS-077') if step.operations[0].args['replace'] else ('sort-duplicates', 'DS-076')
                elif step.kind == 'sort':
                    route = ('sort', 'DS-008')
                elif step.operations[0].args['profile'] == existing.DIRECTED_PROFILE:
                    route = ('directed-sort', 'DS-073')
                else:
                    raise ValueError('DUPOUT composition with BY _ALL_ is deferred')
            elif re.match(r'^title(?:\s|$)', text, re.I | re.ASCII) and len(block) == 1:
                step, route = mixed_reports.parse_title(block[0]), ('logical-title', 'ST-020')
            elif re.match(r'^proc\s+print\b', text, re.I | re.ASCII):
                step, route = parse_print(block), ('sort-duplicate-reports', 'ST-024')
            else:
                raise ValueError('DUPOUT family permits character DATA,SORT,TITLE and default PRINT only')
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
    plan.tickets.extend(Ticket(line, text, 'sort-duplicates', reason) for line, text, reason in failures)
    plan.matched.extend((kind, rule, statements[index].line) for index, (kind, rule) in routes.items())
    try:
        validate_program(plan.to_dict())
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        plan.tickets.append(Ticket(1, 'dual-output SORT program', 'sort-duplicates', str(error)))
    return plan


def validate_program(plan, catalog=None):
    _containers(plan)
    if type(plan) is not dict or type(plan.get('steps')) is not list:
        raise ValueError('DUPOUT program requires a steps list')
    if not any(type(step) is dict and step.get('kind') == KIND for step in plan['steps']):
        refuse_legacy(plan)
        return None
    if (set(plan) != {'steps', 'tickets', 'matched', 'version'} or type(plan.get('version')) is not int
            or plan['version'] != 2 or type(plan.get('tickets')) is not list or plan['tickets']
            or type(plan.get('matched')) is not list or len(plan['steps']) > 64):
        raise ValueError('DUPOUT requires a complete version2 program with at most64 Steps')
    refuse_legacy(plan['matched'])
    if catalog is not None and (type(catalog) is not dict or catalog):
        raise ValueError('DUPOUT requires an empty initial catalog')
    from .character_input import validate_step as validate_character
    tables, owners = {}, set()
    producers = sorts = prints = titles = 0
    for step in plan['steps']:
        if type(step) is not dict or type(step.get('kind')) is not str:
            raise ValueError('DUPOUT requires typed Steps')
        kind = step['kind']
        if kind not in KINDS:
            refuse_legacy(step)
        if kind == 'character_data':
            context = validate_character(step, plan['version'])
            if step['name'] in tables:
                raise ValueError('DUPOUT producer destination must be fresh')
            tables[step['name']] = {'schema': context['schema'], 'rows': context['rows']}
            producers += 1
        elif kind in (KIND, existing.KIND, 'sort'):
            if not producers:
                raise ValueError('DUPOUT requires genuine preceding character lineage')
            schemas = {name: existing._table(table)['schema'] for name, table in tables.items()}
            if kind == KIND:
                args = _context(step, schemas, plan['version'], owners)
                # Conservative preflight propagates values, never executes SORT.
                original = deepcopy(tables[step['inputs'][0]])
                tables[step['name']] = deepcopy(original)
                tables[args['dupout']] = original
                sorts += 1
            else:
                if step.get('name') in schemas:
                    raise ValueError('non-DUPOUT SORT requires fresh OUT in this family')
                context = existing._sort_context(step, schemas, plan['version'])
                if kind == existing.KIND and step['operations'][0]['args']['profile'] != existing.DIRECTED_PROFILE:
                    raise ValueError('DUPOUT composition with BY _ALL_ is deferred')
                tables[step['name']] = deepcopy(tables[step['inputs'][0]])
            owners.add(step['name'])
        elif kind == PRINT_KIND:
            validate_step(step, plan['version'])
            if step['name'] not in tables:
                raise ValueError('three-report PRINT requires preceding table lineage')
            mixed_reports._schema(tables[step['name']]['schema'])
            prints += 1
        elif kind == 'report_title':
            mixed_reports.validate_step(step, plan['version'])
            titles += 1
        else:
            raise ValueError('DUPOUT program has an unadmitted Step')
    if not producers or not sorts or prints > 3 or titles > 32:
        raise ValueError('DUPOUT requires producer,partition,at most3PRINTs and32TITLEs')
    return {'producers': producers, 'sorts': sorts, 'prints': prints, 'titles': titles}


def run_program(plan, catalog=None, *, trace=None):
    if validate_program(plan, catalog) is None:
        raise ValueError('DUPOUT executor requires its explicit program family')
    from .character_input import execute_step
    tables, reports, logs, title, ordinal = {}, {}, [], None, 0
    for step in plan['steps']:
        kind = step['kind']
        if kind == 'character_data':
            table, messages = execute_step(step, tables, plan['version'], trace=trace)
            tables[step['name']] = table
            logs.extend(messages)
        elif kind == KIND:
            tables.update(execute_partition(step, tables, plan['version'], trace=trace))
        elif kind in (existing.KIND, 'sort'):
            tables[step['name']] = existing.execute_sort(step, tables, plan['version'], trace=trace)
        elif kind == 'report_title':
            title = mixed_reports.execute_title(step, plan['version'], trace=trace)
        else:
            ordinal += 1
            reports.update(execute_print(step, tables, title, ordinal, plan['version'], trace=trace))
    result = {'datasets': deepcopy(tables), 'log': logs}
    if reports:
        result['reports'] = validate_reports(reports)
    return result
