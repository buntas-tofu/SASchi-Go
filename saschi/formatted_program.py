"""Whole-program admission for the bounded job-local INVALUE report family.

The source recognizer and portable validator share component contracts. They
require real prior definitions and producers, never keyword co-occurrence.
"""
from copy import deepcopy
from dataclasses import asdict
import re

from . import formatted_input as inputs
from . import informat_reports as reports

KINDS = inputs.KINDS | reports.KINDS
STEP_KINDS = frozenset((inputs.DEFINITION_KIND, inputs.DATA_KIND)) | reports.KINDS


def _blocks(statements):
    """Keep opaque payloads inside their DATA block and respect step boundaries."""
    position = 0
    while position < len(statements):
        start = position
        text = statements[start].text
        position += 1
        if re.match(r'^(?:data|proc)(?:\s|$)', text, re.I | re.ASCII):
            while position < len(statements):
                current = statements[position]
                from .parser import Kind
                opaque = any(token.kind is Kind.DATA for token in current.tokens)
                if not opaque and current.text.lower() == 'run':
                    position += 1
                    break
                if not opaque and re.match(r'^(?:data|proc)(?:\s|$)', current.text, re.I | re.ASCII):
                    break
                position += 1
        yield start, position, statements[start:position]


def source_steps(source, statements):
    """Return parsed Steps, refusals, and source-index routes without a Plan."""
    registry, steps, failures, routes = {}, [], [], {}
    has_producer = False
    for start, end, block in _blocks(statements):
        text = block[0].text
        try:
            if re.match(r'^proc\s+format\b', text, re.I | re.ASCII):
                step = inputs.compile_definition(block)
                context = inputs.validate_definition_step(asdict(step))
                if step.name in registry or len(registry) >= 8:
                    raise ValueError('job-local informats require unique names and at most8 definitions')
                registry[step.name] = context
                construct, rule = 'numeric-invalue', 'DS-071'
            elif re.match(r'^data(?:\s|$)', text, re.I | re.ASCII):
                step = inputs.compile_data(block, source, registry)
                has_producer = True
                construct, rule = 'formatted-input', 'DS-072'
            elif re.match(r'^title(?:\s|$)', text, re.I | re.ASCII) and len(block) == 1:
                step = reports.compile_title(block[0])
                construct, rule = 'informat-title', 'ST-023'
            elif re.match(r'^proc\s+print\b', text, re.I | re.ASCII):
                step = reports.compile_print(block)
                construct, rule = 'labelled-print', 'ST-021'
            elif re.match(r'^proc\s+means\b', text, re.I | re.ASCII):
                step = reports.compile_means(block)
                construct, rule = 'default-means', 'ST-022'
            else:
                raise ValueError('statement is outside the bounded INVALUE family')
            steps.append(step)
            from .parser import Kind
            for index in range(start, end):
                if not any(token.kind is Kind.DATA for token in statements[index].tokens):
                    routes[index] = (construct, rule)
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            failures.append((block[0].line, text, str(error)))
    return steps, failures, routes, bool(registry) and has_producer


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
    plan.tickets.extend(Ticket(line, text, 'formatted-program', reason) for line, text, reason in failures)
    plan.matched.extend((construct, rule, statements[index].line)
                        for index, (construct, rule) in routes.items())
    try:
        validate_program(plan.to_dict())
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        plan.tickets.append(Ticket(1, 'formatted program', 'formatted-program', str(error)))
    return plan


def validate_program(plan, catalog=None):
    if type(plan) is not dict or type(plan.get('steps')) is not list:
        raise ValueError('portable program requires a steps list')
    selected = any(type(step) is dict and type(step.get('kind')) is str
                   and step['kind'] in STEP_KINDS for step in plan['steps'])
    if not selected:
        inputs.refuse_legacy(plan)
        reports.refuse_legacy(plan)
        return None
    if (type(plan.get('version')) is not int or plan['version'] != 2
            or type(plan.get('tickets')) is not list or plan['tickets']
            or len(plan['steps']) > 64):
        raise ValueError('formatted program requires complete version2 and at most64 Steps')
    if catalog is not None and (type(catalog) is not dict or catalog):
        raise ValueError('formatted program requires an empty initial catalog')
    registry, tables = {}, {}
    counts = {kind: 0 for kind in STEP_KINDS}
    for step in plan['steps']:
        if type(step) is not dict or type(step.get('kind')) is not str or step['kind'] not in STEP_KINDS:
            raise ValueError('formatted family permits only its five distinct Step kinds')
        kind = step['kind']
        counts[kind] += 1
        if kind == inputs.DEFINITION_KIND:
            context = inputs.validate_definition_step(step, plan['version'])
            if step['name'] in registry:
                raise ValueError('job-local informat cannot overwrite a prior definition')
            registry[step['name']] = context
        elif kind == inputs.DATA_KIND:
            context = inputs.validate_data_step(step, registry, plan['version'])
            if step['name'] in tables:
                raise ValueError('formatted DATA requires a fresh destination')
            tables[step['name']] = {'schema': context['schema'], 'rows': context['rows']}
        else:
            context = reports.validate_step(step, plan['version'])
            if kind != 'informat_title':
                if context['input'] not in tables:
                    raise ValueError('informat report requires a preceding formatted producer')
                reports.validate_table(tables[context['input']], kind, context.get('labels'))
    if (not 1 <= counts[inputs.DEFINITION_KIND] <= 8 or not 1 <= counts[inputs.DATA_KIND] <= 8
            or counts['informat_title'] > 32 or counts['labelled_print'] > 1 or counts['default_means'] > 1):
        raise ValueError('formatted family exceeds its definition,producer,title or report bounds')
    return {'counts': counts}


def run_program(plan, catalog=None, *, trace=None):
    if validate_program(plan, catalog) is None:
        raise ValueError('formatted executor requires its explicit family')
    registry, tables, artifacts, logs, title = {}, {}, {}, [], None
    for step in plan['steps']:
        kind = step['kind']
        if kind == inputs.DEFINITION_KIND:
            registry[step['name']] = inputs.validate_definition_step(step)
        elif kind == inputs.DATA_KIND:
            table, messages = inputs.execute_data(step, registry, tables, trace=trace)
            tables[step['name']] = table
            logs.extend(messages)
        elif kind == 'informat_title':
            title = reports.execute_title(step, trace=trace)
        else:
            execute = reports.execute_print if kind == 'labelled_print' else reports.execute_means
            new = execute(step, tables, title, trace=trace)
            if artifacts.keys() & new.keys():
                raise ValueError('logical report artifact cannot overwrite an earlier snapshot')
            artifacts.update(new)
    result = {'datasets': deepcopy(tables), 'log': logs}
    if artifacts:
        reports.validate_reports(artifacts)
        result['reports'] = artifacts
    return result
