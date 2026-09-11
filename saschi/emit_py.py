"""emit_py: the Python emitter for the data-step subset (Track A step 3).

Translates a SAS program into Python that reproduces SAS behavior by
construction: emitted code imports the semantics reference (sas_semantics)
and calls the pinned functions for every gated construct it touches. The
plan's doctrine: a translated program is accepted because it ran and its
numbers matched, and every emitted line records where it came from.

Slice one covers the rounding program surface: DATA step framing, scalar
assignments over numeric literals and variables, ROUND (DS-012, emitted as
sas_round), and the named-list PUT rendering. Everything else becomes a
ticket: a comment at the statement site plus a Ticket record, never
generated code and never a silent drop. Later slices add merge, BY-group,
conditionals, and the rest of the fixture set.

Output rendering note: PUT is rendered at 17 significant digits, number
fidelity first. SAS's own PUT display format is a later refinement; the
translation tests pin the double, not the typography.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from saschi.parser import split_statements  # noqa: E402
from saschi.rules import route_function, route_statement  # noqa: E402

ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$")
LITERAL_RE = re.compile(r"^-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$")
VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)$")
DATA_RE = re.compile(r"^data\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)
PUT_NAMED_RE = re.compile(r"^put\s+(.*)$", re.I)
PUT_NAME_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=")

EMITTERS_SLICE_ONE = ("round",)


@dataclass
class Ticket:
    """One statement the slice cannot emit; a human reads it, not code."""

    line: int
    statement: str
    construct: str
    reason: str


@dataclass
class Translation:
    """The emitted program plus its accounting."""

    code: str
    matched: list = field(default_factory=list)  # (construct, rule_id, line)
    tickets: list = field(default_factory=list)  # Ticket records


def _split_args(arg_text: str) -> list[str]:
    """Split a call's arguments on top-level commas."""
    args: list[str] = []
    depth = 0
    current = ""
    for ch in arg_text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            args.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        args.append(current.strip())
    return args


def _translate_atom(atom: str) -> str | None:
    """A numeric literal or a variable name emits as-is; else None."""
    if LITERAL_RE.match(atom) or VAR_RE.match(atom):
        return atom
    return None


def translate(source: str) -> Translation:
    """Translate one SAS program (data-step subset) to Python."""
    statements = split_statements(source)
    body: list[str] = []
    matched: list[tuple[str, str, int]] = []
    tickets: list[Ticket] = []
    uses: set[str] = set()

    def emit(code: str, line: int) -> None:
        body.append(f"{code}  # SAS line {line}")

    def ticket(line: int, statement: str, construct: str, reason: str) -> None:
        tickets.append(Ticket(line, statement, construct, reason))
        body.append(f"# TICKET (SAS line {line}): {construct or 'unrouted'};"
                    " human review required, no code emitted.")

    for st in statements:
        text = st.text
        construct, _rule_id = route_statement(text)
        lower = text.lower()

        if construct == "data-step":
            m = DATA_RE.match(text)
            body.append(f"# data step {m.group(1) if m else '?'}"
                        f" (SAS line {st.line})")
            continue
        if lower in ("run", "quit"):
            body.append(f"# {lower}; (SAS line {st.line})")
            continue

        # The function table catches calls in statements the statement
        # table does not claim (the fixture's round calls are assignments).
        fconstruct, frule = route_function(text)
        if construct == "unknown" and fconstruct in EMITTERS_SLICE_ONE:
            construct, _rule_id = fconstruct, frule

        if construct == "round":
            m = ASSIGN_RE.match(text)
            call = CALL_RE.match(m.group(2)) if m else None
            if m and call and call.group(1).lower() == "round":
                args = _split_args(call.group(2))
                if len(args) == 2:
                    a0, a1 = _translate_atom(args[0]), _translate_atom(args[1])
                    if a0 is not None and a1 is not None:
                        uses.add("sas_round")
                        emit(f"{m.group(1)} = sas_round({a0}, {a1})", st.line)
                        matched.append(("round", "DS-012", st.line))
                        continue
            ticket(st.line, text, "round",
                   "only 'name = round(x, unit)' over a literal or variable"
                   " emits in slice one")
            continue

        if construct == "unknown":
            if fconstruct != "unknown":
                ticket(st.line, text, fconstruct,
                       "emitter lands in a later slice")
                continue
            m = ASSIGN_RE.match(text)
            if m:
                atom = _translate_atom(m.group(2))
                if atom is not None:
                    emit(f"{m.group(1)} = {atom}", st.line)
                    continue
                ticket(st.line, text, "assignment",
                       "the right-hand side is not a literal or a variable"
                       " in slice one")
                continue
            m = PUT_NAMED_RE.match(text)
            if m:
                names = PUT_NAME_RE.findall(m.group(1))
                if names:
                    uses.add("_put")
                    pairs = ", ".join(f'("{n}", {n})' for n in names)
                    emit(f"_put([{pairs}])", st.line)
                    continue
                ticket(st.line, text, "put",
                       "only the named-list form (r1= r2=) emits in slice"
                       " one")
                continue
            ticket(st.line, text, construct, "no emitter in slice one")
            continue

        ticket(st.line, text, construct, "no emitter in slice one")

    code_lines = [
        "# Translated by saschi emit_py (Track A step 3, slice one: the",
        "# rounding program surface). Target language: Python. Emitted code",
        "# calls the semantics reference from sas_semantics; run it with the",
        "# repository root importable. Every line traces to a SAS source line.",
        "",
    ]
    if "sas_round" in uses:
        code_lines.append("from sas_semantics import sas_round")
    if "_put" in uses:
        code_lines.append("")
        code_lines.append("def _put(pairs):")
        code_lines.append(
            '    print(" ".join(name + "=" + format(value, ".17g")'
            " for name, value in pairs))")
    code_lines.append("")
    code_lines.extend(body)
    code = "\n".join(code_lines) + "\n"

    return Translation(code=code, matched=matched, tickets=tickets)
