"""saschi.pipeline: the end-to-end translation process.

One function, run(), is the golden path the interface drives: load the
rulebook, split a SAS program, recognize functions, route every statement to a
construct, emit the translated target, and record the whole pass into the
DuckDB catalog so completeness is a query and not a print statement.

The completeness verdict is the emitter's: a translation with any ticket is
blocked (it refuses to run), and that is the whole of "complete". The catalog
adds visibility on top of that verdict: which statements routed, which
functions were recognized, and how the tickets group by construct.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from saschi.catalog import Catalog, Completeness
from saschi.emit_py import Translation, translate
from saschi.parser import Statement, split_statements
from saschi.rules import CONSTRUCT_MAP, FUNCTION_ROUTER, load_rulebook, route_statement

REPO_ROOT = Path(__file__).resolve().parent.parent

_FUNC_NAME_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_DQ_STRING_RE = re.compile(r'"(?:[^"]|"")*"')
_SQ_STRING_RE = re.compile(r"'(?:[^']|'')*'")


def _mask_strings(text: str) -> str:
    """Blank quoted spans so function recognition reads code, not data."""
    text = _DQ_STRING_RE.sub(" ", text)
    return _SQ_STRING_RE.sub(" ", text)


def _git_sha() -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
        )
        return r.stdout.strip() or "NA"
    except OSError:
        return "NA"


@dataclass
class FunctionHit:
    line: int
    name: str
    construct: str
    rule_id: str


@dataclass
class PipelineResult:
    file: str
    target: str
    statements: list[Statement]
    functions: list[FunctionHit]
    translation: Translation
    completeness: Completeness
    rule_count: int


def function_hits(text: str, line: int) -> list[FunctionHit]:
    """Recognize function calls in one statement, code only.

    Iterates the rulebook's FUNCTION_ROUTER so recognition and routing can
    never disagree about a function's family. First match per pattern, name
    upper-cased for grouping. Strings are masked first so a literal that
    looks like a call is not counted as a call. Recognition is a census, not
    an exhaustive parse: it reports what is present, not a parse tree.
    """
    code = _mask_strings(text)
    hits: list[FunctionHit] = []
    for rx, construct in FUNCTION_ROUTER:
        m = rx.search(code)
        if not m:
            continue
        nm = _FUNC_NAME_RE.search(m.group(0))
        name = nm.group(1).upper() if nm else "?"
        hits.append(FunctionHit(line, name, construct, CONSTRUCT_MAP.get(construct, "")))
    return hits


def run(source: str, *, file: str = "<stdin>", target: str = "python",
        allow_partial: bool = False,
        catalog_path: str | None = None) -> PipelineResult:
    """Translate one SAS program and record the pass.

    Returns a PipelineResult carrying the split statements, the recognized
    functions, the emitter's Translation, and the Completeness accounting read
    back from the catalog. The rulebook is loaded from the shipped YAML and
    its size rides along so the interface can report it.
    """
    rules = load_rulebook()
    statements = split_statements(source)

    statement_rows: list[tuple] = []
    for st in statements:
        construct, rule_id = route_statement(st.text)
        statement_rows.append((st.line, st.text, construct, rule_id, st.terminated))

    functions = [hit for st in statements for hit in function_hits(st.text, st.line)]
    translation = translate(source, allow_partial=allow_partial)

    with Catalog(catalog_path) as cat:
        cat.record_statements(statement_rows)
        cat.record_functions(
            [(f.line, f.name, f.construct, f.rule_id) for f in functions]
        )
        cat.record_tickets(
            [(t.line, t.construct, t.reason) for t in translation.tickets]
        )
        cat.record_run(
            file=file,
            target=target,
            ts_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            n_statements=len(statements),
            n_functions=len(functions),
            n_matched=len(translation.matched),
            n_tickets=len(translation.tickets),
            blocked=translation.blocked,
            tool_git=_git_sha(),
        )
        completeness = cat.completeness()

    return PipelineResult(
        file=file,
        target=target,
        statements=statements,
        functions=functions,
        translation=translation,
        completeness=completeness,
        rule_count=len(rules),
    )
