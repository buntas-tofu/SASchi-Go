"""Independent pinned hand expectations; derived vendor bodies stay temporary."""
from copy import deepcopy
from decimal import Decimal, localcontext, ROUND_HALF_UP
import json
import re

from vendor_invalue_lex import SOURCE_SHA256, checksum, scan

LINES = [13, 14, 20, 22, 23, 24, 34, 35, 36, 37, 39, 40, 41]


def build(original):
    if len(original) != 1802 or checksum(original) != SOURCE_SHA256:
        raise ValueError('whole immutable original required')
    statements, events = scan(original.decode('ascii'))
    assert [statement['line'] for statement in statements] == LINES
    texts = [statement['text'] for statement in statements]
    normalized = [' '.join(text.lower().split()) for text in texts]
    assert normalized[0] == 'proc format' and normalized[2] == normalized[6] == normalized[10] == normalized[12] == 'run'
    assert normalized[3] == 'data evals'
    assert normalized[4] == 'input id $ @6 string $9. @6 evaluation eval.'
    assert normalized[5] == 'datalines'
    assert normalized[8] == 'proc print data=evals label noobs'
    assert normalized[11] == 'proc means data=evals'
    definition = re.fullmatch(r'invalue\s+eval\s+(.+)', texts[1], re.I | re.S)
    pairs = re.findall(r"'([^']+)'\s*=\s*([0-9]+)", definition[1])
    assert len(pairs) == 4
    mapping = {raw: int(value) for raw, value in pairs}
    assert list(mapping.values()) == [4, 3, 2, 1]
    assert max(map(len, mapping)) == 9
    payload, = [event for event in events if event['kind'] == 'opaque_data']
    assert payload['line'] == 25 and payload['terminator_line'] == 33 and len(payload['records']) == 8
    schema = {'id': {'type': 'character', 'length': 8},
              'string': {'type': 'character', 'length': 9},
              'evaluation': {'type': 'number', 'length': 8}}
    rows = []
    for card in payload['records']:
        assert len(card) == 14 and card[4] == ' ' and re.fullmatch(r'[0-9]{4}', card[:4])
        raw = card[5:14]
        token = raw.rstrip(' ')
        value = mapping[token] if token in mapping else int(token)
        rows.append({'id': card[:4].ljust(8), 'string': raw.lstrip(' ').ljust(9), 'evaluation': float(value)})
    values = [int(row['evaluation']) for row in rows]
    assert values == [3, 2, 4, 1, 2, 4, 3, 3] and sum(values) == 22 and sum(value*value for value in values) == 68
    assert sum((a-b)**2 for i,a in enumerate(values) for b in values[i+1:]) == 60
    title_match = re.fullmatch(r"title\s+'([^']+)'", texts[7], re.I)
    title = title_match[1]
    labels = {name.lower(): value for name,value in re.findall(r'([A-Za-z_]+)\s*=\s*"([^"]+)"', texts[9][5:])}
    assert list(labels) == ['evaluation', 'string']
    header = ' '.join(json.dumps(labels.get(name, name)) for name in schema)
    print_records = ['TITLE: ' + title, header]
    print_records += [' '.join([json.dumps(row['id'].rstrip(' ')), json.dumps(row['string'].rstrip(' ')), str(int(row['evaluation']))]) for row in rows]
    with localcontext() as context:
        context.prec = 80
        mean = str((Decimal(11)/4).quantize(Decimal('.00000001'), rounding=ROUND_HALF_UP))
        std = str((Decimal(15)/14).sqrt().quantize(Decimal('.00000001'), rounding=ROUND_HALF_UP))
    assert mean == '2.75000000' and std == '1.03509834'
    means_records = ['TITLE: ' + title, 'variable n mean std min max', '"evaluation" 8 '+mean+' '+std+' 1 4']
    artifacts = {'print_01.txt': '\n'.join(print_records)+'\n', 'means_01.txt': '\n'.join(means_records)+'\n'}
    result = {'datasets': {'evals': {'schema': deepcopy(schema), 'rows': rows}}, 'log': [], 'reports': artifacts}
    accounting = {'language_statements': 13, 'opaque_payloads': 1, 'steps': 5,
                  'input_records': 8, 'data_iterations': 8, 'input_attempts': 9, 'implicit_outputs': 8,
                  'title_sets': 1, 'prints': 1, 'means': 1, 'report_records': [10,3], 'final_title': title}
    trace = []
    for i in range(9):
        trace.append({'kind':'formatted_input','line':23,'attempt':i+1,'complete':i<8})
        if i<8: trace.append({'kind':'formatted_output','line':23,'observation':i+1})
    trace.append('informat-title|set|' + title.encode().hex())
    trace += ['labelled-print|input|evals|8', 'labelled-print|title|' + print_records[0].encode().hex(),
              'labelled-print|header|' + header.encode().hex()]
    trace += ['labelled-print|row|' + row.encode().hex() for row in print_records[2:]]
    trace += ['labelled-print|output|print_01.txt|' + str(len(artifacts['print_01.txt']))]
    trace += ['default-means|input|evals|8', 'default-means|title|' + means_records[0].encode().hex(),
              'default-means|header|' + means_records[1].encode().hex(),
              'default-means|stats|evaluation|8|22|68|11/4|15/14',
              'default-means|row|' + means_records[2].encode().hex(),
              'default-means|output|means_01.txt|' + str(len(artifacts['means_01.txt']))]
    assert len(trace) == 36
    return result, accounting, trace
