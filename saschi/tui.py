"""saschi.tui: the rich terminal interface.

The interactive console and the rich report renderers. Rich is the only
presentation dependency; the pipeline and catalog never import it, so the gate
suite stays free of a UI dependency. The subcommands fall back to plain text
when rich is absent; the interactive console requires it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table

from saschi.envcheck import diagnose
from saschi.pipeline import PipelineResult, run

REPO_ROOT = Path(__file__).resolve().parent.parent
console = Console()


def _ticket_table(result: PipelineResult) -> Table:
    t = Table(box=box.ROUNDED, title="Tickets (what blocked the translation)")
    t.add_column("line", justify="right")
    t.add_column("construct")
    t.add_column("reason")
    for tk in result.translation.tickets:
        t.add_row(str(tk.line), tk.construct, tk.reason)
    return t


def _function_table(result: PipelineResult) -> Table:
    t = Table(box=box.ROUNDED, title="Recognized functions")
    t.add_column("line", justify="right")
    t.add_column("function")
    t.add_column("construct")
    t.add_column("rule")
    for f in result.functions:
        t.add_row(str(f.line), f.name, f.construct, f.rule_id)
    return t


def render_report(result: PipelineResult, *, show_code: bool,
                  stream: Console | None = None) -> None:
    out = console if stream is None else stream
    c = result.completeness
    verdict = "complete" if c.complete else "BLOCKED"
    style = "green" if c.complete else "red"
    summary = (
        f"[bold]{result.file}[/bold] -> {result.target}   "
        f"[{style}]{verdict}[/{style}]\n"
        f"statements [bold]{c.n_statements}[/bold] "
        f"({c.n_terminated} terminated)   "
        f"functions [bold]{c.n_functions}[/bold]   "
        f"emitted [bold]{c.n_matched}[/bold]   "
        f"tickets [bold]{c.n_tickets}[/bold]   "
        f"coverage [bold]{c.coverage:.0%}[/bold]"
    )
    out.print(Panel(summary, title="SASchi-Go translation", border_style=style))
    if c.n_tickets:
        out.print(_ticket_table(result))
    if result.functions:
        out.print(_function_table(result))
    if show_code:
        out.print(Panel(
            Syntax(result.translation.code, "python", line_numbers=False),
            title="Translated python", border_style=style))


def render_check(rows) -> None:
    t = Table(box=box.ROUNDED, title="Environment readiness")
    t.add_column("component")
    t.add_column("status")
    t.add_column("detail")
    for name, ok, detail in rows:
        t.add_row(name, "[green]ok[/green]" if ok else "[red]missing[/red]", detail)
    console.print(t)


def _verify() -> None:
    console.print("[dim]running the gate suite (verify_all.py)...[/dim]")
    r = subprocess.run([sys.executable, str(REPO_ROOT / "verify_all.py")],
                       cwd=str(REPO_ROOT))
    if r.returncode != 0:
        console.print("[red]the gate suite reported a failure.[/red]")


def interactive() -> int:
    """The menu loop: run steps of the pipeline without remembering flags."""
    console.print(Panel(
        "Analyze or translate a SAS program, check the environment, or run the\n"
        "gate suite. Type a command.",
        title="SASchi-Go", border_style="blue"))
    while True:
        try:
            choice = Prompt.ask(
                "command",
                choices=["analyze", "translate", "check", "verify", "quit"],
                default="analyze",
            )
        except (EOFError, KeyboardInterrupt):
            console.print()
            return 0

        if choice == "quit":
            console.print("[dim]bye[/dim]")
            return 0
        if choice == "check":
            render_check(diagnose())
            continue
        if choice == "verify":
            _verify()
            continue

        path = Prompt.ask("path to .sas file")
        if not path:
            continue
        try:
            source = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            console.print(f"[red]cannot read {path}: {exc}[/red]")
            continue

        result = run(source, file=path)
        render_report(result, show_code=(choice == "translate"))
