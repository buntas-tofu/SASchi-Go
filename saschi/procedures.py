"""Separate bounded MEANS output and logical numeric PRINT procedure policies."""
from copy import deepcopy
from fractions import Fraction
from itertools import groupby
import math
import re

from .binary64 import numeric, render_numeric_list
from .values import column_type, normalize_catalog

MEANS_PROFILE = 'grouped-integer-means-df-v1'
PRINT_PROFILE = 'numeric-print-v1'
KINDS = frozenset(('proc_means', 'proc_print'))
MAX_ROWS = 1000
MAX_COLUMNS = 32
MAX_VALUE = 1000
STEP_KEYS = frozenset(('kind','name','line','inputs','by','operations','nodupkey',
                       'where','retained','lengths','display_names'))
NAME = re.compile(r'[a-z_][a-z0-9_]{0,31}\Z', re.ASCII)
RESERVED = frozenset(('_null_','_n_','_error_','_all_','_numeric_','_character_',
                      '_temporary_','_infile_','_file_','_ods_','_page_','_blankpage_'))
STATISTICS = frozenset(('n','nmiss','mean','var'))


def ordinary(name):
    return type(name) is str and NAME.fullmatch(name) is not None and name not in RESERVED


def _lines(value, length, first):
    if (type(value) is not list or len(value) != length or
            any(type(line) is not int or line < first for line in value) or
            value != sorted(value)):
        raise ValueError('procedure source lines must retain complete ordered statement positions')


def validate_step(step, version=2):
    """Validate new portable shapes independently of source parsing and row count."""
    if (type(version) is not int or version != 2 or type(step) is not dict or
            set(step) != STEP_KEYS or type(step.get('kind')) is not str or step['kind'] not in KINDS or
            not ordinary(step.get('name')) or type(step.get('line')) is not int or step['line'] < 1 or
            type(step.get('inputs')) is not list or len(step['inputs']) != 1 or
            not ordinary(step['inputs'][0]) or type(step.get('by')) is not list or
            step.get('nodupkey') is not False or step.get('where') is not None or
            type(step.get('retained')) is not dict or step['retained'] != {} or
            type(step.get('lengths')) is not dict or step['lengths'] != {} or
            type(step.get('display_names')) is not dict or step['display_names'] != {} or
            type(step.get('operations')) is not list or len(step['operations']) != 1):
        raise ValueError('procedure requires its exact version2 Step shape and one input')
    operation = step['operations'][0]
    if (type(operation) is not dict or set(operation) != {'kind','line','args'} or
            operation.get('kind') != step['kind'] or type(operation.get('line')) is not int or
            operation['line'] != step['line'] or type(operation.get('args')) is not dict):
        raise ValueError('procedure requires one same-kind header-line operation')
    args = operation['args']
    if step['kind'] == 'proc_print':
        if (set(args) != {'profile','names','source_lines'} or args.get('profile') != PRINT_PROFILE or
                step['name'] != step['inputs'][0] or step['by'] != [] or
                type(args.get('names')) is not list or not 1 <= len(args['names']) <= MAX_COLUMNS or
                any(not ordinary(name) for name in args['names']) or
                len(args['names']) != len(set(args['names']))):
            raise ValueError('PRINT requires explicit unique numeric names and numeric-print-v1')
        _lines(args['source_lines'], 2, step['line'])
        return {'kind':'proc_print','names':args['names']}
    if (set(args) != {'profile','variable','statistics','source_lines'} or
            args.get('profile') != MEANS_PROFILE or len(step['by']) != 1 or
            not ordinary(step['by'][0]) or step['by'][0] in ('_type_','_freq_') or
            not ordinary(args.get('variable')) or args['variable'] == step['by'][0] or
            type(args.get('statistics')) is not list or len(args['statistics']) != 4):
        raise ValueError('MEANS requires one distinct BY/VAR and explicit bounded DF statistics')
    names, statistics = [], []
    for item in args['statistics']:
        if (type(item) is not dict or set(item) != {'statistic','name'} or
                type(item.get('statistic')) is not str or item['statistic'] not in STATISTICS or
                not ordinary(item.get('name')) or item['name'] in (*step['by'],'_type_','_freq_')):
            raise ValueError('MEANS requires unique ordinary output names outside BY/TYPE/FREQ')
        names.append(item['name']); statistics.append(item['statistic'])
    if len(names) != len(set(names)) or set(statistics) != STATISTICS:
        raise ValueError('MEANS requires each of N/NMISS/MEAN/VAR exactly once')
    _lines(args['source_lines'], 4, step['line'])
    return {'kind':'proc_means','by':step['by'][0],'variable':args['variable'],
            'statistics':args['statistics']}


def refuse_legacy(operations):
    """Detect hidden new operations without adding a legacy size/depth budget."""
    active = set()
    stack = [(operations, False)]
    while stack:
        value, leave = stack.pop()
        if type(value) not in (dict, list, tuple):
            continue
        identity = id(value)
        if leave:
            active.remove(identity); continue
        if identity in active:
            raise ValueError('cyclic portable procedure structure')
        if type(value) is dict and type(value.get('kind')) is str and value['kind'] in KINDS:
            raise ValueError('procedure operations require their own procedure Step kind')
        active.add(identity); stack.append((value, True))
        stack.extend((child, False) for child in (value.values() if type(value) is dict else value))


def validate_program(plan):
    count = 0
    for step in plan['steps']:
        if type(step) is dict and type(step.get('kind')) is str and step['kind'] in KINDS:
            context = validate_step(step, plan['version'])
            count += context['kind'] == 'proc_print'
        else:
            refuse_legacy(step.get('operations', []) if type(step) is dict else step)
    if count > 1:
        raise ValueError('one PRINT per complete program is the bounded report policy')


def _input(step, tables, names):
    source = step['inputs'][0]
    if type(tables) is not dict or source not in tables:
        raise ValueError('procedure input dataset is missing: ' + source)
    table = normalize_catalog({source: tables[source]})[source]
    if len(table['rows']) > MAX_ROWS:
        raise ValueError('procedure input exceeds1000 selected rows')
    for name in names:
        if name not in table['schema']:
            raise ValueError('procedure selected variable is missing: ' + name)
        spec = table['schema'][name]
        if column_type(spec) != 'number' or isinstance(spec, dict) and spec.get('format'):
            raise ValueError('procedure selected variables require unformatted numeric descriptors')
    return table


def _integer(value):
    if value is None:
        return None
    if (type(value) not in (int, float) or not math.isfinite(value) or
            not float(value).is_integer() or abs(value) > MAX_VALUE):
        raise ValueError('MEANS selected values require ordinary missing or integers within1000')
    return int(value)


def execute_means(step, tables, version=2, *, trace=None):
    context = validate_step(step, version)
    if context['kind'] != 'proc_means':
        raise ValueError('MEANS executor requires proc_means')
    if type(tables) is not dict or any(type(name) is not str for name in tables):
        raise ValueError('MEANS requires a named catalog')
    if any(name.lower() == step['name'] for name in tables):
        raise ValueError('MEANS existing destination requires separate overwrite evidence')
    group, variable = context['by'], context['variable']
    table = _input(step, tables, (group, variable))
    selected = [(_integer(row[group]), _integer(row[variable])) for row in table['rows']]
    key = lambda value: (value is not None, value or 0)
    if any(key(left[0]) > key(right[0]) for left, right in zip(selected, selected[1:])):
        raise ValueError('MEANS requires ascending BY-sorted input')
    schema = {group: deepcopy(table['schema'][group])}
    for name in ['_type_','_freq_'] + [item['name'] for item in context['statistics']]:
        schema[name] = {'type':'number','length':8}
    if trace is not None: trace.append('means|input|' + step['inputs'][0] + '|' + str(len(selected)))
    rows = []
    for value, entries in groupby(selected, key=lambda pair: pair[0]):
        values = [pair[1] for pair in entries]
        xs = [x for x in values if x is not None]
        n, total, squares = len(xs), sum(xs), sum(x*x for x in xs)
        if abs(total) > 10**6 or squares > 10**9 or n*squares > 10**12 or total*total > 10**12:
            raise ValueError('MEANS exact sufficient statistics exceed the declared bound')
        statistics = {'n':float(n),'nmiss':float(len(values)-n),
                      'mean':float(Fraction(total,n)) if n else None,
                      'var':float(Fraction(n*squares-total*total,n*(n-1))) if n>1 else None}
        row = {group:None if value is None else float(value), '_type_':0.0,
               '_freq_':float(len(values))}
        for item in context['statistics']:
            row[item['name']] = statistics[item['statistic']]
        rows.append(row)
        if trace is not None: trace.append('group|' + ('.' if value is None else str(value)) + '|' + str(len(values)) + '|' + str(n) + '|' + str(len(values)-n))
    if trace is not None: trace.append('means|output|' + step['name'] + '|' + str(len(rows)))
    return {'schema':schema,'rows':rows}


def execute_print(step, tables, version=2, *, trace=None):
    from .report_artifacts import validate_reports
    context = validate_step(step, version)
    if context['kind'] != 'proc_print':
        raise ValueError('PRINT executor requires proc_print')
    names = context['names']; table = _input(step, tables, names)
    records = [' '.join(names)]
    if trace is not None:
        trace.append('print|input|' + step['inputs'][0] + '|' + str(len(table['rows'])))
        trace.append('print|header|' + records[0].encode('ascii').hex())
    for row in table['rows']:
        fields = [render_numeric_list([numeric(row[name])])[:-1] for name in names]
        records.append(' '.join(fields))
        if trace is not None: trace.append('print|row|' + records[-1].encode('ascii').hex())
    reports = {'print.txt':'\n'.join(records)+'\n'}
    validate_reports(reports)
    if trace is not None: trace.append('print|output|print.txt|' + str(len(reports['print.txt'])))
    return reports


def _name(text):
    if not text.isascii():
        raise ValueError('procedure names require ASCII before normalization')
    value = text.lower()
    if not ordinary(value):
        raise ValueError('procedure requires ordinary unqualified names')
    return value


def parse_block(statements):
    from .plan import Operation, Step
    if any(statement.terminated is not True for statement in statements):
        raise ValueError('every procedure statement requires its explicit semicolon')
    texts = [statement.text for statement in statements]
    if any(not text.isascii() or len(text) > 16384 for text in texts):
        raise ValueError('procedure statements require bounded canonical ASCII text')
    means = re.fullmatch(r'proc\s+means\s+data\s*=\s*([A-Za-z_][A-Za-z0-9_]{0,31})\s+noprint\s+vardef\s*=\s*df',texts[0],re.I|re.ASCII)
    if means:
        if len(texts) != 5 or texts[-1].lower() != 'run':
            raise ValueError('MEANS requires BY, VAR, OUTPUT and explicit RUN exactly once')
        by = re.fullmatch(r'by\s+([A-Za-z_][A-Za-z0-9_]{0,31})',texts[1],re.I|re.ASCII)
        var = re.fullmatch(r'var\s+([A-Za-z_][A-Za-z0-9_]{0,31})',texts[2],re.I|re.ASCII)
        out = re.fullmatch(r'output\s+out\s*=\s*([A-Za-z_][A-Za-z0-9_]{0,31})\s+(.+)\s*/\s*noinherit',texts[3],re.I|re.ASCII)
        if not by or not var or not out:
            raise ValueError('MEANS requires explicit one BY/VAR and named OUTPUT /NOINHERIT')
        terms = re.findall(r'(n|nmiss|mean|var)\s*=\s*([A-Za-z_][A-Za-z0-9_]{0,31})',out[2],re.I|re.ASCII)
        consumed = re.sub(r'(n|nmiss|mean|var)\s*=\s*[A-Za-z_][A-Za-z0-9_]{0,31}', '', out[2], flags=re.I|re.ASCII)
        if consumed.strip() or len(terms) != 4:
            raise ValueError('MEANS OUTPUT supports four explicit N/NMISS/MEAN/VAR aliases only')
        step = Step('proc_means',_name(out[1]),statements[0].line,
                    inputs=[_name(means[1])],by=[_name(by[1])])
        args = {'profile':MEANS_PROFILE,'variable':_name(var[1]),
                'statistics':[{'statistic':stat.lower(),'name':_name(name)} for stat,name in terms],
                'source_lines':[statement.line for statement in statements[1:]]}
    else:
        printed = re.fullmatch(r'proc\s+print\s+data\s*=\s*([A-Za-z_][A-Za-z0-9_]{0,31})\s+noobs',texts[0],re.I|re.ASCII)
        if not printed or len(texts) != 3 or texts[-1].lower() != 'run':
            raise ValueError('PRINT requires explicit DATA=, NOOBS, VAR and RUN only')
        var = re.fullmatch(r'var\s+(.+)',texts[1],re.I|re.ASCII)
        if not var:
            raise ValueError('PRINT requires an explicit ordered VAR list')
        step = Step('proc_print',_name(printed[1]),statements[0].line,inputs=[_name(printed[1])])
        args = {'profile':PRINT_PROFILE,'names':[_name(word) for word in var[1].split()],
                'source_lines':[statement.line for statement in statements[1:]]}
    step.operations = [Operation(step.kind,step.line,args)]
    from dataclasses import asdict
    validate_step(asdict(step))
    return step


def compile_program(source, legacy):
    from .parser import Kind, ParseError, split_statements
    from .plan import Plan, Ticket
    try:
        statements = split_statements(source)
    except ParseError:
        return None
    blocks = []; position = 0
    while position < len(statements):
        statement = statements[position]
        if (any(token.kind is Kind.DATA for token in statement.tokens) or
                not re.match(r'^proc\s+(?:means|print)\b',statement.text,re.I|re.ASCII)):
            position += 1; continue
        end = position + 1
        while end < len(statements) and statements[end].text.lower() != 'run':
            if re.match(r'^(?:data|proc)\s',statements[end].text,re.I|re.ASCII):
                break
            end += 1
        limit = end+1 if end < len(statements) and statements[end].text.lower() == 'run' else end
        start = statement.tokens[0].start
        stop = statements[limit].tokens[0].start if limit < len(statements) else len(source)
        if start is None or stop is None:
            return None
        blocks.append((start,stop,statements[position:limit]))
        position = max(position+1,limit)
    if not blocks:
        return None
    plan = Plan(); cursor = 0
    def preceding(start,stop):
        if not source[start:stop].strip():
            return
        compiled = legacy('\n'*source[:start].count('\n')+source[start:stop])
        plan.steps.extend(compiled.steps); plan.tickets.extend(compiled.tickets)
        plan.matched.extend(compiled.matched)
    for start,stop,block in blocks:
        preceding(cursor,start)
        try:
            step = parse_block(block); plan.steps.append(step)
            rule, construct = ('ST-017','proc-means') if step.kind == 'proc_means' else ('ST-018','proc-print')
            plan.matched.extend((construct,rule,statement.line) for statement in block)
        except (ValueError,KeyError,TypeError,RecursionError) as exc:
            plan.tickets.append(Ticket(block[0].line,block[0].text,'bounded-procedure',str(exc)))
        cursor = stop
    preceding(cursor,len(source))
    prints = [step for step in plan.steps if step.kind == 'proc_print']
    if len(prints)>1:
        plan.tickets.append(Ticket(prints[1].line,'PROC PRINT','proc-print',
                                   'one PRINT per complete program is the bounded report policy'))
    files = [op for step in plan.steps if step.kind == 'exchange_data'
             for op in step.operations if op.kind == 'file_select']
    if len(files)>1:
        ticket = Ticket(files[1].line,'FILE','csv-export',
                        'one export destination per program is the bounded profile')
        if ticket not in plan.tickets:
            plan.tickets.append(ticket)
    return plan
