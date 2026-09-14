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

A ticket BLOCKS the artifact. Until 2026-09-14 a ticket was a comment at the
statement site while the rest of the program emitted and ran, so a program
whose control flow was dropped still produced an executable file that looked
like a successful translation: the IF became a comment and its body executed
anyway. A blocked unit now emits diagnostics plus a partial body that is never
called, and the module raises when executed, so the artifact and the report
cannot disagree about whether the program ran. The partial body stays readable
through translate(source, allow_partial=True), which marks the file as an
inspection artifact rather than a conversion.

Zero tickets means every semantically relevant token was accounted for. A
statement the emitter accepts and then reduces tickets rather than emitting the
reduction: `put x= "suffix"` used to emit the name and drop the literal, DATA
options were consumed as framing, and a statement the splitter could not fence
was translated whatever fragment it happened to hold. Each of those is refused
now, and the emitted artifact declares the scope it was checked against.
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
# One item of the named-list form: a name immediately followed by `=`. Anchored
# at the front because the caller consumes items one at a time and then holds
# whatever is left over against the statement.
PUT_ITEM_RE = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")

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
    """The emitted program plus its accounting.

    `blocked` is the load-bearing field: a translation with tickets did not
    cover the program, so `code` refuses to execute. Anything reading this
    object must check `blocked` rather than assume a non-empty `code` is
    runnable.
    """

    code: str
    matched: list = field(default_factory=list)  # (construct, rule_id, line)
    tickets: list = field(default_factory=list)  # Ticket records
    blocked: bool = False


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


def _consume_put_names(items: str) -> tuple[list[str], str]:
    """Consume the `name=` items of a named-list PUT and return what is left.

    The emitter used to collect every `name=` in the statement and ignore
    whatever else was there, so `put x= "suffix"` emitted the name, dropped the
    literal, and reported zero tickets. The leftover text is returned so the
    caller can refuse a statement it did not fully account for.
    """
    names: list[str] = []
    rest = items
    while True:
        m = PUT_ITEM_RE.match(rest)
        if not m:
            break
        names.append(m.group(1))
        rest = rest[m.end():]
    return names, rest.strip()


def translate(source: str, allow_partial: bool = False) -> Translation:
    """Translate one SAS program (data-step subset) to Python.

    Zero tickets means the whole program was covered and `code` runs. Any
    ticket means the program was covered only in part: `code` carries the
    diagnostics and a body that is never called, and executing it raises.
    `allow_partial` returns the partial body as runnable code for inspection,
    marked on its face as not a conversion.
    """
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
        # A statement the splitter could not fence has no known boundary. The
        # text may be a fragment of a longer statement or two statements fused,
        # so translating it would be a guess wearing the costume of a
        # translation.
        if not st.terminated:
            ticket(st.line, text, "unterminated",
                   "the splitter could not find this statement's terminator, so "
                   "its boundary is unknown")
            continue
        construct, _rule_id = route_statement(text)
        lower = text.lower()

        if construct == "data-step":
            m = DATA_RE.match(text)
            name = m.group(1) if m else "?"
            # DATA options change what the step produces and none of them are
            # implemented, so accepting them as framing would silently drop
            # behaviour the program asked for.
            leftover = text[m.end():].strip() if m else text
            if leftover:
                ticket(st.line, text, "data-step",
                       f"DATA options are not implemented: {leftover!r}")
                continue
            body.append(f"# data step {name} (SAS line {st.line})")
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
                names, leftover = _consume_put_names(m.group(1))
                if names and not leftover:
                    uses.add("_put")
                    pairs = ", ".join(f'("{n}", {n})' for n in names)
                    emit(f"_put([{pairs}])", st.line)
                    continue
                if names:
                    # Accepted and then silently reduced is the worst of the
                    # three outcomes, so the leftover text is refused by name.
                    ticket(st.line, text, "put",
                           "the named-list form takes only name= items, so "
                           f"{leftover!r} is unaccounted for")
                    continue
                ticket(st.line, text, "put",
                       "only the named-list form (r1= r2=) emits in slice"
                       " one")
                continue
            ticket(st.line, text, construct, "no emitter in slice one")
            continue

        ticket(st.line, text, construct, "no emitter in slice one")

    blocked = bool(tickets)
    header = [
        "# Translated by saschi emit_py (Track A step 3, slice one: the",
        "# rounding program surface). Target language: Python. Emitted code",
        "# calls the semantics reference from sas_semantics; run it with the",
        "# repository root importable. Every line traces to a SAS source line.",
        "#",
        "# Scope: a scalar and log demonstration, not a dataset-producing",
        "# program. It computes values and prints them. SET, MERGE, BY, RETAIN,",
        "# and OUTPUT are not modelled, so a statement that uses one tickets",
        "# instead of emitting.",
    ]
    if blocked and not allow_partial:
        header += [
            "#",
            f"# BLOCKED: {len(tickets)} unsupported construct(s). This is NOT a runnable",
            "# conversion. Emitting it as code would execute statements whose",
            "# surrounding control flow was dropped, which changes what the program",
            "# means while looking like a translation that worked.",
            "#",
            "# The partial body below is preserved so a person can read it. It is",
            "# never called and this module refuses to execute.",
        ]
    elif blocked:
        header += [
            "#",
            f"# PARTIAL: {len(tickets)} unsupported construct(s). This body is an",
            "# inspection artifact, not a conversion. Statements whose control flow",
            "# was dropped still execute here, so this output is not the program's",
            "# output.",
        ]

    code_lines = list(header) + [""]
    if "sas_round" in uses:
        code_lines.append("from sas_semantics import sas_round")
    if "_put" in uses:
        code_lines.append("")
        code_lines.append("def _put(pairs):")
        code_lines.append(
            '    print(" ".join(name + "=" + format(value, ".17g")'
            " for name, value in pairs))")

    if blocked and not allow_partial:
        # A function whose body is only comments has no body as far as Python is
        # concerned, so a program that ticketed on every statement would emit a
        # file that does not compile. That failure is worse than the one this
        # gate exists to prevent, so the inert body always carries a statement.
        inert = list(body)
        if not inert or all(
            not line.strip() or line.lstrip().startswith("#") for line in inert
        ):
            inert = ["pass"] + inert
        code_lines += ["", "def _unreachable_partial_body():"]
        code_lines += [f"    {line}" if line else "" for line in inert]
        code_lines += [
            "",
            "raise RuntimeError(",
            f'    "saschi: blocked translation, {len(tickets)} unsupported construct(s)."',
            '    " Nothing from this program was executed."',
            ")",
        ]
    else:
        code_lines.append("")
        code_lines.extend(body)
    code = "\n".join(code_lines) + "\n"

    return Translation(code=code, matched=matched, tickets=tickets, blocked=blocked)
