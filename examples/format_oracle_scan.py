"""Independent finite-source oracle scanner; no translator/parser imports."""

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
        if statement.lower() in ('cards', 'datalines'):
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


