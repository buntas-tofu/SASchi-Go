"""Bounded logical PRINT artifacts and an opt-in exact text comparator."""
import hashlib
import json
import re

REPORT_BASENAME = 'print.txt'
REPORT_CONTRACT = 'numeric-space-fixed12-v1'
MIXED_REPORT_CONTRACT = 'ascii-titled-mixed-integer-v1'
REPORT_COMPARISON_CONTRACT = 'exact-basename-set-utf8-bytes-v1'
MAX_REPORT_BYTES = 417056


def validate_reports(reports):
    if type(reports) is not dict or set(reports) != {REPORT_BASENAME}:
        raise ValueError('logical PRINT requires exactly the print.txt artifact')
    text = reports[REPORT_BASENAME]
    if (type(text) is not str or not text.isascii() or not text.endswith('\n')
            or len(text) > MAX_REPORT_BYTES
            or any(c != '\n' and not 32 <= ord(c) <= 126 for c in text)):
        raise ValueError('logical PRINT requires bounded printable ASCII LF text with final newline')
    records = text[:-1].split('\n')
    if (not 1 <= len(records) <= 1001 or not records[0] or len(records[0]) > 1055
            or any(len(record) > 415 for record in records[1:])
            or any(not record or record != record.strip(' ') for record in records)):
        raise ValueError('logical PRINT exceeds its header, row or record limits')
    return reports


def report_manifest(reports, *, contract=REPORT_CONTRACT):
    if contract == REPORT_CONTRACT:
        validate_reports(reports)
    elif contract == MIXED_REPORT_CONTRACT:
        from .mixed_reports import validate_reports as validate_mixed_reports
        validate_mixed_reports(reports)
    else:
        raise ValueError('unknown logical report contract')
    return {name: {'sha256': hashlib.sha256(text.encode('ascii')).hexdigest(),
                   'bytes': len(text), 'records': text.count('\n')}
            for name, text in reports.items()}


def read_expected_reports(path, *, contract=REPORT_CONTRACT):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('expected reports contain a duplicate artifact name')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('invalid expected report JSON constant')
    if contract not in (REPORT_CONTRACT, MIXED_REPORT_CONTRACT):
        raise ValueError('unknown expected report contract')
    maximum = 2097152 if contract == MIXED_REPORT_CONTRACT else 1048576
    raw = path.read_bytes()
    if len(raw) > maximum:
        if contract == MIXED_REPORT_CONTRACT:
            raise ValueError('expected mixed report manifest exceeds two MiB')
        raise ValueError('expected report manifest exceeds one MiB')
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('expected reports require bounded valid JSON text') from exc
    if (contract == MIXED_REPORT_CONTRACT and
            (type(value) is not dict or not 1 <= len(value) <= 2)):
        raise ValueError('expected mixed reports require one or two basename-to-text entries')
    if contract == REPORT_CONTRACT and (type(value) is not dict or len(value) != 1):
        raise ValueError('expected reports require one complete basename-to-text map')
    for name, text in value.items():
        if (type(name) is not str or not name.isascii() or not 5 <= len(name) <= 64
                or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*\.txt', name, re.ASCII) is None
                or name[:-4].lower() in {'con', 'prn', 'aux', 'nul'}
                or name[:-4].lower() in {p + str(i) for p in ('com', 'lpt') for i in range(1, 10)}):
            raise ValueError('expected report name requires a safe literal .txt basename')
        if type(text) is not str:
            raise ValueError('expected report contents must be text')
        try:
            text.encode('utf-8')
        except UnicodeError as exc:
            raise ValueError('expected report contents require valid UTF8 text') from exc
    return value, hashlib.sha256(raw).hexdigest()


def reports_equal(actual, expected):
    if type(actual) is not dict or type(expected) is not dict or set(actual) != set(expected):
        return False
    try:
        return all(type(actual[name]) is str and type(expected[name]) is str
                   and actual[name].encode('utf-8') == expected[name].encode('utf-8')
                   for name in actual)
    except UnicodeError:
        return False
