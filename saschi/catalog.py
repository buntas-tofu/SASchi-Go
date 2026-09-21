"""saschi.catalog: the DuckDB analysis layer.

The pipeline records every statement, recognized function, and ticket into a
DuckDB catalog, then answers the completeness question as a query rather than
a print statement. DuckDB is already in the gate set (the SQL target rules can
only be proven in an engine); this module gives it a second job, the analysis
spine. The catalog is in-memory by default; pass a path to persist it for
later inspection with any DuckDB client.

Completeness is a query, not an opinion: how many statements routed, how many
functions were recognized, and what blocked the translation. The blocked flag
itself comes from the emitter (emit_py sets it when any ticket exists); this
module records it and reports it, it never re-derives it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import duckdb

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


@dataclass
class Completeness:
    """The accounting a translation reports about itself.

    `blocked` is the emitter's verdict: a translation with any ticket refuses
    to run. `coverage` is the analysis side of the same pass: how many
    statements routed to a known construct. Both are reported, neither is
    derived from the other.
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

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "Catalog":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
