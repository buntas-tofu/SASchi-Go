"""saschi.catalog: the DuckDB analysis layer.

A pass records every statement, recognized function, and ticket into a DuckDB
catalog, then answers the completeness question as a query rather than a print
statement. DuckDB is already in the gate set (the SQL target rules can only be
proven in an engine); this module gives it a second job, the analysis spine. The
catalog is in-memory by default; pass a path to persist it for later inspection
with any DuckDB client.

Completeness is a query, not an opinion: how many statements routed, how many
functions were recognized, and what blocked the translation. The blocked flag
itself comes from the plan (a plan with any ticket is blocked); this module
records it and reports it, it never re-derives it.

Dependency posture: duckdb lives in the `verify` extra, not in the base install,
so `saschi.job` imports this module lazily and a machine without duckdb still
runs jobs. A receipt records either the accounting or an explicit unavailable
status, never silence.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS statements ("
    " line INTEGER, statement VARCHAR, construct VARCHAR,"
    " rule_id VARCHAR, terminated BOOLEAN)",
    "CREATE TABLE IF NOT EXISTS functions ("
    " line INTEGER, name VARCHAR, construct VARCHAR, rule_id VARCHAR)",
    "CREATE TABLE IF NOT EXISTS tickets ("
    " line INTEGER, construct VARCHAR, reason VARCHAR)",
    "CREATE TABLE IF NOT EXISTS run ("
    " file VARCHAR, target VARCHAR, ts_utc VARCHAR, n_statements INTEGER,"
    " n_functions INTEGER, n_matched INTEGER, n_tickets INTEGER,"
    " blocked BOOLEAN, tool_git VARCHAR)",
]

# Function recognition reads code, not data: quoted spans are blanked first, or
# a call-shaped string inside a literal would be recorded as a real call.
_FUNC_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_DQ_STRING_RE = re.compile(r'"(?:[^"]|"")*"')
_SQ_STRING_RE = re.compile(r"'(?:[^']|'')*'")


def _mask_strings(text: str) -> str:
    """Blank quoted spans so function recognition reads code, not data."""
    text = _DQ_STRING_RE.sub(" ", text)
    return _SQ_STRING_RE.sub(" ", text)


def tool_git() -> str:
    """The short commit that produced this record, or NA outside a checkout."""
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
        )
        return r.stdout.strip() or "NA"
    except OSError:
        return "NA"


@dataclass
class Completeness:
    """The accounting a translation reports about itself.

    `blocked` is the plan's verdict: a plan with any ticket refuses to run.
    `coverage` is the analysis side of the same pass: the fraction of statements
    that produced no ticket. Both are reported, neither is derived from the
    other.
    """

    n_statements: int = 0
    n_terminated: int = 0
    n_routed: int = 0
    n_unrouted: int = 0
    n_functions: int = 0
    n_matched: int = 0
    n_tickets: int = 0
    blocked: bool = False
    tickets_by_construct: dict[str, int] = field(default_factory=dict)

    @property
    def coverage(self) -> float:
        """Fraction of statements the translation accounted for without a ticket.

        This is the honest coverage number, not the statement-router hit rate:
        scalar assignments and the named-list PUT route to "unknown" at the
        statement level yet are fully handled by the emitter, so they are
        covered in the only sense that matters (no ticket). Framing statements
        (data-step, run, quit) are also accounted for, so a program of only
        framing is fully covered.
        """
        if not self.n_statements:
            return 0.0
        return (self.n_statements - self.n_tickets) / self.n_statements

    @property
    def complete(self) -> bool:
        """True when the translation is not blocked (zero tickets)."""
        return not self.blocked

    def as_record(self) -> dict:
        """The receipt form, carrying its own status line."""
        return {
            "status": "recorded",
            "evidence": "statement and ticket accounting from this pass; not a live SAS comparison",
            "n_statements": self.n_statements,
            "n_terminated": self.n_terminated,
            "n_routed": self.n_routed,
            "n_unrouted": self.n_unrouted,
            "n_functions": self.n_functions,
            "n_matched": self.n_matched,
            "n_tickets": self.n_tickets,
            "blocked": self.blocked,
            "coverage": round(self.coverage, 6),
            "tickets_by_construct": dict(self.tickets_by_construct),
        }


class Catalog:
    """A DuckDB connection holding one translation pass.

    The connection is in-memory by default so a one-off run leaves nothing on
    disk. Pass a path to persist the catalog beside the input for later
    inspection.
    """

    def __init__(self, path: Optional[str] = None):
        self._con = duckdb.connect(path if path else ":memory:")
        for statement in SCHEMA:
            self._con.execute(statement)
        self.path = path

    def record_statements(self, rows: list[tuple]) -> None:
        if not rows:
            return
        self._con.executemany(
            "INSERT INTO statements VALUES (?, ?, ?, ?, ?)", rows
        )

    def record_functions(self, rows: list[tuple]) -> None:
        if not rows:
            return
        self._con.executemany(
            "INSERT INTO functions VALUES (?, ?, ?, ?)", rows
        )

    def record_tickets(self, rows: list[tuple]) -> None:
        if not rows:
            return
        self._con.executemany(
            "INSERT INTO tickets VALUES (?, ?, ?)", rows
        )

    def record_run(self, *, file: str, target: str, ts_utc: str,
                   n_statements: int, n_functions: int, n_matched: int,
                   n_tickets: int, blocked: bool, tool_git: str) -> None:
        self._con.execute(
            "INSERT INTO run VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [file, target, ts_utc, n_statements, n_functions, n_matched,
             n_tickets, blocked, tool_git],
        )

    def completeness(self) -> Completeness:
        c = Completeness()
        row = self._con.execute(
            "SELECT COUNT(*),"
            " COALESCE(SUM(CASE WHEN terminated THEN 1 ELSE 0 END), 0),"
            " COALESCE(SUM(CASE WHEN construct != 'unknown' THEN 1 ELSE 0 END), 0),"
            " COALESCE(SUM(CASE WHEN construct = 'unknown' THEN 1 ELSE 0 END), 0)"
            " FROM statements"
        ).fetchone()
        c.n_statements, c.n_terminated, c.n_routed, c.n_unrouted = row
        c.n_functions = self._con.execute(
            "SELECT COUNT(*) FROM functions").fetchone()[0]
        c.n_tickets = self._con.execute(
            "SELECT COUNT(*) FROM tickets").fetchone()[0]
        c.tickets_by_construct = {
            r[0]: r[1]
            for r in self._con.execute(
                "SELECT construct, COUNT(*) FROM tickets"
                " GROUP BY construct ORDER BY COUNT(*) DESC"
            ).fetchall()
        }
        run_row = self._con.execute(
            "SELECT n_matched, blocked FROM run").fetchone()
        if run_row:
            c.n_matched, c.blocked = run_row
        return c

    def functions_seen(self) -> list[str]:
        """Function names recorded by the pass, in row order.

        Exposed so a caller (and a test) can inspect what recognition actually
        saw without reaching into the connection.
        """
        return [r[0] for r in self._con.execute(
            "SELECT name FROM functions ORDER BY line").fetchall()]

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "Catalog":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def record_pass(source: str, plan, *, file: str = "<source>",
                target: str = "python", ts_utc: Optional[str] = None,
                git: Optional[str] = None) -> "tuple[Catalog, Completeness]":
    """Record one translation pass from the source and its compiled plan.

    The statement and function rows come from the source itself (the parser and
    the statement router), so the statement accounting is about the program, not
    about the plan's internal shape. Blocked status and the ticket rows come
    from the plan, which is the emitter's own verdict. Nothing is re-derived
    from the other side, which is what makes the two counts a cross-check.
    """
    from .parser import split_statements
    from .rules import route_function, route_statement

    statements = split_statements(source)
    cat = Catalog()
    statement_rows = []
    function_rows = []
    for st in statements:
        construct, rule_id = route_statement(st.text)
        statement_rows.append(
            (st.line, st.text, construct, rule_id, bool(st.terminated)))
        masked = _mask_strings(st.text)
        seen: set[str] = set()
        for m in _FUNC_CALL_RE.finditer(masked):
            name = m.group(1).upper()
            if name in seen:
                continue
            seen.add(name)
            f_construct, f_rule = route_function(m.group(0))
            function_rows.append((st.line, name, f_construct, f_rule))
    cat.record_statements(statement_rows)
    cat.record_functions(function_rows)
    cat.record_tickets([(t.line, t.construct, t.reason) for t in plan.tickets])
    matched = sum(1 for row in function_rows if row[2] != "unknown")
    cat.record_run(
        file=file, target=target,
        ts_utc=ts_utc or datetime.now(timezone.utc).isoformat(),
        n_statements=len(statement_rows), n_functions=len(function_rows),
        n_matched=matched, n_tickets=len(plan.tickets), blocked=bool(plan.blocked),
        tool_git=git if git is not None else tool_git(),
    )
    return cat, cat.completeness()
