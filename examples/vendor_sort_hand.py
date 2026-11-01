"""Pinned hand expectations for the approved character/report whole target.

No translator/helper import and no vendor rows or program are embedded here.
Derived bodies are written only to a new task-owned temporary output directory.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from vendor_sort_lex import SOURCE_SHA256, checksum, scan, classify


ORDER = [3, 5, 4, 10, 11, 12, 13, 14, 2, 1, 6, 7, 8, 9]
KINDS = ['data', 'infile', 'input', 'datalines4', 'run', 'title_set',
         'proc_print', 'run', 'title_reset', 'proc_sort', 'by', 'run',
         'title_set', 'proc_print', 'run', 'title_reset']
LINES = [14, 15, 16, 20, 36, 38, 39, 40, 41, 43, 44, 45, 47, 48, 49, 50]


def title_literal(statement):
    value = statement[5:].strip()
    delimiter = value[0]
    if delimiter not in ('"', "'") or value[-1] != delimiter:
        raise ValueError('expected one SAS title literal')
    value = value[1:-1].replace(delimiter * 2, delimiter)
    if not 1 <= len(value) <= 128 or not value.strip(' '):
        raise ValueError('title policy')
    if any(not 32 <= ord(ch) <= 126 for ch in value):
        raise ValueError('printable ASCII title required')
    if '&' in value or '%' in value:
        raise ValueError('macro-sensitive title text is outside DECISION-02')
    return value


def report(table, title):
    columns = list(table['schema'])
    header = 'obs ' + ' '.join(columns)
    lines = ['TITLE: ' + title, header]
    for ordinal, row in enumerate(table['rows'], 1):
        fields = []
        for name in columns:
            descriptor, value = table['schema'][name], row[name]
            if descriptor['type'] == 'character':
                fields.append(json.dumps(value.rstrip(' '), ensure_ascii=True))
            else:
                if value is not None and (not value.is_integer() or abs(value) > 2147483647):
                    raise ValueError('integer report policy')
                fields.append('.' if value is None else str(int(value)))
        line = str(ordinal) + ' ' + ' '.join(fields)
        if len(line.encode()) > 415:
            raise ValueError('data-row resource policy')
        lines.append(line)
    text = '\n'.join(lines) + '\n'
    if len(header.encode()) > 1055 or len(text.encode()) > 417056:
        raise ValueError('report resource policy')
    return text


def build(source_bytes):
    if checksum(source_bytes) != SOURCE_SHA256 or len(source_bytes) != 1896:
        raise ValueError('the exact original target is required')
    statements, events = scan(source_bytes.decode('utf-8'))
    assert [classify(item['text']) for item in statements] == KINDS
    assert [item['line'] for item in statements] == LINES
    payloads = [item for item in events if item['kind'] == 'opaque_data']
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload['line'] == 21 and payload['terminator_line'] == 35
    assert len(payload['records']) == 14
    columns = ['name', 'subject', 'score']
    schema = {'name': {'type': 'character', 'length': 7},
              'subject': {'type': 'character', 'length': 7},
              'score': {'type': 'number', 'length': 8}}
    # This is the hand descriptor expectation, checked against the actual syntax.
    declaration = statements[2]['text']
    terms = re.findall(r'([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*\$([0-9]+)\.)?',
                       declaration[5:], flags=re.ASCII)
    assert [(name.lower(), width) for name, width in terms] == [
        ('name', '7'), ('subject', '7'), ('score', '')]
    rows = []
    for record in payload['records']:
        assert len(record.encode('ascii')) <= 80
        assert not any(ch in record for ch in "\"'")
        fields = [field.strip(' ') for field in record.split(',')]
        assert len(fields) == 3 and all(len(field) <= 7 for field in fields[:2])
        assert all(field != '.' for field in fields[:2])
        assert re.fullmatch(r'[0-9]+', fields[2], flags=re.ASCII)
        rows.append(dict(zip(columns, [fields[0].ljust(7), fields[1].ljust(7),
                                      float(fields[2])])))
    raw = {'schema': deepcopy(schema), 'rows': rows}
    ordered = {'schema': deepcopy(schema),
               'rows': [deepcopy(rows[index - 1]) for index in ORDER]}
    # The ordinal pin was hand-derived before the implementation. This separate
    # consistency check checks ASCII keys and stable ties rather than supplying it.
    assert ORDER == sorted(range(1, 15),
                           key=lambda i: (rows[i - 1]['name'].encode(),
                                          rows[i - 1]['subject'].encode(), i))
    first_title = title_literal(statements[5]['text'])
    second_title = title_literal(statements[12]['text'])
    reports = {'print_01.txt': report(raw, first_title),
               'print_02.txt': report(ordered, second_title)}
    result = {'datasets': {'classtest': raw, 'classtest_sort': ordered},
              'log': [], 'reports': reports}
    accounting = {'language_statements': 16, 'opaque_payloads': 1, 'steps': 8,
                  'input_records': 14, 'data_iterations': 14, 'input_attempts': 15,
                  'implicit_outputs': 14, 'sort_rows': 14,
                  'sort_source_ordinals': ORDER,
                  'title_sets': 2, 'title_resets': 2, 'prints': 2,
                  'report_records': [16, 16], 'final_title': None}
    trace = [{'event': 'data_begin', 'line': 14, 'table': 'classtest'}]
    for ordinal in range(1, 15):
        trace.append({'event': 'input_attempt', 'line': 16, 'record': ordinal,
                      'record_line': 20 + ordinal, 'eof': False})
        trace.append({'event': 'implicit_output', 'table': 'classtest',
                      'observation': ordinal})
    trace.extend([
        {'event': 'input_attempt', 'line': 16, 'record': 15, 'eof': True},
        {'event': 'data_end', 'line': 36, 'table': 'classtest', 'rows': 14},
        {'event': 'title_set', 'line': 38, 'text': first_title},
        {'event': 'print', 'line': 39, 'table': 'classtest',
         'report': 'print_01.txt', 'rows': 14, 'title': first_title},
        {'event': 'title_reset', 'line': 41},
        {'event': 'sort', 'line': 43, 'source': 'classtest',
         'destination': 'classtest_sort', 'source_ordinals': ORDER},
        {'event': 'title_set', 'line': 47, 'text': second_title},
        {'event': 'print', 'line': 48, 'table': 'classtest_sort',
         'report': 'print_02.txt', 'rows': 14, 'title': second_title},
        {'event': 'title_reset', 'line': 50},
    ])
    assert len(trace) == 38
    return result, accounting, trace
