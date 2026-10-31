"""Versioned, target-independent operations for the executable SAS subset.

Names are case-insensitive strings, numbers are binary64 values, and steps own
local state. Unsupported statements remain tickets; no backend can clear them.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from sas_semantics import sas_put_literals, sas_put_character_list, sas_put_numeric_list, sas_do_counted, SAS_BITWISE_ARITY
from .functions import FUNCTIONS, format_token, FORMATS, function_call_lines, substr_context_errors, catx_arguments_allowed, LAG_FUNCTIONS, validate_lag_calls, expression_nodes
from .trim_strip import validate_step as validate_trim_step
from .parser import Kind, ParseError, Statement, split_statements, tokenize
from .operations import walk_operations as _walk_operations
from .rules import route_function, route_statement
from .arrays import declaration as array_declaration, validate_step as validate_array_step
from .counted import parse_control, validate_step as validate_counted_step
from .put_mixed import validate_items as validate_mixed_put_items
from .input_list import names_valid as input_names_valid, source_records, validate_step as validate_input_step
from .input_numeric import PROFILE as INPUT_PROFILE, parse_terms as parse_input_terms, parse_infile, validate_step as validate_numeric_input_step
from .projection import declaration as projection_declaration, dataset as projection_dataset, validate_step as validate_projection_step
from .numeric_pipeline import PROFILE as PIPELINE_PROFILE
from .binary64 import PROFILE as BINARY64_PROFILE, ROWS_PROFILE as BINARY64_ROWS_PROFILE, FUNCTIONS as BINARY64_FUNCTIONS, validate_step as validate_binary64_step
from .sql_create import parse_create as parse_sql_create, validate_step as validate_sql_create

NAME = r"[A-Za-z_][A-Za-z0-9_]{0,31}"
NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\Z")
CALL = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)$", re.S)
_FORMAT_NAMED = re.compile(r"^([A-Za-z][A-Za-z0-9_]*?)(\d*)\.$")
_FORMAT_NUMERIC = re.compile(r"^(?:(\d+)\.(\d*)|(\d+)\.)$")


@dataclass
class Ticket:
    line: int
    statement: str
    construct: str
    reason: str


@dataclass
class Operation:
    kind: str
    line: int
    args: dict


@dataclass
class Step:
    kind: str
    name: str
    line: int
    inputs: list[str] = field(default_factory=list)
    by: list[str] = field(default_factory=list)
    operations: list[Operation] = field(default_factory=list)
    nodupkey: bool = False
    where: dict | None = None
    retained: dict = field(default_factory=dict)
    lengths: dict = field(default_factory=dict)
    display_names: dict = field(default_factory=dict)


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    tickets: list[Ticket] = field(default_factory=list)
    matched: list[tuple[str, str, int]] = field(default_factory=list)
    version: int = 2

    @property
    def blocked(self):
        return bool(self.tickets)

    def to_dict(self):
        return asdict(self)


def atom(text):
    text = text.strip()
    if len(text) >= 2 and text[0] in ("'", '"') and text[-1] == text[0]:
        quote = text[0]
        interior = text[1:-1]
        if quote not in interior.replace(quote * 2, ''):
            return {"kind": "character", "value": interior.replace(quote * 2, quote)}
    if re.fullmatch(r"(?:first|last)\." + NAME, text, re.I) or text.lower() == '_n_':
        return {"kind": "automatic", "value": text.lower()}
    if re.fullmatch(r'\.[A-Za-z_]', text):
        return {'kind': 'tagged_missing', 'value': {'missing': text[1].upper()}}
    if text == ".":
        return {"kind": "missing", "value": None}
    if NUMBER.fullmatch(text):
        value = float(text)
        if math.isfinite(value):
            return {"kind": "number", "value": value}
    if re.fullmatch(NAME, text):
        return {"kind": "variable", "value": text.lower()}
    return None


def _arithmetic_positions(text, operators='+-'):
    """Binary depth-zero offsets, excluding numeric exponent/unary signs."""
    depth, quote, positions = 0, "", []
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "'\"":
            quote = char
            continue
        if char in "({[":
            depth += 1
        elif char in ")}]":
            depth -= 1
        elif char in operators and depth == 0:
            if char == '*' and (text[index:index + 2] == '**' or index and text[index - 1] == '*'):
                continue
            before = text[:index].rstrip()
            if not before or before[-1] in '+-/*(,':
                continue
            if char in '+-' and re.search(r'(?<![\w.])(?:\d+(?:\.\d*)?|\.\d+)[eE]$', before):
                continue
            positions.append(index)
    return positions


def _power_positions(text):
    """Top-level powers, split at the first for SAS right association."""
    depth, quote, positions = 0, '', []
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = ''
        elif char in "'\"":
            quote = char
        elif char in '({[':
            depth += 1
        elif char in ')}]':
            depth -= 1
        elif not depth and text[index:index + 2] == '**':
            positions.append(index)
    return positions


def _split_args(text):
    """Comma-split a call's argument list, respecting quotes and nesting."""
    parts, depth, quote, current = [], 0, "", ""
    for char in text:
        if quote:
            current += char
            if char == quote:
                quote = ""
            continue
        if char in "'\"":
            quote = char
        elif char in "({[":
            depth += 1
        elif char in ")}]":
            depth -= 1
            if depth < 0:
                return None
        elif char == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        current += char
    if quote or depth != 0:
        return None
    parts.append(current)
    return [part.strip() for part in parts]


def _format_argument(text):
    """A format token, when this slice has a gate for it. Otherwise None."""
    text = text.strip()
    match = _FORMAT_NUMERIC.fullmatch(text)
    if match:
        return format_token("", int(match[1] or match[3]), int(match[2] or 0))
    if text.startswith("$"):
        return None  # dollar formats have no gate yet
    match = _FORMAT_NAMED.fullmatch(text)
    if match:
        name = match[1].lower()
        if name not in FORMATS:
            return None
        return format_token(name, int(match[2] or 0), 0)
    return None


def _argument(text, allow_format=False, strict=False):
    """One argument: a format token only in a position this function declares."""
    if allow_format:
        value = _format_argument(text)
        if value is not None:
            return value
    return expression(text, strict=strict)


def call(text, strict=False):
    """Parse a call to a wired function, or None when it is not wired."""
    match = CALL.fullmatch(text.strip())
    if not match:
        return None
    name = match[1].lower()
    spec = FUNCTIONS.get(name)
    if spec is None:
        return None
    parts = _split_args(match[2])
    if parts is None or len(parts) < spec.min_args:
        return None
    if spec.max_args >= 0 and len(parts) > spec.max_args:
        return None
    # B1 admits a single atom. Refuse nested syntax without recursive parsing.
    values = ([atom(parts[0])] if name in ('trim', 'strip') else
              [_argument(part, index in spec.format_args, strict) for index, part in enumerate(parts)])
    if any(value is None for value in values):
        return None
    return {"kind": "call", "name": name, "args": values}


def operand(text, _depth=0, strict=False):
    """One expression operand: an atom or a wired call."""
    value = atom(text)
    if value is not None:
        return value
    summed = re.fullmatch(r'sum\s*\(\s*of\s+(' + NAME + r')\s*(?:\{\s*\*\s*\}|\[\s*\*\s*\]|\(\s*\*\s*\))\s*\)', text, re.I)
    if summed:
        return {'kind': 'array_sum', 'name': summed[1].lower()}
    value = call(text, strict)
    if value is not None:
        return value
    indexed = re.match(r'(' + NAME + r')\s*([{\[])', text, re.I)
    if indexed:
        stack, quote, complete = [], '', False
        for pos in range(indexed.end() - 1, len(text)):
            char = text[pos]
            if quote:
                if char == quote:
                    quote = ''
                continue
            if char in "'\"":
                quote = char
            elif char in '({[':
                stack.append(char)
                if len(stack) > 32:
                    return None
            elif char in ')}]':
                if not stack or stack.pop() != {')': '(', '}': '{', ']': '['}[char]:
                    return None
                if not stack:
                    complete = pos == len(text) - 1
                    break
        if not complete:
            return None
        index = expression(text[indexed.end():-1], _depth + 1, strict)
        if index is not None:
            return {'kind': 'array_get', 'name': indexed[1].lower(), 'index': index}
    return None


def _concat_parts(text):
    """Split only complete depth-zero operators outside quoted literals."""
    parts, depth, quote, start, index = [], 0, None, 0, 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 2
                    continue
                quote = None
        elif char in "'\"":
            quote = char
        elif char in '({[':
            depth += 1
        elif char in ')}]':
            depth -= 1
            if depth < 0:
                return []
        elif depth == 0 and char in '!|':
            if text[index:index + 2] not in ('!!', '||'):
                return []
            parts.append(text[start:index].strip())
            index += 2
            start = index
            continue
        index += 1
    if quote or depth:
        return []
    return parts + [text[start:].strip()] if parts else None


def _string_nodes(value):
    if isinstance(value, dict):
        if value.get('kind') == 'concat' or value.get('kind') == 'call' and value.get('name') == 'catx':
            yield value
        for child in value.values():
            yield from _string_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _string_nodes(child)


def expression(text, _depth=0, strict=False):
    text = text.strip()
    # A failed depth-budget split must never regroup a product and hide an
    # invalid intermediate behind zero or missing in another parse tree.
    unquoted = re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", '', text)
    strict = strict or '*' in unquoted
    if _depth > 32:
        return None
    parts = _concat_parts(text)
    if parts is not None:
        if not 2 <= len(parts) <= 32:
            return None
        values = [operand(part, strict=strict) for part in parts]
        if any(value is None for value in values):
            return None
        return {'kind': 'concat', 'args': values}
    value = operand(text, _depth, strict)
    if value is not None:
        return value
    if text.startswith('(') and text.endswith(')'):
        depth, quote, enclosed = 0, '', True
        for index, char in enumerate(text):
            if quote:
                if char == quote: quote = ''
            elif char in "'\"": quote = char
            elif char == '(': depth += 1
            elif char == ')':
                depth -= 1
                if depth == 0 and index != len(text) - 1: enclosed = False
        if enclosed and depth == 0 and not quote:
            return expression(text[1:-1], _depth + 1, strict)
    for operators in ('+-', '/*'):
        positions = _arithmetic_positions(text, operators)
        # New array expressions use deterministic precedence instead of trying
        # alternative binary splits after a depth/budget refusal.
        if strict or re.search(NAME + r'\s*[{\[]', text):
            positions = positions[-1:]
        for position in reversed(positions):
            left = expression(text[:position], _depth + 1, strict)
            right = expression(text[position + 1:], _depth + 1, strict)
            if left is not None and right is not None:
                return {'kind': 'arithmetic', 'left': left, 'op': text[position], 'right': right}
            if strict or re.search(NAME + r'\s*[{\[]', text):
                return None
    powers = _power_positions(text)
    if powers:
        # SAS GroupI unary signs and powers evaluate right to left.
        if text[0] in '+-':
            child = expression(text[1:], _depth + 1, True)
            if child is None:
                return None
            return child if text[0] == '+' else {'kind': 'arithmetic', 'op': '-',
                'left': {'kind': 'number', 'value': 0.0}, 'right': child}
        position = powers[0]
        left = expression(text[:position], _depth + 1, True)
        right = expression(text[position + 2:], _depth + 1, True)
        if left is not None and right is not None:
            return {'kind': 'arithmetic', 'op': '**', 'left': left, 'right': right}
    return None


def predicate(text, strict=False):
    value = expression(text, strict=strict)
    if value is not None:
        return {'left': value, 'op': 'truth'}
    match = re.fullmatch(r'(.+?)\s*(<=|>=|\^=|~=|<>|=|<|>|\beq\b|\bne\b|\blt\b|\bgt\b|\ble\b|\bge\b)\s*(.+)', text, re.I)
    if match and expression(match[1], strict=strict) is not None and expression(match[3], strict=strict) is not None:
        return {'left': expression(match[1], strict=strict), 'op': match[2].lower(), 'right': expression(match[3], strict=strict)}
    return None


def action(text, line, strict=False):
    match = re.fullmatch(r'(' + NAME + r')\s*\+\s*(.+)', text)
    reserved = {'_n_', '_error_', '_all_', '_numeric_', '_character_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_'}
    if match and match[1].lower() not in reserved:
        value = expression(match[2], strict=strict)
        if value is not None:
            return Operation('sum_statement', line, {'name': match[1].lower(), 'value': value})
    match = re.fullmatch(r'output(?:\s+(' + NAME + r'))?', text, re.I)
    if match:
        return Operation('output', line, {'target': match[1].lower() if match[1] else None})
    indexed = re.fullmatch(r'(.+?)\s*=\s*(.+)', text)
    if indexed:
        target, value = operand(indexed[1].strip(), strict=strict), expression(indexed[2], strict=strict)
        if target is not None and target['kind'] == 'array_get' and value is not None:
            return Operation('array_set', line, {'name': target['name'], 'index': target['index'], 'value': value})
    match = re.fullmatch(r'(' + NAME + r')\s*=\s*(.+)', text)
    if match and match[1].lower() != '_n_':
        value = expression(match[2], strict=strict)
        # ROUND keeps its dedicated operation: the rule id DS-012 is recorded on
        # that path, and the C++ pilot emits its scalar call from it.
        if value is not None and not (value.get('kind') == 'call' and value['name'] == 'round'):
            return Operation('assign', line, {'name': match[1].lower(), 'value': value})
    return None


def walk_operations(ops, *, all_containers=False):
    """Expose shared traversal nodes as compiler operations."""
    for op in _walk_operations(ops, all_containers=all_containers):
        yield op if isinstance(op, Operation) else Operation(**op)


def put_known_types(ops):
    """Source-order types for PUT routing, with no descriptor-only guesses."""
    known = {}

    def expression_type(expr):
        kind = expr['kind']
        if kind in ('number', 'missing', 'tagged_missing', 'automatic', 'array_get', 'array_sum', 'array_current'):
            return 'number'
        if kind in ('character', 'concat'):
            return 'character'
        if kind == 'variable':
            return known.get(expr['value'])
        if kind == 'call':
            return FUNCTIONS[expr['name']].returns
        if kind == 'arithmetic' and all(expression_type(expr[key]) == 'number' for key in ('left', 'right')):
            return 'number'
        return None

    for previous in walk_operations(ops):
        args, kind = previous.args, previous.kind
        if kind == 'declare':
            spec = args['spec']
            known.setdefault(args['name'], spec if isinstance(spec, str) else spec['type'])
        elif kind in ('array_declare', 'input_list', 'input_numeric'):
            for name in args['names']:
                known.setdefault(name, 'number')
        elif kind == 'put_numeric_list':
            for name in args.get('discover', []):
                known.setdefault(name, 'number')
        elif kind in ('assign', 'round', 'sum_statement'):
            known.setdefault(args['name'], 'number' if kind in ('round', 'sum_statement') else expression_type(args['value']))
    return known


def contains_put(ops, kinds):
    """Inspect structural containers conservatively for source-wide guards."""
    return any(op.kind in kinds for op in walk_operations(ops, all_containers=True))


def bind_current(node, name):
    """Bind only bare references to this loop's array; leave other arrays scoped."""
    if isinstance(node, dict):
        if node.get('kind') == 'variable' and node.get('value') == name:
            node.clear()
            node.update(kind='array_current', name=name)
        elif node.get('kind') == 'assign' and node['args']['name'] == name:
            node['kind'] = 'array_current_set'
        for child in node.values():
            bind_current(child, name)
    elif isinstance(node, list):
        for child in node:
            bind_current(child, name)


def compile_plan(source: str) -> Plan:
    plan, step, context, active_do = Plan(), None, None, None
    character_put_matches = {}
    numeric_rules = {}
    infile_configs = {}
    pending_if, chain_length, pending_end = None, 0, None
    do_parents = []
    inline_pending = False
    sql_closed = set()

    def append_operation(op):
        if active_do is None:
            step.operations.append(op)
            return op.args
        serialized = asdict(op)
        if active_do.kind == 'do_over':
            bind_current(serialized, active_do.args['name'])
        active_do.args['body'].append(serialized)
        return serialized['args']

    def reject(st, construct, reason):
        plan.tickets.append(Ticket(st.line, st.text, construct, reason))

    def put_action(st):
        """Reuse every bounded PUT path with original token offsets/source text."""
        text = st.text
        if re.fullmatch(r'put\s+_all_', text, re.I):
            plan.matched.append(('put-all', 'DS-025', st.line))
            return Operation('put_all', st.line, {})
        items = st.tokens[1:]
        if items and all(item.kind == Kind.STRING for item in items):
            literals = [item.text for item in items]
            try:
                sas_put_literals(literals)
            except ValueError as exc:
                reject(st, 'put', str(exc))
            else:
                plan.matched.append(('put-literal', 'DS-023', st.line))
                return Operation('put_literal', st.line, {'literals': literals})
            return None
        if items and all(item.kind == Kind.STRING or
                         item.kind == Kind.WORD and re.fullmatch(NAME, item.text) for item in items):
            if any(left.kind == Kind.STRING and right.kind == Kind.WORD and
                   (left.end is None or not source[left.end:left.end + 1].isspace())
                   for left, right in zip(items, items[1:])):
                reject(st, 'put', 'literal-to-variable PUT requires source whitespace; typed literals and comment-only separation need review')
                return None
            names = [item.text.lower() for item in items if item.kind == Kind.WORD]
            types = put_known_types(step.operations)
            discover = list(dict.fromkeys(name for name in names if name not in types))
            discovery_profile = (bool(discover) and step.kind == 'data' and not step.inputs
                and not any(o.kind == 'lookup' for o in step.operations)
                and all(item.kind == Kind.WORD and re.fullmatch(NAME, item.text, re.ASCII) for item in items)
                and all(name not in types or types[name] == 'number' for name in names))
            if all(item.kind == Kind.WORD for item in items) and (
                    all(types.get(name) == 'number' for name in names) or discovery_profile):
                if any(name in ('_n_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_') for name in names):
                    reject(st, 'put', 'PUT automatic variables and special controls require review')
                    return None
                try:
                    sas_put_numeric_list([None] * len(names))
                except ValueError as exc:
                    reject(st, 'put', str(exc))
                else:
                    plan.matched.append(('put-numeric-list', 'DS-027', st.line))
                    args = {'names': names}
                    if discovery_profile:
                        args['discover'] = discover
                        plan.matched.append(('put-numeric-discovery', 'DS-046', st.line))
                    return Operation('put_numeric_list', st.line, args)
                return None
            if any(item.kind == Kind.STRING for item in items) and all(types.get(name) == 'number' for name in names):
                mixed = [{'kind': 'literal', 'value': item.text} if item.kind == Kind.STRING
                         else {'kind': 'variable', 'value': item.text.lower()} for item in items]
                try:
                    if step.kind != 'data' or active_do is not None and active_do.kind != 'do_counted':
                        raise ValueError('mixed numeric PUT requires DATA, optionally counted DO or simple IF')
                    validate_mixed_put_items(mixed)
                except ValueError as exc:
                    reject(st, 'put-mixed-numeric', str(exc))
                else:
                    plan.matched.append(('put-mixed-numeric', 'DS-042', st.line))
                    return Operation('put_mixed_numeric', st.line, {'items': mixed})
                return None
            known = set(step.lengths)
            for previous in walk_operations(step.operations):
                if previous.kind in ('assign', 'round', 'declare'):
                    known.add(previous.args['name'])
            if any(name in ('_n_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_') for name in names) or (
                    not step.inputs and not any(o.kind == 'lookup' for o in step.operations)
                    and any(name not in known for name in names)):
                reject(st, 'put', 'character-list PUT requires declared character variables; automatic or uninitialized numeric variables need review')
                return None
            resolved = [{'kind': 'literal', 'value': item.text} if item.kind == Kind.STRING
                        else {'kind': 'character', 'value': 'x'} for item in items]
            try:
                sas_put_character_list(resolved)
            except ValueError as exc:
                reject(st, 'put', str(exc))
            else:
                matched = ('put-character-list', 'DS-024', st.line)
                plan.matched.append(matched)
                character_put_matches.setdefault(id(step), []).append((matched, all(item.kind == Kind.WORD for item in items)))
                return Operation('put_character_list', st.line, {'items': [
                    {'kind': 'literal', 'value': item.text} if item.kind == Kind.STRING
                    else {'kind': 'variable', 'value': item.text.lower()} for item in items]})
            return None
        rest, names = re.sub(r'^put\s*', '', text, flags=re.I), []
        while match := re.match(r'\s*(' + NAME + r')\s*=', rest):
            names.append(match[1].lower())
            rest = rest[match.end():]
        if not names or rest.strip():
            reject(st, 'put', 'unaccounted for text in named-list PUT')
            return None
        return Operation('put', st.line, {'names': names})

    def simple_branch(st):
        nested = action(st.text, st.line, strict=active_do is not None and active_do.kind == 'do_over')
        if nested is None and re.match(r'^put\b', st.text, re.I):
            nested = put_action(st)
        if nested is None or nested.kind == 'put_all':
            return None
        return nested

    def conditional_action(st):
        # THEN inside quoted strings is data, and token offsets remain original.
        if not st.tokens or st.tokens[0].text.lower() != 'if':
            return None
        for pos, token in enumerate(st.tokens[1:], 1):
            if token.kind != Kind.WORD or token.text.lower() != 'then':
                continue
            condition = predicate(' '.join(t.text for t in st.tokens[1:pos]), strict=active_do is not None and active_do.kind == 'do_over')
            tail = st.tokens[pos + 1:]
            if condition is None or not tail:
                continue
            leaf = Statement(' '.join(t.text for t in tail), tail[0].line, st.terminated, tail)
            nested = simple_branch(leaf)
            if nested is not None:
                return Operation('if', st.line, {'condition': condition, 'operation': asdict(nested)})
        return None

    def admit_loop_branch(op, st):
        if active_do is None:
            return True
        allowed = {'assign', 'array_set', 'round', 'sum_statement', 'if', 'put', 'put_literal', 'put_character_list', 'put_numeric_list', 'put_mixed_numeric', 'output'}
        if any(child.kind not in allowed or
               child.kind in ('assign', 'round', 'sum_statement') and child.args['name'] in {loop.args['index'] for loop in do_parents + [active_do] if loop.kind == 'do_counted'}
               for child in walk_operations([op])):
            reject(st, 'do-counted', 'counted DO branches require simple actions and cannot write the loop index')
            return False
        return True

    def finish():
        nonlocal active_do
        if step and step.kind == 'sql_create':
            if id(step) not in sql_closed:
                plan.tickets.append(Ticket(step.line, 'PROC SQL', 'sql-create', 'descriptor-only PROC SQL requires explicit QUIT'))
            try:
                validate_sql_create(asdict(step), plan.version)
            except ValueError as exc:
                plan.tickets.append(Ticket(step.line, 'PROC SQL', 'sql-create', str(exc)))
            return
        if active_do is not None:
            family = {'do_until': 'do-until', 'do_while': 'do-while', 'do_over': 'do-over'}.get(active_do.kind, 'do-counted')
            label = {'do_until': 'DO UNTIL', 'do_while': 'DO WHILE', 'do_over': 'DO OVER'}.get(active_do.kind, 'counted DO')
            plan.tickets.append(Ticket(active_do.line, 'DO', family, label + ' requires a closing END before the step ends'))
            active_do = None
            do_parents.clear()
        if step and any(o.kind == 'put_all' for o in walk_operations(step.operations)):
            if (step.kind != 'data' or step.inputs or step.by or step.retained or step.where or
                    (step.name == '_null_' and any(o.kind == 'output' for o in step.operations)) or
                    any(o.kind not in ('declare', 'assign', 'put_all', 'output') for o in step.operations)):
                plan.tickets.append(Ticket(step.line, step.name, 'put-all',
                    'PUT _ALL_ supports scalar declarations, safe assignments, and named-destination OUTPUT only; SET, BY, conditions, DATA _NULL_ OUTPUT, and other operations require review'))
        if step:
            if id(step) in infile_configs and not any(o.kind == 'input_numeric' for o in step.operations):
                plan.tickets.append(Ticket(step.line, 'INFILE', 'inline-csv', 'inline INFILE requires one following numeric INPUT and inline data block'))
            flat = list(walk_operations(step.operations))
            try:
                validate_projection_step(asdict(step), plan.version)
            except ValueError as exc:
                plan.tickets.append(Ticket(step.line, step.name, 'projection', str(exc)))
            for op in flat:
                if op.kind == 'put_numeric_list' and 'discover' in op.args and (
                        step.inputs or any(o.kind == 'lookup' for o in step.operations)):
                    plan.tickets.append(Ticket(op.line, 'PUT', 'put-numeric-discovery',
                        'output-only numeric discovery requires a catalog-free DATA step'))
                if op.kind == 'sum_statement':
                    if step.kind != 'data' or op.args['name'] in step.by:
                        plan.tickets.append(Ticket(op.line, 'SUM', 'sum-statement', 'sum statements require DATA execution and cannot change BY keys'))
                    step.retained.setdefault(op.args['name'], {'kind': 'number', 'value': 0.0})
                    plan.matched.append(('sum-statement', 'DS-034', op.line))
                if op.kind in ('do_until', 'do_while'):
                    if any(node.get('kind') == 'call' and node.get('name') in LAG_FUNCTIONS
                           for node, _ in expression_nodes(op.args)):
                        label = 'DO UNTIL' if op.kind == 'do_until' else 'DO WHILE'
                        plan.tickets.append(Ticket(op.line, 'LAG/DIF', op.kind.replace('_', '-'), label + ' queue scheduling requires review'))
            for op in flat:
                payload = op.args.get('value') if op.kind == 'assign' else op.args.get('condition')
                nodes = list(_string_nodes(payload))
                if nodes:
                    plan.matched.append(('concat-catx', 'DS-029', op.line))
                cats = [node for node in nodes if node['kind'] == 'call']
                if cats and not (op.kind == 'assign' and payload.get('kind') == 'call' and
                                 payload.get('name') == 'catx' and len(cats) == 1 and
                                 catx_arguments_allowed(payload)):
                    plan.tickets.append(Ticket(op.line, 'CATX', 'concat-catx',
                        'CATX is gated only as a direct assignment RHS with literal/variable delimiter and literal/variable or checked SUBSTR items; other temporary contexts require review'))
            where_nodes = list(_string_nodes(step.where))
            if where_nodes:
                plan.matched.append(('concat-catx', 'DS-029', step.line))
            if any(node.get('name') == 'catx' for node in where_nodes):
                plan.tickets.append(Ticket(step.line, 'CATX', 'concat-catx', 'CATX in WHERE requires temporary-buffer review'))
            if (step.name == '_null_' and any(o.kind in ('do_counted', 'do_until', 'do_while', 'do_over') for o in flat)
                    and any(o.kind == 'output' for o in flat)):
                family = 'do-over' if any(o.kind == 'do_over' for o in flat) else 'do-until' if any(o.kind == 'do_until' for o in flat) else 'do-while' if any(o.kind == 'do_while' for o in flat) else 'do-counted'
                label = {'do-until': 'DO UNTIL', 'do-while': 'DO WHILE', 'do-over': 'DO OVER'}.get(family, 'counted DO')
                plan.tickets.append(Ticket(step.line, 'OUTPUT', family, 'explicit OUTPUT in DATA _NULL_ ' + label + ' steps is deferred'))
            for op in flat:
                if op.kind == 'output' and op.args['target'] not in (None, step.name):
                    plan.tickets.append(Ticket(op.line, str(op.args['target']), 'output', 'OUTPUT target must be the declared DATA destination'))
            if step.where and (not step.inputs or step.kind != 'data'):
                plan.tickets.append(Ticket(step.line, step.name, 'where', 'WHERE requires one driving SET'))
            if any(o.kind == 'lookup' for o in step.operations) and (not step.inputs or step.kind != 'data'):
                plan.tickets.append(Ticket(step.line, step.name, 'lookup', 'initial lookup requires one driving SET'))
        if step and step.kind in ("sort", "merge") and not step.by:
            plan.tickets.append(Ticket(step.line, step.name, "by", "BY keys are required"))

    try:
        statements = split_statements(source)
    except ParseError as exc:
        plan.tickets.append(Ticket(exc.line, "", "unterminated", str(exc)))
        return plan
    # Bound new-profile source before recursive call parsing. Old source keeps
    # its earlier parsing contract; quoted function-shaped text is data.
    source_texts = ['' if any(t.kind == Kind.DATA for t in s.tokens) else
                    re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", '', s.text)
                    for s in statements]
    numeric_input_source = any(re.match(r'^infile\b(?!\s*=)', text, re.I)
                               or re.match(r'^input\b(?!\s*=)', text, re.I) and '-' in text
                               for text in source_texts)
    if numeric_input_source or any('**' in text or re.search(r'\b(?:constant|sin|cos|tan|arsin|arcos|atan)\s*\(', text, re.I)
                                   for text in source_texts):
        for statement, text in zip(statements, source_texts):
            if numeric_input_source and not any(t.kind == Kind.DATA for t in statement.tokens) and len(re.findall(r'[+*/-]|[A-Za-z_][A-Za-z0-9_]*\s*\(', text, re.ASCII)) > 128:
                plan.tickets.append(Ticket(statement.line, 'numeric-inline-v1', 'input-ranges',
                    'numeric inline source exceeds128 arithmetic/call markers per statement'))
                return plan
            depth = 0
            for char in text:
                depth += (char == '(') - (char == ')')
                if depth > 32:
                    plan.tickets.append(Ticket(statement.line, 'numeric-inline-v1' if numeric_input_source else 'binary64-v1',
                        'input-ranges' if numeric_input_source else 'binary64',
                        'numeric source parentheses exceed the32-level policy'))
                    return plan
    for st in statements:
        text = st.text
        if any(t.kind == Kind.DATA for t in st.tokens):
            try:
                if not inline_pending or step is None:
                    raise ValueError('inline data requires one preceding numeric INPUT and CARDS/DATALINES')
                op, = [o for o in step.operations if o.kind in ('input_list', 'input_numeric')]
                raw, = [t for t in st.tokens if t.kind == Kind.DATA]
                op.args.update(records=source_records(raw.text), data_line=raw.line + 1)
            except ValueError as exc:
                reject(st, 'input-list', str(exc))
            inline_pending = False
            finish()
            step, context = None, None
            continue
        is_else = bool(re.match(r'^else\b(?!\s*=)', text, re.I))
        if not is_else:
            pending_if, chain_length, pending_end = None, 0, None
        # Quoted words are data, including names that resemble variable lists.
        unquoted = re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", ' ', text)
        if re.search(r"\b(?:_ERROR_|_ALL_|_NUMERIC_|_CHARACTER_)\b", unquoted, re.I) and not re.fullmatch(r'put\s+_all_', text, re.I):
            reject(st, "automatic-variable", "automatic variables and variable lists are outside this slice")
            continue
        if not st.terminated:
            reject(st, "unterminated", "statement terminator is missing")
            continue
        construct, rule = route_statement(text, context)
        if context == 'sql-create':
            if text.lower() == 'quit':
                sql_closed.add(id(step))
                finish()
                step, context = None, None
            elif re.match(r'^create\b', text, re.I):
                if step.operations:
                    reject(st, 'sql-create', 'one CREATE TABLE per bare PROC SQL is supported')
                else:
                    try:
                        name, columns = parse_sql_create(text)
                    except ValueError as exc:
                        reject(st, 'sql-create', str(exc))
                    else:
                        step.name = name
                        step.operations.append(Operation('sql_create', st.line, {'columns': columns}))
                        plan.matched.append(('sql-create', 'SQL-004', st.line))
            else:
                reject(st, 'sql-create', 'descriptor-only PROC SQL admits one explicit CHAR CREATE followed by QUIT')
            continue
        if re.fullmatch(r'proc\s+sql', text, re.I):
            finish()
            step = Step('sql_create', '', st.line)
            plan.steps.append(step)
            context = 'sql-create'
            continue
        if re.match(r"^data\b", text, re.I):
            finish()
            try:
                name, projection = projection_dataset(text, 'data')
            except ValueError as exc:
                reject(st, "data-step", str(exc))
                step, context = None, None
                continue
            step = Step("data", name, st.line)
            if projection is not None:
                step.operations.append(Operation('projection', st.line, projection))
                plan.matched.append(('projection-options', 'DS-048', st.line))
            plan.steps.append(step)
            context = "data"
            continue
        if re.match(r"^proc\s+sort\b", text, re.I):
            finish()
            # Full consumption prevents unimplemented SORT options being dropped.
            m = re.fullmatch(r"proc\s+sort\s+data\s*=\s*(" + NAME + r")(?:\s+out\s*=\s*(" + NAME + r"))?(\s+nodupkey)?", text, re.I)
            if not m:
                reject(st, "sort", "supported syntax: PROC SORT DATA=name [OUT=name] [NODUPKEY]")
                step, context = None, None
                continue
            step = Step("sort", (m[2] or m[1]).lower(), st.line,
                        inputs=[m[1].lower()], nodupkey=bool(m[3]))
            plan.steps.append(step)
            plan.matched.append(("sort", "DS-008", st.line))
            context = "sort"
            continue
        if text.lower() in ("run", "quit"):
            finish()
            step, context = None, None
            continue
        if re.match(r"^proc\b", text, re.I):
            finish()
            step = None
            context = "sql" if re.match(r"^proc\s+sql\b", text, re.I) else "proc"
            reject(st, construct, "procedure has no executable backend")
            continue
        if step is None:
            reject(st, construct, "statement is outside a supported step")
            continue
        if re.match(r'^infile\b(?!\s*=)', text, re.I):
            try:
                if (step.kind != 'data' or active_do is not None or id(step) in infile_configs
                        or any(o.kind not in ('declare', 'projection') for o in step.operations)):
                    raise ValueError('one inline INFILE must precede INPUT and all executable actions')
                infile_configs[id(step)] = {**parse_infile(text), 'line': st.line}
                plan.matched.append(('inline-csv', 'DS-058', st.line))
            except ValueError as exc:
                reject(st, 'inline-csv', str(exc))
            continue
        if re.match(r'^input\b(?!\s*=)', text, re.I):
            try:
                terms, names = parse_input_terms(text.split(None, 1)[1])
                config = infile_configs.get(id(step))
                extended = config is not None or any('-' in term for term in terms)
                if (step.kind != 'data' or active_do is not None
                        or any(o.kind not in ('declare', 'projection', 'array_declare') for o in step.operations)):
                    raise ValueError('one numeric INPUT must be the first top-level executable action')
                if extended:
                    args = {'profile': INPUT_PROFILE, 'terms': terms, 'names': names,
                            'delimiter': config['delimiter'] if config else ' ',
                            'firstobs': config['firstobs'] if config else 1,
                            'infile_line': config['line'] if config else None}
                    step.operations.append(Operation('input_numeric', st.line, args))
                    if any('-' in term for term in terms):
                        plan.matched.append(('input-ranges', 'DS-059', st.line))
                else:
                    step.operations.append(Operation('input_list', st.line, {'names': names}))
                    plan.matched.append(('input-list', 'DS-044', st.line))
            except (ValueError, IndexError) as exc:
                reject(st, 'input-list', str(exc))
            continue
        if re.fullmatch(r'(?:cards|datalines)', text, re.I):
            if (active_do is not None or step.kind != 'data'
                    or sum(o.kind in ('input_list', 'input_numeric') for o in step.operations) != 1):
                reject(st, 'input-list', 'CARDS/DATALINES requires one preceding top-level numeric INPUT')
            else:
                inline_pending = True
            continue
        if re.match(r'^array\b(?!\s*=)', text, re.I):
            try:
                if active_do is not None:
                    raise ValueError('numeric ARRAY declarations must be outside loop bodies')
                args = array_declaration(text, preserve_mode=True)
                append_operation(Operation('array_declare', st.line, args))
                plan.matched.append(('numeric-arrays', 'DS-039', st.line))
            except ValueError as exc:
                reject(st, 'numeric-arrays', str(exc))
            continue
        if re.match(r'^do\b(?!\s*=)', text, re.I):
            over = re.fullmatch(r'do\s+over\s+(' + NAME + r')', text, re.I)
            if over and active_do is None and context == 'data' and step.kind == 'data':
                active_do = Operation('do_over', st.line, {'name': over[1].lower(), 'body': []})
                step.operations.append(active_do)
                plan.matched.append(('do-over', 'DS-040', st.line))
                continue
            until = re.fullmatch(r'do\s+(until|while)\s*\((.*)\)', text, re.I | re.S)
            if until and active_do is None and context == 'data' and step.kind == 'data':
                name = until[1].lower()
                test = predicate(until[2])
                if test is None:
                    reject(st, 'do-' + name, 'DO ' + name.upper() + ' requires a supported predicate')
                else:
                    active_do = Operation('do_' + name, st.line, {'condition': test, 'body': []})
                    step.operations.append(active_do)
                    plan.matched.append(('do-' + name, 'DS-035' if name == 'until' else 'DS-038', st.line))
                continue
            match = re.fullmatch(r'do\s+(' + NAME + r')\s*=\s*(.*?)\s+to\s+(.*?)(?:\s+by\s+(.*))?', text, re.I | re.ASCII)
            if active_do is not None and active_do.kind != 'do_counted':
                reject(st, 'do-counted', 'only counted loops can nest in the A2 profile')
            elif context != 'data' or step.kind != 'data' or not match:
                reject(st, 'do-counted', 'supported DO controls: index=start TO stop [BY step]')
            elif match[1].lower() in ('_n_', '_error_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_'):
                reject(st, 'do-counted', 'automatic variables cannot be counted DO indices')
            elif active_do is not None and len(do_parents) >= 7:
                reject(st, 'do-counted-bounded', 'counted DO exceeds8 nested levels')
            else:
                try:
                    start, stop, by = (parse_control(v) for v in (match[2], match[3], match[4] or '1'))
                    if all(type(v) is int for v in (start, stop, by)):
                        sas_do_counted(start, stop, by)
                except ValueError as exc:
                    reject(st, 'do-counted', str(exc))
                else:
                    name = match[1].lower()
                    step.display_names.setdefault(name, match[1])
                    append_operation(Operation('declare', st.line, {'name': name, 'spec': 'number'}))
                    args = {'index': name, 'start': start, 'stop': stop, 'by': by, 'body': []}
                    if active_do is not None or any(type(v) is not int for v in (start, stop, by)):
                        args['profile'] = 'bounded'
                        for parent in do_parents + ([active_do] if active_do else []):
                            parent.args['profile'] = 'bounded'
                        plan.matched.append(('do-counted-bounded', 'DS-041', st.line))
                    # append_operation serializes children; keep the live stored args.
                    stored = append_operation(Operation('do_counted', st.line, args))
                    if active_do is not None:
                        do_parents.append(active_do)
                    active_do = Operation('do_counted', st.line, stored)
                    plan.matched.append(('do-counted', 'DS-026', st.line))
            continue
        if re.match(r'^end\b(?!\s*=)', text, re.I):
            if text.lower() != 'end' or active_do is None:
                reject(st, 'do-counted', 'END requires one open counted DO')
            else:
                active_do = do_parents.pop() if do_parents else None
            continue
        if active_do is not None:
            family = {'do_until': 'do-until', 'do_while': 'do-while', 'do_over': 'do-over'}.get(active_do.kind, 'do-counted')
            label = {'do-until': 'DO UNTIL', 'do-while': 'DO WHILE', 'do-over': 'DO OVER'}.get(family, 'counted DO')
            target = re.match(r'(' + NAME + r')(?:\s*[({\[].*?[)}\]])?\s*(?:=|\+(?!=))', text)
            if target and target[1].lower() in {loop.args['index'] for loop in do_parents + [active_do] if loop.kind == 'do_counted'}:
                reject(st, 'do-counted', 'assignment to the counted DO index inside its body is deferred')
                continue
            if not target and not re.match(r'^(?:put|output|if|else)\b', text, re.I):
                reject(st, family, label + ' body supports simple actions and bounded IF/ELSE branches only')
                continue
            if re.fullmatch(r'put\s+_all_', text, re.I):
                reject(st, family, 'PUT _ALL_ error-flag contract excludes ' + label)
                continue
        if re.match(r"^by\b", text, re.I):
            words = text.split()[1:]
            if (step.kind not in ("sort", "merge") and not step.inputs) or step.by or not words or any(
                    not re.fullmatch(NAME, w) or w.lower() in ("descending", "notsorted") for w in words):
                reject(st, "by", "only one ascending BY list on SORT or MERGE is supported")
            elif len(set(w.lower() for w in words)) != len(words):
                reject(st, "by", "duplicate BY keys are unsupported")
            else:
                step.by = [w.lower() for w in words]
            continue
        if re.match(r"^(set|merge)\b", text, re.I):
            input_projection = None
            if re.match(r'^set\b', text, re.I):
                try:
                    dataset_name, input_projection = projection_dataset(text, 'set')
                except ValueError as exc:
                    reject(st, 'set', str(exc))
                    continue
                m = re.fullmatch(r'(set)\s+(' + NAME + r')(?:\s+(' + NAME + r'))?', 'set ' + dataset_name, re.I)
            else:
                m = re.fullmatch(r"(set|merge)\s+(" + NAME + r")(?:\s+(" + NAME + "))?", text, re.I)
            if (not m or context != "data" or step.inputs or any(o.kind not in ("lookup", "declare", "array_declare", "projection") for o in step.operations) or
                    (m[1].lower() == "set" and m[3]) or (m[1].lower() == "merge" and not m[3])):
                reject(st, construct, "one SET input or two MERGE inputs must precede computations")
            else:
                step.inputs = [v.lower() for v in (m[2], m[3]) if v]
                if input_projection is not None:
                    append_operation(Operation('projection', st.line, input_projection))
                    plan.matched.append(('projection-options', 'DS-048', st.line))
                append_operation(Operation("read", st.line, {"datasets": step.inputs}))
                if m[1].lower() == "merge":
                    step.kind = "merge"
                plan.matched.append((m[1].lower(), "DS-001" if m[1].lower() == "set" else "DS-002", st.line))
            continue
        if context != "data":
            reject(st, construct, "unsupported procedure clause")
            continue
        if re.match(r'^(keep|drop)\b(?!\s*=)', text, re.I):
            try:
                if active_do is not None:
                    raise ValueError('projection statements must be top-level DATA declarations')
                args = projection_declaration(text)
                append_operation(Operation('projection', st.line, args))
                plan.matched.append(('projection-statements', 'DS-047', st.line))
            except ValueError as exc:
                reject(st, 'projection', str(exc))
            continue
        # Only variable occurrences establish spelling; skip statement heads
        # and function names. PUT _ALL_ uses these names without normalizing case.
        spelling_text = unquoted
        if not re.match(NAME + r'\s*=', spelling_text):
            spelling_text = re.sub(r'^\s*' + NAME, '', spelling_text, count=1)
        spelling_text = re.sub(r'(?<![\w.])(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?!\w)', ' ', spelling_text)
        spelling_text = re.sub(r'\.[A-Za-z_]\b', ' ', spelling_text)
        for word in re.finditer(NAME, spelling_text):
            if not spelling_text[word.end():].lstrip().startswith('('):
                step.display_names.setdefault(word[0].lower(), word[0])
        if re.match(r'^where\b', text, re.I):
            condition = predicate(re.sub(r'^where\s*', '', text, flags=re.I))
            if not condition or step.where or step.kind == 'merge':
                reject(st, 'where', 'one simple WHERE predicate on SET is supported')
            else:
                step.where = condition
            continue
        declaration = re.fullmatch(r'retain\s+(' + NAME + r')(?:\s+(.+))?', text, re.I)
        if declaration:
            value = atom(declaration[2]) if declaration[2] else None
            if value is not None and value['kind'] in ('number', 'missing') and declaration[1].lower() != '_n_':
                step.retained[declaration[1].lower()] = value
                append_operation(Operation('declare', st.line, {'name': declaration[1].lower(), 'spec': 'number'}))
            else:
                reject(st, 'retain', 'RETAIN requires one variable and a numeric or missing initializer')
            continue
        declaration = re.fullmatch(r'length\s+(' + NAME + r'(?:\s+' + NAME + r')*)\s+\$\s*([0-9]+)', text, re.I | re.ASCII)
        if declaration:
            names = [name.lower() for name in declaration[1].split()]
            try:
                width = int(declaration[2])
            except ValueError:
                width = 0
            automatic = {'_n_', '_error_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_'}
            if (step.inputs or any(o.kind not in ('declare', 'projection') for o in step.operations) or
                    len(names) != len(set(names)) or any(name in step.lengths or name in automatic for name in names) or
                    not 1 <= width <= 32767):
                reject(st, 'length', 'character LENGTH requires unique ordinary names before SET/computations; width 1..32767')
            else:
                for name in names:
                    step.lengths[name] = width
                    append_operation(Operation('declare', st.line, {'name': name, 'spec': {'type': 'character', 'length': width}}))
                plan.matched.append(('length-list' if len(names) > 1 else 'length-reverse', 'DS-028', st.line))
            continue
        lookup = re.fullmatch(r'if\s+_n_\s*=\s*1\s+then\s+set\s+(' + NAME + r')', text, re.I)
        if lookup:
            if step.inputs or any(o.kind not in ('declare', 'projection') for o in step.operations):
                reject(st, 'lookup', 'one initial lookup SET must precede the driving SET')
            else:
                append_operation(Operation('lookup', st.line, {'dataset': lookup[1].lower()}))
            continue
        if is_else:
            gap = (tokenize(source[pending_end:st.tokens[0].start])
                   if pending_end is not None and st.tokens and st.tokens[0].start is not None else [])
            if pending_if is None or len(gap) != 1 or gap[0].kind != Kind.SEMI:
                reject(st, 'do-if', 'ELSE requires an immediately preceding unmatched IF in the same body')
                pending_if = None
                continue
            tail = st.tokens[1:]
            branch = Statement(' '.join(t.text for t in tail), tail[0].line if tail else st.line,
                               st.terminated, tail)
            nested = conditional_action(branch) if tail and tail[0].text.lower() == 'if' else simple_branch(branch)
            if nested is None or not admit_loop_branch(nested, st):
                reject(st, 'do-if', 'ELSE requires a simple action or ELSE IF with a simple action')
                pending_if = None
                continue
            if nested.kind == 'if' and chain_length >= 32:
                reject(st, 'do-if', 'IF/ELSE chain exceeds the bounded32-condition policy')
                pending_if = None
                continue
            pending_if['otherwise'] = asdict(nested)
            if active_do is not None and active_do.kind == 'do_over':
                bind_current(pending_if['otherwise'], active_do.args['name'])
            pending_if = pending_if['otherwise']['args'] if nested.kind == 'if' else None
            pending_end = st.tokens[-1].end
            chain_length += int(nested.kind == 'if')
            plan.matched.append(('do-if', 'DS-031', st.line))
            continue
        conditional = conditional_action(st)
        if conditional is not None:
            if admit_loop_branch(conditional, st):
                pending_if = append_operation(conditional)
                chain_length = 1
                pending_end = st.tokens[-1].end
                plan.matched.append(('do-if', 'DS-031', st.line))
            continue
        if re.match(r'^if\b', text, re.I) and any(t.kind == Kind.WORD and t.text.lower() == 'then' for t in st.tokens):
            reject(st, 'if', 'IF THEN requires a simple assignment, OUTPUT or bounded PUT action')
            continue
        if re.match(r'^if\b', text, re.I):
            if active_do is not None:
                family = {'do_until': 'do-until', 'do_while': 'do-while', 'do_over': 'do-over'}.get(active_do.kind, 'do-counted')
                label = {'do-until': 'DO UNTIL', 'do-while': 'DO WHILE', 'do-over': 'DO OVER'}.get(family, 'counted DO')
                reject(st, family, 'subsetting IF inside ' + label + ' is deferred')
                continue
            condition = predicate(re.sub(r'^if\s*', '', text, flags=re.I))
            if condition:
                append_operation(Operation('subset', st.line, {'condition': condition}))
            else:
                reject(st, 'if', 'unsupported subsetting predicate')
            continue
        simple = action(text, st.line, strict=active_do is not None and active_do.kind == 'do_over')
        if simple:
            append_operation(simple)
            continue
        assignment = re.fullmatch(r"(" + NAME + r")\s*=\s*(.+)", text)
        if assignment and assignment[1].lower() == "_n_":
            reject(st, 'automatic-variable', 'assignment to _N_ is outside this slice')
            continue
        if assignment:
            rounded = re.fullmatch(r"round\s*\(([^,]+),([^,]+)\)", assignment[2], re.I)
            if rounded and atom(rounded[1]) is not None and atom(rounded[2]) is not None:
                append_operation(Operation("round", st.line, {"name": assignment[1].lower(),
                                                                    "value": atom(rounded[1]),
                                                                    "unit": atom(rounded[2])}))
                plan.matched.append(("round", "DS-012", st.line))
                continue
            value = expression(assignment[2], strict=active_do is not None and active_do.kind == 'do_over')
            if value is not None:
                if value['kind'] == 'call' and value['name'] == 'round':
                    plan.matched.append(("round", "DS-012", st.line))
                append_operation(Operation("assign", st.line, {"name": assignment[1].lower(),
                                                                     "value": value}))
                continue
            family, _ = route_function(assignment[2])
            reject(st, family if family != "unknown" else "assignment", "unsupported expression")
            continue
        if re.match(r"^put\b", text, re.I):
            nested = put_action(st)
            if nested is not None:
                append_operation(nested)
            continue
        family, _ = route_function(text)
        reject(st, family if family != "unknown" else construct, "no operation for this statement")
    finish()
    for compiled in plan.steps:
        if compiled.kind == 'sql_create':
            continue
        nodes = [node for node, _ in expression_nodes(asdict(compiled))]
        if any(node.get('kind') == 'arithmetic' and node.get('op') == '**'
               or node.get('kind') == 'call' and node.get('name') in BINARY64_FUNCTIONS for node in nodes):
            pipeline_features = {op.kind for op in walk_operations(compiled.operations)} & {'input_list','array_declare','do_over','do_while','do_until'}
            composed = bool(compiled.inputs or any(op.kind == 'projection' for op in walk_operations(compiled.operations)))
            profile = PIPELINE_PROFILE if pipeline_features else BINARY64_ROWS_PROFILE if composed else BINARY64_PROFILE
            groups = ({'input'} if 'input_list' in pipeline_features else set()) | ({'arrays'} if pipeline_features & {'array_declare','do_over'} else set()) | ({'loops'} if pipeline_features & {'do_while','do_until'} else set())
            rule = ('DS-057' if len(groups)>1 else 'DS-054' if 'input' in groups else 'DS-055' if 'arrays' in groups else 'DS-056') if pipeline_features else 'DS-053' if compiled.inputs else 'DS-052' if composed else 'DS-049'
            numeric_rules[id(compiled)] = rule
            compiled.operations.insert(0, Operation('numeric_profile', compiled.line, {'name': profile}))
            construct = {'DS-054':'pipeline-input','DS-055':'pipeline-arrays','DS-056':'pipeline-loops','DS-057':'numeric-pipeline'}.get(rule) if pipeline_features else 'numeric-set' if compiled.inputs else 'numeric-projection' if composed else 'binary64'
            plan.matched.append((construct, rule, compiled.line))
            if compiled.inputs:
                # A supplied numeric descriptor resolves these names at runtime.
                # Only the new profile changes the legacy character fallback;
                # output-only discovery remains the separate catalog-free gate.
                for raw in _walk_operations(compiled.operations):
                    kind, args = (raw['kind'], raw['args']) if isinstance(raw, dict) else (raw.kind, raw.args)
                    if kind == 'put_character_list' and all(item['kind'] == 'variable' for item in args['items']):
                        numeric_args = {'names': [item['value'] for item in args['items']]}
                        if isinstance(raw, dict):
                            raw.update(kind='put_numeric_list', args=numeric_args)
                            line = raw['line']
                        else:
                            raw.kind, raw.args = 'put_numeric_list', numeric_args
                            line = raw.line
                        plan.matched.append(('put-numeric-list', 'DS-027', line))
                removed = {id(matched) for matched, variables_only in character_put_matches.get(id(compiled), []) if variables_only}
                plan.matched[:] = [matched for matched in plan.matched if id(matched) not in removed]
            if any(node.get('kind') == 'call' and node.get('name') in BINARY64_FUNCTIONS for node in nodes):
                plan.matched.append(('elementary-functions', 'DS-050', compiled.line))
            if any(op.kind == 'put_numeric_list' for op in walk_operations(compiled.operations)):
                plan.matched.append(('fractional-put', 'DS-051', compiled.line))
        try:
            validate_binary64_step(asdict(compiled), plan.version)
        except ValueError as exc:
            plan.tickets.append(Ticket(compiled.line, 'binary64-v1', 'binary64', str(exc)))
        try:
            validate_numeric_input_step(asdict(compiled), plan.version)
            validate_input_step(asdict(compiled))
        except ValueError as exc:
            plan.tickets.append(Ticket(compiled.line, 'INPUT', 'input-list', str(exc)))
        try:
            validate_trim_step(asdict(compiled))
        except ValueError as exc:
            plan.tickets.append(Ticket(compiled.line, 'TRIM/STRIP', 'trim-strip', str(exc)))
        # Preserve the old serialized shape unless new DO OVER needs source mode.
        over_names = {op.args['name'] for op in walk_operations(compiled.operations) if op.kind == 'do_over'}
        for op in walk_operations(compiled.operations):
            if op.kind == 'do_over':
                bind_current(op.args['body'], op.args['name'])
            if op.kind == 'array_declare' and op.args['name'] not in over_names:
                op.args.pop('mode', None)
        try:
            validate_counted_step(asdict(compiled))
        except ValueError as exc:
            plan.tickets.append(Ticket(compiled.line, 'DO', 'do-counted-bounded', str(exc)))
        try:
            arrays = validate_array_step(asdict(compiled))
            if arrays:
                plan.matched.extend(('numeric-arrays', 'DS-039', op.line) for op in walk_operations(compiled.operations)
                                    if op.kind == 'array_set' or any(node.get('kind') in ('array_get', 'array_sum') for node, _ in expression_nodes(op.args)))
        except ValueError as exc:
            plan.tickets.append(Ticket(compiled.line, 'ARRAY', 'numeric-arrays', str(exc)))
        for op in walk_operations(compiled.operations):
            payloads = [(op.args.get('value'), 'assignment')] if op.kind == 'assign' else [
                (value, 'other') for key, value in op.args.items() if key not in ('body', 'operation', 'otherwise')]
            for payload, context in payloads:
                try:
                    validate_lag_calls(payload, direct=context == 'assignment')
                except ValueError as exc:
                    plan.tickets.append(Ticket(op.line, 'LAG/DIF', 'lag-dif', str(exc)))
                for message in substr_context_errors(payload, context):
                    plan.tickets.append(Ticket(op.line, 'SUBSTR', 'substr', message))
        try:
            validate_lag_calls(compiled.where)
        except ValueError as exc:
            plan.tickets.append(Ticket(compiled.line, 'LAG/DIF', 'lag-dif', str(exc)))
        lag_nodes = [(node, line) for node, line in expression_nodes(asdict(compiled))
                     if node.get('kind') == 'call' and node.get('name') in LAG_FUNCTIONS]
        plan.matched.extend(('lag-dif', 'DS-007', line or compiled.line) for _, line in lag_nodes)
        if lag_nodes and any(op.kind == 'put_all' for op in walk_operations(compiled.operations)):
            plan.tickets.append(Ticket(compiled.line, 'LAG/DIF', 'lag-dif', 'LAG/DIF with PUT _ALL_ requires error-state review'))
        for message in substr_context_errors(compiled.where):
            plan.tickets.append(Ticket(compiled.line, 'SUBSTR', 'substr', message))
    checked_substr_lines = function_call_lines(plan.to_dict(), 'substr')
    if checked_substr_lines:
        plan.matched.extend(('substr', 'DS-030', line or 1) for line in checked_substr_lines)
        for st in statements:
            for token in st.tokens:
                if token.kind != Kind.STRING:
                    continue
                if token.text.startswith('"') and any(char in token.text for char in '&%'):
                    reject(st, 'substr', 'checked SUBSTR requires macro-free source character values')
                if any(not 32 <= ord(char) <= 126 for char in token.text):
                    reject(st, 'substr', 'checked SUBSTR requires printable ASCII source character values')
    for name in ('trim', 'strip'):
        plan.matched.extend(('trim-strip', 'DS-043', line or 1)
                            for line in function_call_lines(plan.to_dict(), name))
    has_strings = any(item[0] in ('concat-catx', 'trim-strip') for item in plan.matched)
    if has_strings or any(contains_put(compiled.operations, {'put_character_list', 'put_numeric_list', 'put_mixed_numeric', 'put_all'}) for compiled in plan.steps):
        # Macros resolve before DATA execution. Without taint tracking, even
        # unused or prior-step literals can affect this output contract.
        for st in statements:
            if any(token.kind == Kind.STRING and token.text.startswith('"') and
                   any(char in token.text for char in '&%') for token in st.tokens):
                reject(st, 'concat-catx' if has_strings else 'put', ('bounded character operations' if has_strings else 'bounded PUT') + ' require macro-free source: double-quoted & or % anywhere in the program requires macro review')
    has_all_put = any(contains_put(compiled.operations, {'put_all'}) for compiled in plan.steps)
    if has_strings or has_all_put or any(contains_put(compiled.operations, {'put_numeric_list', 'put_mixed_numeric'}) for compiled in plan.steps):
        for st in statements:
            if any(token.kind == Kind.STRING and any(not 32 <= ord(c) <= 126 for c in token.text) for token in st.tokens):
                reject(st, 'concat-catx' if has_strings else 'put-all' if has_all_put else 'put',
                       ('bounded character operations' if has_strings else 'PUT _ALL_' if has_all_put else 'PUT numeric list') + ' require printable ASCII source character values')
    reverse_ops = [op for compiled in plan.steps for op in walk_operations(compiled.operations) if function_call_lines({key:value for key,value in op.args.items() if key not in ('operation','body')}, 'reverse')]
    reverse_in_where = any(function_call_lines(compiled.where, 'reverse') for compiled in plan.steps)
    if reverse_ops or reverse_in_where:
        plan.matched.extend(('length-reverse', 'DS-028', op.line) for op in reverse_ops)
        for st in statements:
            for token in st.tokens:
                if token.kind != Kind.STRING:
                    continue
                if token.text.startswith('"') and any(char in token.text for char in '&%'):
                    reject(st, 'length-reverse', 'REVERSE requires macro-free source character values')
                if any(not 32 <= ord(char) <= 126 for char in token.text):
                    reject(st, 'length-reverse', 'REVERSE requires printable ASCII source character values')
    for name in SAS_BITWISE_ARITY:
        plan.matched.extend(('bitwise', 'DS-032', line or 1)
                            for line in function_call_lines(plan.to_dict(), name))
    for name in ('mdy', 'weekday'):
        plan.matched.extend(('calendar', 'DS-033', line or 1)
                            for line in function_call_lines(plan.to_dict(), name))
    numeric_nodes = [(node, line, numeric_rules.get(id(compiled)))
                     for compiled in plan.steps for node, line in expression_nodes(asdict(compiled))
                     if node.get('kind') == 'arithmetic' and node.get('op') in ('/', '*')
                     or node.get('kind') == 'call' and node.get('name') == 'int']
    for node, line, rounded_rule in numeric_nodes:
        family, rule = (('int', 'DS-037') if node['kind'] == 'call' else
                        ({'DS-054':'pipeline-input','DS-055':'pipeline-arrays','DS-056':'pipeline-loops','DS-057':'numeric-pipeline'}.get(rounded_rule) if rounded_rule in ('DS-054','DS-055','DS-056','DS-057') else 'numeric-set' if rounded_rule == 'DS-053' else
                         'numeric-projection' if rounded_rule == 'DS-052' else 'binary64', rounded_rule) if rounded_rule else
                        ('multiplication', 'DS-045') if node['op'] == '*' else ('division', 'DS-036'))
        plan.matched.append((family, rule, line or 1))
    if numeric_nodes:
        for compiled in plan.steps:
            nodes = [node for node, _ in expression_nodes(asdict(compiled))]
            if not any(node.get('kind') == 'arithmetic' and node.get('op') in ('/', '*')
                       or node.get('kind') == 'call' and node.get('name') == 'int' for node in nodes):
                continue
            count = sum(node.get('kind') in ('arithmetic', 'call') for node in nodes)
            if count > 128:
                plan.tickets.append(Ticket(compiled.line, 'expression', 'division', 'numeric composition exceeds the128-node step policy'))
    return plan
