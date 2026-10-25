"""Versioned, target-independent operations for the executable SAS subset.

Names are case-insensitive strings, numbers are binary64 values, and steps own
local state. Unsupported statements remain tickets; no backend can clear them.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from sas_semantics import sas_put_literals, sas_put_character_list, sas_put_numeric_list, sas_do_counted
from .functions import FUNCTIONS, format_token, FORMATS, function_call_lines, substr_context_errors
from .parser import Kind, ParseError, split_statements
from .operations import walk_operations as _walk_operations
from .rules import route_function, route_statement

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


def _arithmetic_positions(text):
    """Offsets of depth-0, unquoted + and - in an expression."""
    depth, quote, positions = 0, "", []
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "'\"":
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char in "+-" and depth == 0:
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
        elif char == "(":
            depth += 1
        elif char == ")":
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


def _argument(text, allow_format=False):
    """One argument: a format token only in a position this function declares."""
    if allow_format:
        value = _format_argument(text)
        if value is not None:
            return value
    return expression(text)


def call(text):
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
    values = [_argument(part, index in spec.format_args) for index, part in enumerate(parts)]
    if any(value is None for value in values):
        return None
    return {"kind": "call", "name": name, "args": values}


def operand(text):
    """One expression operand: an atom or a wired call."""
    value = atom(text)
    return value if value is not None else call(text)


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
        elif char == '(':
            depth += 1
        elif char == ')':
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


def expression(text):
    text = text.strip()
    parts = _concat_parts(text)
    if parts is not None:
        if not 2 <= len(parts) <= 32:
            return None
        values = [operand(part) for part in parts]
        if any(value is None for value in values):
            return None
        return {'kind': 'concat', 'args': values}
    value = operand(text)
    if value is not None:
        return value
    for position in _arithmetic_positions(text):
        left, right = operand(text[:position]), operand(text[position + 1:])
        if left is not None and right is not None:
            return {'kind': 'arithmetic', 'left': left, 'op': text[position], 'right': right}
    return None


def predicate(text):
    value = operand(text)
    if value is not None:
        return {'left': value, 'op': 'truth'}
    match = re.fullmatch(r'(.+?)\s*(<=|>=|\^=|~=|<>|=|<|>|\beq\b|\bne\b|\blt\b|\bgt\b|\ble\b|\bge\b)\s*(.+)', text, re.I)
    if match and operand(match[1]) is not None and operand(match[3]) is not None:
        return {'left': operand(match[1]), 'op': match[2].lower(), 'right': operand(match[3])}
    return None


def action(text, line):
    match = re.fullmatch(r'output(?:\s+(' + NAME + r'))?', text, re.I)
    if match:
        return Operation('output', line, {'target': match[1].lower() if match[1] else None})
    match = re.fullmatch(r'(' + NAME + r')\s*=\s*(.+)', text)
    if match and match[1].lower() != '_n_':
        value = expression(match[2])
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
        if kind in ('number', 'missing', 'tagged_missing', 'automatic'):
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
        elif kind in ('assign', 'round'):
            known.setdefault(args['name'], 'number' if kind == 'round' else expression_type(args['value']))
    return known


def contains_put(ops, kinds):
    """Inspect structural containers conservatively for source-wide guards."""
    return any(op.kind in kinds for op in walk_operations(ops, all_containers=True))


def compile_plan(source: str) -> Plan:
    plan, step, context, active_do = Plan(), None, None, None

    def append_operation(op):
        if active_do is None:
            step.operations.append(op)
        else:
            active_do.args['body'].append(asdict(op))

    def reject(st, construct, reason):
        plan.tickets.append(Ticket(st.line, st.text, construct, reason))

    def finish():
        nonlocal active_do
        if active_do is not None:
            plan.tickets.append(Ticket(active_do.line, 'DO', 'do-counted', 'counted DO requires a closing END before the step ends'))
            active_do = None
        if step and any(o.kind == 'put_all' for o in walk_operations(step.operations)):
            if (step.kind != 'data' or step.inputs or step.by or step.retained or step.where or
                    (step.name == '_null_' and any(o.kind == 'output' for o in step.operations)) or
                    any(o.kind not in ('declare', 'assign', 'put_all', 'output') for o in step.operations)):
                plan.tickets.append(Ticket(step.line, step.name, 'put-all',
                    'PUT _ALL_ supports scalar declarations, safe assignments, and named-destination OUTPUT only; SET, BY, conditions, DATA _NULL_ OUTPUT, and other operations require review'))
        if step:
            flat = list(walk_operations(step.operations))
            for op in flat:
                payload = op.args.get('value') if op.kind == 'assign' else op.args.get('condition')
                nodes = list(_string_nodes(payload))
                if nodes:
                    plan.matched.append(('concat-catx', 'DS-029', op.line))
                cats = [node for node in nodes if node['kind'] == 'call']
                if cats and not (op.kind == 'assign' and payload.get('kind') == 'call' and
                                 payload.get('name') == 'catx' and len(cats) == 1 and
                                 all(arg['kind'] in ('character', 'variable') for arg in payload['args'])):
                    plan.tickets.append(Ticket(op.line, 'CATX', 'concat-catx',
                        'CATX is gated only as a direct assignment RHS with literal/variable character arguments; temporary contexts require review'))
            where_nodes = list(_string_nodes(step.where))
            if where_nodes:
                plan.matched.append(('concat-catx', 'DS-029', step.line))
            if any(node.get('name') == 'catx' for node in where_nodes):
                plan.tickets.append(Ticket(step.line, 'CATX', 'concat-catx', 'CATX in WHERE requires temporary-buffer review'))
            if (step.name == '_null_' and any(o.kind == 'do_counted' for o in flat)
                    and any(o.kind == 'output' for o in flat)):
                plan.tickets.append(Ticket(step.line, 'OUTPUT', 'do-counted', 'explicit OUTPUT in DATA _NULL_ counted DO steps is deferred'))
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
    for st in statements:
        text = st.text
        # Quoted words are data, including names that resemble variable lists.
        unquoted = re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", ' ', text)
        if re.search(r"\b(?:_ERROR_|_ALL_|_NUMERIC_|_CHARACTER_)\b", unquoted, re.I) and not re.fullmatch(r'put\s+_all_', text, re.I):
            reject(st, "automatic-variable", "automatic variables and variable lists are outside this slice")
            continue
        if not st.terminated:
            reject(st, "unterminated", "statement terminator is missing")
            continue
        construct, rule = route_statement(text, context)
        if re.match(r"^data\b", text, re.I):
            finish()
            m = re.fullmatch(r"data\s+(" + NAME + ")", text, re.I)
            if not m:
                reject(st, "data-step", "DATA options or names are not supported")
                step, context = None, None
                continue
            step = Step("data", m[1].lower(), st.line)
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
        if re.match(r'^do\b(?!\s*=)', text, re.I):
            match = re.fullmatch(r'do\s+(' + NAME + r')\s*=\s*([+-]?[0-9]+)\s+to\s+([+-]?[0-9]+)(?:\s+by\s+([+-]?[0-9]+))?', text, re.I | re.ASCII)
            if active_do is not None:
                reject(st, 'do-counted', 'nested DO is deferred')
            elif context != 'data' or step.kind != 'data' or not match:
                reject(st, 'do-counted', 'supported DO controls: index=start TO stop [BY step], signed integer literals only')
            elif match[1].lower() in ('_n_', '_error_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_'):
                reject(st, 'do-counted', 'automatic variables cannot be counted DO indices')
            else:
                try:
                    start, stop, by = int(match[2]), int(match[3]), int(match[4] or '1')
                    sas_do_counted(start, stop, by)
                except ValueError as exc:
                    reject(st, 'do-counted', str(exc))
                else:
                    name = match[1].lower()
                    step.display_names.setdefault(name, match[1])
                    append_operation(Operation('declare', st.line, {'name': name, 'spec': 'number'}))
                    active_do = Operation('do_counted', st.line, {'index': name, 'start': start, 'stop': stop, 'by': by, 'body': []})
                    step.operations.append(active_do)
                    plan.matched.append(('do-counted', 'DS-026', st.line))
            continue
        if re.match(r'^end\b(?!\s*=)', text, re.I):
            if text.lower() != 'end' or active_do is None:
                reject(st, 'do-counted', 'END requires one open counted DO')
            else:
                active_do = None
            continue
        if active_do is not None:
            target = re.match(r'(' + NAME + r')\s*=', text)
            if target and target[1].lower() == active_do.args['index']:
                reject(st, 'do-counted', 'assignment to the counted DO index inside its body is deferred')
                continue
            if not target and not re.match(r'^(?:put|output)\b', text, re.I):
                reject(st, 'do-counted', 'counted DO body supports direct assignments, PUT, and OUTPUT only')
                continue
            if re.fullmatch(r'put\s+_all_', text, re.I):
                reject(st, 'do-counted', 'PUT _ALL_ error-flag contract excludes counted DO')
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
            m = re.fullmatch(r"(set|merge)\s+(" + NAME + r")(?:\s+(" + NAME + "))?", text, re.I)
            if (not m or context != "data" or step.inputs or any(o.kind not in ("lookup", "declare") for o in step.operations) or
                    (m[1].lower() == "set" and m[3]) or (m[1].lower() == "merge" and not m[3])):
                reject(st, construct, "one SET input or two MERGE inputs must precede computations")
            else:
                step.inputs = [v.lower() for v in (m[2], m[3]) if v]
                append_operation(Operation("read", st.line, {"datasets": step.inputs}))
                if m[1].lower() == "merge":
                    step.kind = "merge"
                plan.matched.append((m[1].lower(), "DS-001" if m[1].lower() == "set" else "DS-002", st.line))
            continue
        if context != "data":
            reject(st, construct, "unsupported procedure clause")
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
            if (step.inputs or any(o.kind != 'declare' for o in step.operations) or
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
            if step.inputs or any(o.kind != 'declare' for o in step.operations):
                reject(st, 'lookup', 'one initial lookup SET must precede the driving SET')
            else:
                append_operation(Operation('lookup', st.line, {'dataset': lookup[1].lower()}))
            continue
        conditional = re.fullmatch(r'if\s+(.+?)\s+then\s+(.+)', text, re.I)
        if conditional:
            condition, nested = predicate(conditional[1]), action(conditional[2], st.line)
            if condition and nested:
                append_operation(Operation('if', st.line, {'condition': condition, 'operation': asdict(nested)}))
            else:
                reject(st, 'if', 'simple IF THEN assignment or OUTPUT only')
            continue
        if re.match(r'^if\b', text, re.I):
            condition = predicate(re.sub(r'^if\s*', '', text, flags=re.I))
            if condition:
                append_operation(Operation('subset', st.line, {'condition': condition}))
            else:
                reject(st, 'if', 'unsupported subsetting predicate')
            continue
        simple = action(text, st.line)
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
            value = expression(assignment[2])
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
            if re.fullmatch(r'put\s+_all_', text, re.I):
                append_operation(Operation('put_all', st.line, {}))
                plan.matched.append(('put-all', 'DS-025', st.line))
                continue
            items = st.tokens[1:]
            if items and all(item.kind == Kind.STRING for item in items):
                literals = [item.text for item in items]
                try:
                    sas_put_literals(literals)
                except ValueError as exc:
                    reject(st, "put", str(exc))
                else:
                    append_operation(Operation("put_literal", st.line, {"literals": literals}))
                    plan.matched.append(("put-literal", "DS-023", st.line))
                continue
            if items and all(item.kind == Kind.STRING or
                             item.kind == Kind.WORD and re.fullmatch(NAME, item.text)
                             for item in items):
                # Normalized statement text cannot distinguish '41'x from
                # '41' x. Require actual source whitespace before a variable.
                if any(left.kind == Kind.STRING and right.kind == Kind.WORD and
                       (left.end is None or not source[left.end:left.end + 1].isspace())
                       for left, right in zip(items, items[1:])):
                    reject(st, 'put', 'literal-to-variable PUT requires source whitespace; typed literals and comment-only separation need review')
                    continue
                names = [item.text.lower() for item in items if item.kind == Kind.WORD]
                types = put_known_types(step.operations)
                if all(item.kind == Kind.WORD for item in items) and all(types.get(name) == 'number' for name in names):
                    if any(name in ('_n_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_') for name in names):
                        reject(st, 'put', 'PUT automatic variables and special controls require review')
                        continue
                    try:
                        sas_put_numeric_list([None] * len(names))
                    except ValueError as exc:
                        reject(st, 'put', str(exc))
                    else:
                        append_operation(Operation('put_numeric_list', st.line, {'names': names}))
                        plan.matched.append(('put-numeric-list', 'DS-027', st.line))
                    continue
                known = set(step.lengths)
                for previous in walk_operations(step.operations):
                    if previous.kind in ('assign', 'round', 'declare'):
                        known.add(previous.args['name'])
                if any(name in ('_n_', '_infile_', '_file_', '_ods_', '_page_', '_blankpage_') for name in names) or (
                        not step.inputs and not any(o.kind == 'lookup' for o in step.operations)
                        and any(name not in known for name in names)):
                    reject(st, 'put', 'character-list PUT requires declared character variables; automatic or uninitialized numeric variables need review')
                    continue
                resolved = [{'kind': 'literal', 'value': item.text} if item.kind == Kind.STRING
                            else {'kind': 'character', 'value': 'x'} for item in items]
                try:
                    # Minimum-width validation catches literal hazards now;
                    # runtime checks the actual descriptors and values.
                    sas_put_character_list(resolved)
                except ValueError as exc:
                    reject(st, 'put', str(exc))
                else:
                    append_operation(Operation('put_character_list', st.line, {'items': [
                        {'kind': 'literal', 'value': item.text} if item.kind == Kind.STRING
                        else {'kind': 'variable', 'value': item.text.lower()} for item in items]}))
                    plan.matched.append(('put-character-list', 'DS-024', st.line))
                continue
            rest, names = re.sub(r"^put\s*", "", text, flags=re.I), []
            while match := re.match(r"\s*(" + NAME + r")\s*=", rest):
                names.append(match[1].lower())
                rest = rest[match.end():]
            if not names or rest.strip():
                reject(st, "put", "unaccounted for text in named-list PUT")
            else:
                append_operation(Operation("put", st.line, {"names": names}))
            continue
        family, _ = route_function(text)
        reject(st, family if family != "unknown" else construct, "no operation for this statement")
    finish()
    for compiled in plan.steps:
        for op in walk_operations(compiled.operations):
            payloads = [(op.args.get('value'), 'assignment')] if op.kind == 'assign' else [
                (value, 'other') for key, value in op.args.items() if key not in ('body', 'operation')]
            for payload, context in payloads:
                for message in substr_context_errors(payload, context):
                    plan.tickets.append(Ticket(op.line, 'SUBSTR', 'substr', message))
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
    has_strings = any(item[0] == 'concat-catx' for item in plan.matched)
    if has_strings:
        for line in sorted(set(function_call_lines(plan.to_dict(), 'substr'))):
            plan.tickets.append(Ticket(line, 'SUBSTR', 'substr-quarantine',
                'new character features are quarantined from actual SUBSTR calls pending separate temporary-width and composition evidence'))
    if has_strings or any(contains_put(compiled.operations, {'put_character_list', 'put_numeric_list', 'put_all'}) for compiled in plan.steps):
        # Macros resolve before DATA execution. Without taint tracking, even
        # unused or prior-step literals can affect this output contract.
        for st in statements:
            if any(token.kind == Kind.STRING and token.text.startswith('"') and
                   any(char in token.text for char in '&%') for token in st.tokens):
                reject(st, 'concat-catx' if has_strings else 'put', ('bounded character operations' if has_strings else 'bounded PUT') + ' require macro-free source: double-quoted & or % anywhere in the program requires macro review')
    has_all_put = any(contains_put(compiled.operations, {'put_all'}) for compiled in plan.steps)
    if has_strings or has_all_put or any(contains_put(compiled.operations, {'put_numeric_list'}) for compiled in plan.steps):
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
    serialized = plan.to_dict()
    substr_lines = function_call_lines(serialized, 'substr')
    uses_new_character_slice = (function_call_lines(serialized, 'reverse') or
                                any(construct == 'length-list' for construct, _, _ in plan.matched))
    if substr_lines and uses_new_character_slice:
        plan.tickets.append(Ticket(min(line or 1 for line in substr_lines), 'SUBSTR', 'length-reverse',
            'DS-028 quarantines programs containing SUBSTR with REVERSE or multi-name LENGTH pending separate temporary-width and composition evidence'))
    return plan
