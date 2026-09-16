"""Versioned, target-independent operations for the executable SAS subset.

Names are case-insensitive strings, numbers are binary64 values, and steps own
local state. Unsupported statements remain tickets; no backend can clear them.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from .parser import ParseError, split_statements
from .rules import route_function, route_statement

NAME = r"[A-Za-z_][A-Za-z0-9_]{0,31}"
NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\Z")


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


def expression(text):
    value = atom(text)
    if value is not None:
        return value
    match = re.fullmatch(r'(' + NAME + r')\s*([+\-])\s*(.+)', text.strip())
    if match and atom(match[3]) is not None:
        return {'kind': 'arithmetic', 'left': atom(match[1]), 'op': match[2], 'right': atom(match[3])}
    return None


def predicate(text):
    value = atom(text)
    if value is not None:
        return {'left': value, 'op': 'truth'}
    match = re.fullmatch(r'(.+?)\s*(<=|>=|\^=|~=|<>|=|<|>|\beq\b|\bne\b|\blt\b|\bgt\b|\ble\b|\bge\b)\s*(.+)', text, re.I)
    if match and atom(match[1]) is not None and atom(match[3]) is not None:
        return {'left': atom(match[1]), 'op': match[2].lower(), 'right': atom(match[3])}
    return None


def action(text, line):
    match = re.fullmatch(r'output(?:\s+(' + NAME + r'))?', text, re.I)
    if match:
        return Operation('output', line, {'target': match[1].lower() if match[1] else None})
    match = re.fullmatch(r'(' + NAME + r')\s*=\s*(.+)', text)
    if match and match[1].lower() != '_n_' and expression(match[2]) is not None:
        return Operation('assign', line, {'name': match[1].lower(), 'value': expression(match[2])})
    return None


def compile_plan(source: str) -> Plan:
    plan, step, context = Plan(), None, None

    def reject(st, construct, reason):
        plan.tickets.append(Ticket(st.line, st.text, construct, reason))

    def finish():
        if step:
            def check(ops):
                for op in ops:
                    if op.kind == 'output' and op.args['target'] not in (None, step.name):
                        plan.tickets.append(Ticket(op.line, str(op.args['target']), 'output', 'OUTPUT target must be the declared DATA destination'))
                    if op.kind == 'if':
                        nested = op.args['operation']
                        check([Operation(**nested)])
            check(step.operations)
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
        if re.search(r"\b(?:_ERROR_|_ALL_|_NUMERIC_|_CHARACTER_)\b", text, re.I):
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
                step.operations.append(Operation("read", st.line, {"datasets": step.inputs}))
                if m[1].lower() == "merge":
                    step.kind = "merge"
                plan.matched.append((m[1].lower(), "DS-001" if m[1].lower() == "set" else "DS-002", st.line))
            continue
        if context != "data":
            reject(st, construct, "unsupported procedure clause")
            continue
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
                step.operations.append(Operation('declare', st.line, {'name': declaration[1].lower(), 'spec': 'number'}))
            else:
                reject(st, 'retain', 'RETAIN requires one variable and a numeric or missing initializer')
            continue
        declaration = re.fullmatch(r'length\s+(' + NAME + r')\s+\$\s*(\d+)', text, re.I)
        if declaration:
            name, width = declaration[1].lower(), int(declaration[2])
            if step.inputs or any(o.kind != 'declare' for o in step.operations) or name in step.lengths or name == '_n_' or not 1 <= width <= 32767:
                reject(st, 'length', 'character LENGTH must precede SET and computations; width 1..32767')
            else:
                step.lengths[name] = width
                step.operations.append(Operation('declare', st.line, {'name': name, 'spec': {'type': 'character', 'length': width}}))
            continue
        lookup = re.fullmatch(r'if\s+_n_\s*=\s*1\s+then\s+set\s+(' + NAME + r')', text, re.I)
        if lookup:
            if step.inputs or any(o.kind != 'declare' for o in step.operations):
                reject(st, 'lookup', 'one initial lookup SET must precede the driving SET')
            else:
                step.operations.append(Operation('lookup', st.line, {'dataset': lookup[1].lower()}))
            continue
        conditional = re.fullmatch(r'if\s+(.+?)\s+then\s+(.+)', text, re.I)
        if conditional:
            condition, nested = predicate(conditional[1]), action(conditional[2], st.line)
            if condition and nested:
                step.operations.append(Operation('if', st.line, {'condition': condition, 'operation': asdict(nested)}))
            else:
                reject(st, 'if', 'simple IF THEN assignment or OUTPUT only')
            continue
        if re.match(r'^if\b', text, re.I):
            condition = predicate(re.sub(r'^if\s*', '', text, flags=re.I))
            if condition:
                step.operations.append(Operation('subset', st.line, {'condition': condition}))
            else:
                reject(st, 'if', 'unsupported subsetting predicate')
            continue
        simple = action(text, st.line)
        if simple:
            step.operations.append(simple)
            continue
        assignment = re.fullmatch(r"(" + NAME + r")\s*=\s*(.+)", text)
        if assignment and assignment[1].lower() == '_n_':
            reject(st, 'automatic-variable', 'assignment to _N_ is outside this slice')
            continue
        if assignment:
            value = atom(assignment[2])
            if value is not None:
                step.operations.append(Operation("assign", st.line, {"name": assignment[1].lower(), "value": value}))
                continue
            call = re.fullmatch(r"round\s*\(([^,]+),([^,]+)\)", assignment[2], re.I)
            if call and atom(call[1]) is not None and atom(call[2]) is not None:
                step.operations.append(Operation("round", st.line, {"name": assignment[1].lower(), "value": atom(call[1]), "unit": atom(call[2])}))
                plan.matched.append(("round", "DS-012", st.line))
                continue
            family, _ = route_function(assignment[2])
            reject(st, family if family != "unknown" else "assignment", "unsupported expression")
            continue
        if re.match(r"^put\b", text, re.I):
            rest, names = re.sub(r"^put\s*", "", text, flags=re.I), []
            while match := re.match(r"\s*(" + NAME + r")\s*=", rest):
                names.append(match[1].lower())
                rest = rest[match.end():]
            if not names or rest.strip():
                reject(st, "put", "unaccounted for text in named-list PUT")
            else:
                step.operations.append(Operation("put", st.line, {"names": names}))
            continue
        family, _ = route_function(text)
        reject(st, family if family != "unknown" else construct, "no operation for this statement")
    finish()
    return plan
