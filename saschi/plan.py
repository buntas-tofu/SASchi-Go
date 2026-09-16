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


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    tickets: list[Ticket] = field(default_factory=list)
    matched: list[tuple[str, str, int]] = field(default_factory=list)
    version: int = 1

    @property
    def blocked(self):
        return bool(self.tickets)

    def to_dict(self):
        return asdict(self)


def atom(text):
    text = text.strip()
    if text == ".":
        return {"kind": "missing", "value": None}
    if NUMBER.fullmatch(text):
        value = float(text)
        if math.isfinite(value):
            return {"kind": "number", "value": value}
    if re.fullmatch(NAME, text):
        return {"kind": "variable", "value": text.lower()}
    return None


def compile_plan(source: str) -> Plan:
    plan, step, context = Plan(), None, None

    def reject(st, construct, reason):
        plan.tickets.append(Ticket(st.line, st.text, construct, reason))

    def finish():
        if step and step.kind in ("sort", "merge") and not step.by:
            plan.tickets.append(Ticket(step.line, step.name, "by", "BY keys are required"))

    try:
        statements = split_statements(source)
    except ParseError as exc:
        plan.tickets.append(Ticket(exc.line, "", "unterminated", str(exc)))
        return plan
    for st in statements:
        text = st.text
        if re.search(r"\b(?:_N_|_ERROR_|_ALL_|_NUMERIC_|_CHARACTER_)\b", text, re.I):
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
            if step.kind not in ("sort", "merge") or step.by or not words or any(
                    not re.fullmatch(NAME, w) or w.lower() in ("descending", "notsorted") for w in words):
                reject(st, "by", "only one ascending BY list on SORT or MERGE is supported")
            elif len(set(w.lower() for w in words)) != len(words):
                reject(st, "by", "duplicate BY keys are unsupported")
            else:
                step.by = [w.lower() for w in words]
            continue
        if re.match(r"^(set|merge)\b", text, re.I):
            m = re.fullmatch(r"(set|merge)\s+(" + NAME + r")(?:\s+(" + NAME + "))?", text, re.I)
            if (not m or context != "data" or step.inputs or step.operations or
                    (m[1].lower() == "set" and m[3]) or (m[1].lower() == "merge" and not m[3])):
                reject(st, construct, "one SET input or two MERGE inputs must precede computations")
            else:
                step.inputs = [v.lower() for v in (m[2], m[3]) if v]
                if m[1].lower() == "merge":
                    step.kind = "merge"
                plan.matched.append((m[1].lower(), "DS-001" if m[1].lower() == "set" else "DS-002", st.line))
            continue
        if context != "data":
            reject(st, construct, "unsupported procedure clause")
            continue
        assignment = re.fullmatch(r"(" + NAME + r")\s*=\s*(.+)", text)
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
