"""Independent finite-source lexer for the INVALUE/report review oracle.

This is review code, not a translator implementation or a general SAS parser.
External source remains in its authorized cache. The public summary emits only
source hashes, statement classifications and physical-line accounting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


SOURCE_SHA256 = 'eae2264db49ea95677de658216903cb0685970538cf7c3fe9a676c7f4e173493'


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def scan(source):
    """Consume every code character and isolate opaque DATALINES records."""
    events = []
    statements = []
    current = []
    first = None
    i = 0
    quote = None
    while i < len(source):
        ch = source[i]
        if quote is not None:
            current.append(ch)
            if ch == quote:
                if i + 1 < len(source) and source[i + 1] == quote:
                    current.append(source[i + 1])
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if source.startswith('/*', i):
            end = source.find('*/', i + 2)
            if end < 0:
                raise ValueError('unterminated block comment')
            current.append(' ')
            i = end + 2
            continue
        if ch == '*' and not ''.join(current).strip():
            end = source.find(';', i + 1)
            if end < 0:
                raise ValueError('unterminated statement comment')
            current = []
            first = None
            i = end + 1
            continue
        if not ch.isspace() and first is None:
            first = i
        if ch in ('"', "'"):
            quote = ch
            current.append(ch)
            i += 1
            continue
        if ch != ';':
            current.append(ch)
            i += 1
            continue
        statement = ''.join(current).strip()
        if statement:
            line = source.count('\n', 0, first) + 1
            item = {'line': line, 'text': statement}
            statements.append(item)
            events.append({'kind': 'statement', **item})
        else:
            raise ValueError('unowned empty statement')
        current = []
        first = None
        i += 1
        if statement.lower() == 'datalines':
            start = source.find('\n', i)
            if start < 0 or source[i:start].strip():
                raise ValueError('DATALINES records must begin on the next line')
            pos = start + 1
            rows = []
            while pos < len(source):
                end = source.find('\n', pos)
                if end < 0:
                    end = len(source)
                record = source[pos:end]
                if record.endswith('\r'):
                    record = record[:-1]
                if record == ';':
                    events.append({'kind': 'opaque_data', 'line': source.count('\n', 0, start + 1) + 1,
                                   'terminator_line': source.count('\n', 0, pos) + 1,
                                   'records': rows})
                    i = end + (end < len(source))
                    break
                rows.append(record)
                pos = end + (end < len(source))
            else:
                raise ValueError('missing DATALINES terminator')
    if quote is not None or ''.join(current).strip():
        raise ValueError('unterminated source statement')
    return statements, events

