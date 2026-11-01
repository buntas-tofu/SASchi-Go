"""Bounded labelled PRINT and exact decimal default MEANS report policies."""
from dataclasses import asdict
from fractions import Fraction
from math import isfinite, isqrt
import json
import re

from .procedures import STEP_KEYS, ordinary

TITLE_PROFILE = 'informat-title-v1'
PRINT_PROFILE = 'labelled-print-v1'
MEANS_PROFILE = 'default-means-v1'
REPORT_CONTRACT = 'ascii-informat-reports-v1'
KINDS = frozenset(('informat_title', 'labelled_print', 'default_means'))
PROFILES = frozenset((TITLE_PROFILE, PRINT_PROFILE, MEANS_PROFILE))
MAX_ROWS, MAX_COLUMNS, MAX_NUMERIC = 1000, 32, 8
MAX_VALUE, MAX_HEADER_BYTES, MAX_ROW_BYTES = 1000, 1055, 415
MAX_REPORT_BYTES, MAX_TOKEN_BYTES = 417056, 14
SCALE = 10**8
NAME = r'[A-Za-z_][A-Za-z0-9_]{0,31}'


def _literal(value, maximum):
    if (type(value) is not str or not 1 <= len(value) <= maximum or not value.strip(' ')
            or any(not 32 <= ord(char) <= 126 for char in value) or '&' in value or '%' in value):
        raise ValueError('report literal requires bounded printableASCII nonspace text without macro markers')
    return value


def _title(value):
    return None if value is None else _literal(value, 128)


def _labels(value):
    if type(value) is not list or not 1 <= len(value) <= MAX_COLUMNS:
        raise ValueError('labelled PRINT requires1..32 label declarations')
    result = {}
    for item in value:
        if (type(item) is not dict or set(item) != {'name', 'text'}
                or not ordinary(item.get('name')) or item['name'] in result):
            raise ValueError('PRINT labels require unique ordinary names and exact declaration fields')
        result[item['name']] = _literal(item['text'], 64)
    return result


def validate_step(step, version=2):
    """Validate every new portable field before a row-count shortcut."""
    if (type(version) is not int or version != 2 or type(step) is not dict
            or set(step) != STEP_KEYS or type(step.get('kind')) is not str or step['kind'] not in KINDS
            or type(step.get('line')) is not int or step['line'] < 1
            or type(step.get('inputs')) is not list or type(step.get('by')) is not list or step['by']
            or step.get('where') is not None or step.get('nodupkey') is not False
            or any(type(step.get(key)) is not dict or step[key] for key in ('retained', 'lengths', 'display_names'))
            or type(step.get('operations')) is not list or len(step['operations']) != 1):
        raise ValueError('informat report requires exact version2 Step defaults')
    operation = step['operations'][0]
    if (type(operation) is not dict or set(operation) != {'kind', 'line', 'args'}
            or operation.get('kind') != step['kind'] or type(operation.get('line')) is not int
            or operation['line'] != step['line'] or type(operation.get('args')) is not dict):
        raise ValueError('informat report requires one same-kind header-line operation')
    args, kind = operation['args'], step['kind']
    if kind == 'informat_title':
        if (step['name'] != '_null_' or step['inputs'] or set(args) != {'profile', 'text'}
                or args.get('profile') != TITLE_PROFILE):
            raise ValueError('informat TITLE requires its distinct profile and reset/literal shape')
        return {'kind': kind, 'text': _title(args['text'])}
    if not ordinary(step.get('name')) or step['inputs'] != [step['name']]:
        raise ValueError('informat report requires one ordinary matching input/name')
    expected = {'profile', 'source_lines', 'labels'} if kind == 'labelled_print' else {'profile', 'source_lines'}
    if set(args) != expected or args.get('profile') != (PRINT_PROFILE if kind == 'labelled_print' else MEANS_PROFILE):
        raise ValueError('informat report requires exact profile and operation fields')
    lines = args['source_lines']
    if (type(lines) is not list or len(lines) != (2 if kind == 'labelled_print' else 1)
            or any(type(line) is not int or line < step['line'] for line in lines) or lines != sorted(lines)):
        raise ValueError('informat report requires complete ordered source positions')
    result = {'kind': kind, 'input': step['name']}
    if kind == 'labelled_print':
        result['labels'] = _labels(args['labels'])
    return result


def refuse_legacy(value):
    """Reject hidden new markers with linear DAG traversal and cycle refusal."""
    pending, active, completed = [(value, False)], set(), set()
    while pending:
        node, leaving = pending.pop()
        if type(node) not in (dict, list, tuple):
            continue
        identity = id(node)
        if leaving:
            active.remove(identity)
            completed.add(identity)
            continue
        if identity in completed:
            continue
        if identity in active:
            raise ValueError('cyclic portable informat-report containers')
        if type(node) is dict:
            kind, profile = node.get('kind'), node.get('profile')
            if (type(kind) is str and kind in KINDS) or (type(profile) is str and profile in PROFILES):
                raise ValueError('informat report markers require their distinct new Step kinds')
        active.add(identity)
        pending.append((node, True))
        pending.extend((child, False) for child in (node.values() if type(node) is dict else node))


def validate_schema(schema, kind, labels=None):
    if type(schema) is not dict or not 1 <= len(schema) <= MAX_COLUMNS:
        raise ValueError('informat reports require1..32 plain ordered columns')
    numeric = []
    for name, descriptor in schema.items():
        if (not ordinary(name) or type(descriptor) is not dict or set(descriptor) != {'type', 'length'}
                or type(descriptor.get('type')) is not str or type(descriptor.get('length')) is not int):
            raise ValueError('informat reports require ordinary names and plain typed length descriptors')
        if descriptor['type'] == 'number' and descriptor['length'] == 8:
            numeric.append(name)
        elif descriptor['type'] != 'character' or not 1 <= descriptor['length'] <= 32:
            raise ValueError('informat report columns require characterwidth1..32 or numericlength8')
    if kind == 'default_means':
        if not 1 <= len(numeric) <= MAX_NUMERIC:
            raise ValueError('default MEANS requires1..8 numeric analysis columns')
    elif kind == 'labelled_print':
        if type(labels) is not dict or not set(labels) <= set(schema):
            raise ValueError('PRINT label target is absent from complete input schema')
        header = ' '.join(json.dumps(labels.get(name, name), ensure_ascii=True) for name in schema)
        if len(header) > MAX_HEADER_BYTES:
            raise ValueError('labelled PRINT exceeds1055 header bytes')
    else:
        raise ValueError('unknown informat report schema context')
    return numeric


def _integer(value):
    if value is None:
        return None
    if type(value) not in (int, float) or abs(value) > MAX_VALUE or not isfinite(value) or value != int(value):
        raise ValueError('informat report numbers require ordinarymissing or exact integers within1000')
    return int(value)


def validate_table(table, kind, labels=None):
    if type(table) is not dict or set(table) != {'schema', 'rows'} or type(table.get('rows')) is not list:
        raise ValueError('informat reports require exact schema/rows table fields')
    numeric = validate_schema(table['schema'], kind, labels)
    if len(table['rows']) > MAX_ROWS:
        raise ValueError('informat report input exceeds1000 rows')
    for row in table['rows']:
        if type(row) is not dict or set(row) != set(table['schema']):
            raise ValueError('informat report row fields must match the full schema')
        for name, descriptor in table['schema'].items():
            value = row[name]
            if descriptor['type'] == 'number':
                _integer(value)
            elif (type(value) is not str or len(value) != descriptor['length']
                  or any(not 32 <= ord(char) <= 126 for char in value)):
                raise ValueError('informat report characters require exact padded printableASCII cells')
    return numeric


def _input(step, tables, context):
    if type(tables) is not dict or context['input'] not in tables:
        raise ValueError('informat report input table is missing')
    table = tables[context['input']]
    numeric = validate_table(table, context['kind'], context.get('labels'))
    return table, numeric


def _fixed8(value, *, square_root=False):
    """Exact half-away decimal tokens; no binary64 rounding or tie inference."""
    if type(value) is not Fraction:
        raise ValueError('fixed8 renderer requires an exact Fraction')
    numerator, denominator = value.numerator, value.denominator
    if square_root:
        if numerator < 0:
            raise ValueError('standard deviation requires nonnegative exact variance')
        scaled = numerator * SCALE * SCALE
        magnitude = isqrt(scaled // denominator)
        if 4 * scaled >= denominator * (2 * magnitude + 1)**2:
            magnitude += 1
        negative = False
    else:
        magnitude, remainder = divmod(abs(numerator) * SCALE, denominator)
        if 2 * remainder >= denominator:
            magnitude += 1
        negative = numerator < 0 and magnitude != 0
    whole, decimals = divmod(magnitude, SCALE)
    token = ('-' if negative else '') + str(whole) + '.' + str(decimals).zfill(8)
    if len(token) > MAX_TOKEN_BYTES:
        raise ValueError('fixed8 report token exceeds14 bytes')
    return token


def _rational(value):
    return '.' if value is None else str(value.numerator) + '/' + str(value.denominator)


def _statistics(values):
    selected = [value for value in values if value is not None]
    n, total, squares = len(selected), sum(selected), sum(value * value for value in selected)
    mean = Fraction(total, n) if n else None
    variance = Fraction(n * squares - total * total, n * (n - 1)) if n > 1 else None
    return {'n': n, 'sum': total, 'sum_squares': squares, 'mean': mean, 'variance': variance,
            'min': min(selected) if n else None, 'max': max(selected) if n else None}


def _report(records):
    text = '\n'.join(records) + '\n'
    if len(text) > MAX_REPORT_BYTES:
        raise ValueError('informat report exceeds417056 bytes')
    return text


def execute_title(step, version=2, *, trace=None):
    context = validate_step(step, version)
    if context['kind'] != 'informat_title':
        raise ValueError('TITLE executor requires informat_title')
    value = context['text']
    if trace is not None:
        trace.append('informat-title|reset' if value is None else 'informat-title|set|' + value.encode('ascii').hex())
    return value


def _records(title, header, prefix, trace):
    _title(title)
    if len(header) > MAX_HEADER_BYTES:
        raise ValueError('informat report header exceeds1055 bytes')
    result = [] if title is None else ['TITLE: ' + title]
    if trace is not None:
        if title is not None:
            trace.append(prefix + '|title|' + result[0].encode('ascii').hex())
        trace.append(prefix + '|header|' + header.encode('ascii').hex())
    result.append(header)
    return result


def execute_print(step, tables, title=None, version=2, *, trace=None):
    context = validate_step(step, version)
    if context['kind'] != 'labelled_print':
        raise ValueError('PRINT executor requires labelled_print')
    table, _ = _input(step, tables, context)
    if trace is not None:
        trace.append('labelled-print|input|' + context['input'] + '|' + str(len(table['rows'])))
    records = _records(title, ' '.join(json.dumps(context['labels'].get(name, name), ensure_ascii=True)
                                     for name in table['schema']), 'labelled-print', trace)
    for row in table['rows']:
        fields = [json.dumps(row[name].rstrip(' '), ensure_ascii=True) if descriptor['type'] == 'character'
                  else '.' if row[name] is None else str(_integer(row[name]))
                  for name, descriptor in table['schema'].items()]
        record = ' '.join(fields)
        if len(record) > MAX_ROW_BYTES:
            raise ValueError('labelled PRINT row exceeds415 bytes')
        records.append(record)
        if trace is not None:
            trace.append('labelled-print|row|' + record.encode('ascii').hex())
    reports = {'print_01.txt': _report(records)}
    validate_reports(reports)
    if trace is not None:
        trace.append('labelled-print|output|print_01.txt|' + str(len(reports['print_01.txt'])))
    return reports


def execute_means(step, tables, title=None, version=2, *, trace=None):
    context = validate_step(step, version)
    if context['kind'] != 'default_means':
        raise ValueError('MEANS executor requires default_means')
    table, names = _input(step, tables, context)
    if trace is not None:
        trace.append('default-means|input|' + context['input'] + '|' + str(len(table['rows'])))
    records = _records(title, 'variable n mean std min max', 'default-means', trace)
    for name in names:
        statistics = _statistics([_integer(row[name]) for row in table['rows']])
        fields = [json.dumps(name), str(statistics['n']),
                  '.' if statistics['mean'] is None else _fixed8(statistics['mean']),
                  '.' if statistics['variance'] is None else _fixed8(statistics['variance'], square_root=True),
                  '.' if statistics['min'] is None else str(statistics['min']),
                  '.' if statistics['max'] is None else str(statistics['max'])]
        record = ' '.join(fields)
        if len(record) > MAX_ROW_BYTES:
            raise ValueError('default MEANS row exceeds415 bytes')
        records.append(record)
        if trace is not None:
            trace.append('default-means|stats|' + name + '|' + '|'.join(map(str, [statistics['n'], statistics['sum'], statistics['sum_squares']]))
                         + '|' + _rational(statistics['mean']) + '|' + _rational(statistics['variance']))
            trace.append('default-means|row|' + record.encode('ascii').hex())
    reports = {'means_01.txt': _report(records)}
    validate_reports(reports)
    if trace is not None:
        trace.append('default-means|output|means_01.txt|' + str(len(reports['means_01.txt'])))
    return reports


def _quoted_fields(record, *, tokens=False):
    decoder, fields, position = json.JSONDecoder(), [], 0
    while position < len(record):
        if record[position] == '"':
            value, end = decoder.raw_decode(record, position)
            if (type(value) is not str or any(not 32 <= ord(char) <= 126 for char in value)
                    or json.dumps(value, ensure_ascii=True) != record[position:end]):
                raise ValueError('report JSON string is not canonical')
            fields.append((value, record[position:end]) if tokens else value)
            position = end
        else:
            end = record.find(' ', position)
            end = len(record) if end < 0 else end
            fields.append((record[position:end], record[position:end]) if tokens else record[position:end])
            position = end
        if position < len(record):
            if record[position] != ' ' or position + 1 == len(record) or record[position + 1] == ' ':
                raise ValueError('report fields require one separator without edge blanks')
            position += 1
    return fields


def validate_reports(reports):
    if (type(reports) is not dict or not 1 <= len(reports) <= 2
            or any(type(name) is not str or name not in ('print_01.txt', 'means_01.txt') for name in reports)):
        raise ValueError('informat reports require one or two fixed print/means artifact names')
    for name, text in reports.items():
        if (type(text) is not str or not text.endswith('\n') or len(text) > MAX_REPORT_BYTES
                or any(char != '\n' and not 32 <= ord(char) <= 126 for char in text)):
            raise ValueError('informat reports require bounded printableASCII LF records')
        records = text[:-1].split('\n')
        if records and records[0].startswith('TITLE: '):
            _title(records.pop(0)[7:])
        if not records or len(records[0]) > MAX_HEADER_BYTES or any(len(record) > MAX_ROW_BYTES for record in records[1:]):
            raise ValueError('informat report exceeds independent header/row caps')
        if name == 'means_01.txt':
            if records[0] != 'variable n mean std min max' or not 2 <= len(records) <= MAX_NUMERIC + 1:
                raise ValueError('default MEANS requires canonical header and1..8 variable rows')
            seen = set()
            for record in records[1:]:
                fields = _quoted_fields(record)
                if (len(fields) != 6 or not record.startswith('"') or not ordinary(fields[0]) or fields[0] in seen
                        or re.fullmatch(r'0|[1-9][0-9]{0,3}', fields[1]) is None or int(fields[1]) > MAX_ROWS
                        or any(token != '.' and (len(token) > MAX_TOKEN_BYTES or re.fullmatch(r'-?(?:0|[1-9][0-9]*)\.[0-9]{8}', token) is None or token == '-0.00000000') for token in fields[2:4])
                        or any(token != '.' and (re.fullmatch(r'0|-?[1-9][0-9]*', token) is None or abs(int(token)) > MAX_VALUE) for token in fields[4:])):
                    raise ValueError('default MEANS requires canonical numeric/statistic fields')
                if record != json.dumps(fields[0]) + ' ' + ' '.join(fields[1:]) or fields[3].startswith('-'):
                    raise ValueError('default MEANS fields require canonical quoting and nonnegative STD')
                if int(fields[1]) == 0 and fields[2:] != ['.', '.', '.', '.'] or int(fields[1]) == 1 and fields[3] != '.':
                    raise ValueError('default MEANS missing statistics disagree with N')
                seen.add(fields[0])
        else:
            try:
                header = _quoted_fields(records[0])
            except (ValueError, json.JSONDecodeError) as error:
                raise ValueError('invalid labelled PRINT header') from error
            if (not 1 <= len(header) <= MAX_COLUMNS or not records[0].startswith('"')
                    or records[0] != ' '.join(json.dumps(value, ensure_ascii=True) for value in header)
                    or any(type(value) is not str or not 1 <= len(value) <= 64 or not value.strip(' ') or '&' in value or '%' in value for value in header)
                    or len(records) > MAX_ROWS + 1):
                raise ValueError('labelled PRINT header/row count is invalid')
            for record in records[1:]:
                fields = _quoted_fields(record, tokens=True)
                if len(fields) != len(header):
                    raise ValueError('labelled PRINT row arity differs from header')
                for value, token in fields:
                    if token.startswith('\"'):
                        if len(value) > 32 or value.endswith(' '):
                            raise ValueError('PRINT character token retains padding or exceeds32 bytes')
                    elif token != '.' and (re.fullmatch(r'0|-?[1-9][0-9]*', token) is None or abs(int(token)) > MAX_VALUE):
                        raise ValueError('PRINT numeric token is outside the canonical integer policy')
    return reports


def _name(text):
    if not text.isascii() or not ordinary(text.lower()):
        raise ValueError('informat report requires ordinary ASCII names before normalization')
    return text.lower()


def _source(block, size):
    if (len(block) != size or any(statement.terminated is not True for statement in block)
            or any(not statement.text.isascii() or len(statement.text) > 16384 for statement in block)):
        raise ValueError('informat report source requires complete bounded ASCII statements')


def compile_title(statement):
    from .plan import Step, Operation, atom
    _source([statement], 1)
    match = re.fullmatch(r'title(?:\s+(.+))?', statement.text, re.I | re.ASCII | re.S)
    if match is None:
        raise ValueError('informat TITLE requires reset or one literal')
    value = None
    if match[1] is not None:
        value = atom(match[1])
        if value is None or value['kind'] != 'character':
            raise ValueError('informat TITLE requires one literal')
        value = value['value']
    step = Step('informat_title', '_null_', statement.line)
    step.operations = [Operation(step.kind, step.line, {'profile': TITLE_PROFILE, 'text': _title(value)})]
    validate_step(asdict(step))
    return step


def compile_print(block):
    from .parser import Kind
    from .plan import Step, Operation, atom
    _source(block, 3)
    header = re.fullmatch(r'proc\s+print\s+data\s*=\s*(' + NAME + r')\s+label\s+noobs', block[0].text, re.I | re.ASCII)
    if header is None or block[-1].text.lower() != 'run':
        raise ValueError('labelled PRINT requires DATA=,LABEL,NOOBS,one LABEL statement and RUN')
    matched = re.fullmatch(r'label\s+(.+)', block[1].text, re.I | re.ASCII | re.S)
    if matched is None:
        raise ValueError('PRINT requires one nonempty LABEL statement')
    quoted = r'("(?:[^"\n]|"")*"|\'(?:[^\'\n]|\'\')*\')'
    item = re.compile(r'\s*(' + NAME + r')\s*=\s*' + quoted + r'(?=\s|$)', re.ASCII)
    position, labels = 0, []
    while position < len(matched[1]):
        found = item.match(matched[1], position)
        if found is None or len(labels) >= MAX_COLUMNS:
            raise ValueError('PRINT labels require fully consumed bounded name/literal declarations')
        labels.append({'name': _name(found[1]), 'text': atom(found[2])['value']})
        position = found.end()
        if not matched[1][position:].strip():
            break
    name = _name(header[1])
    step = Step('labelled_print', name, block[0].line, inputs=[name])
    step.operations = [Operation(step.kind, step.line, {'profile': PRINT_PROFILE, 'labels': labels,
                                                     'source_lines': [block[1].line, block[-1].line]})]
    validate_step(asdict(step))
    return step


def compile_means(block):
    from .plan import Step, Operation
    _source(block, 2)
    header = re.fullmatch(r'proc\s+means\s+data\s*=\s*(' + NAME + ')', block[0].text, re.I | re.ASCII)
    if header is None or block[-1].text.lower() != 'run':
        raise ValueError('default MEANS requires DATA= and explicit RUN only')
    name = _name(header[1])
    step = Step('default_means', name, block[0].line, inputs=[name])
    step.operations = [Operation(step.kind, step.line, {'profile': MEANS_PROFILE, 'source_lines': [block[-1].line]})]
    validate_step(asdict(step))
    return step
