"""Opt-in exact comparison input for ordered logical ASCII log records."""
import hashlib
import json


def read_expected_log(path):
    raw = path.read_bytes()
    if len(raw) > 1048576:
        raise ValueError('expected log manifest exceeds one MiB')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate expected log JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('invalid expected log JSON constant')
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('expected log requires bounded valid JSON') from error
    if (type(value) is not list or len(value) > 1000
            or any(type(record) is not str or len(record) > 4096
                   or any(not 32 <= ord(char) <= 126 for char in record) for record in value)):
        raise ValueError('expected log requires at most1000 bounded printableASCII records')
    return value, hashlib.sha256(raw).hexdigest()
