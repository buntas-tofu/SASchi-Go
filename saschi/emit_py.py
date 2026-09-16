"""Python backend for the versioned plan, preserving diagnostics and source lines."""
from dataclasses import dataclass, field
from pprint import pformat
from .plan import Ticket, compile_plan


@dataclass
class Translation:
    code: str
    matched: list = field(default_factory=list)
    tickets: list = field(default_factory=list)
    blocked: bool = False
    plan: dict = field(default_factory=dict)


def translate(source: str, allow_partial: bool = False) -> Translation:
    parsed = compile_plan(source)
    plan = parsed.to_dict()
    lines = [
        "# SASchi plan version 1, Python target.",
        "# Scope: numeric DATA steps, scalar assignments, ROUND, named-list PUT,",
        "# one SET input, two-input MERGE BY, ascending PROC SORT and NODUPKEY.",
        "# Evidence: repository fixtures; not a live-SAS comparison.",
    ]
    for step in parsed.steps:
        lines.append(f"# SAS line {step.line}: {step.kind} {step.name}")
        for op in step.operations:
            lines.append(f"# SAS line {op.line}: {op.kind}")
    for ticket in parsed.tickets:
        lines.append(f"# TICKET (SAS line {ticket.line}): {ticket.construct}")
    if parsed.blocked and not allow_partial:
        lines += ["# BLOCKED: inspection artifact; execution is refused.",
                  "raise RuntimeError('saschi: blocked translation. Nothing from this program was executed.')"]
    else:
        if parsed.blocked:
            lines.append("# PARTIAL: inspection only; output is not the source program's output.")
        lines += ["from saschi.runtime import run_plan", "", "_plan = " + pformat(plan, sort_dicts=False),
                  f"result = run_plan(_plan, globals().get('inputs', {{}}), allow_partial={allow_partial!r})",
                  "for _line in result['log']:", "    print(_line)"]
    return Translation("\n".join(lines) + "\n", parsed.matched, parsed.tickets, parsed.blocked, plan)
