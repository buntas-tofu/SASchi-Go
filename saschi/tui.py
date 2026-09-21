"""Rich presentation layer for the operator commands.

SASchi-Go ships a JSON-first command line (doctor, inspect, translate, run)
and this console, which renders the same commands for a person. Launch it
bare to open the menu, or pass a .sas file to open that file in context.
"""
from __future__ import annotations

import argparse
import io
import json
from argparse import Namespace
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.syntax import Syntax

from . import __version__
from .emit_cpp import translate as cpp_translate
from .emit_py import translate as py_translate
from .plan import compile_plan
from .provenance import environment

console = Console()

YES = "[green]yes[/green]"
NO = "[red]no[/red]"


def _banner(title: str) -> Panel:
    return Panel(title, subtitle=f"SASchi-Go {__version__}", box=box.HEAVY)


def render_doctor() -> bool:
    """Render the verification environment and report whether it is complete."""
    info = environment()
    console.print(_banner("Environment"))
    runtime = Table(box=box.SIMPLE_HEAD, title="Runtime")
    runtime.add_column("Item", style="bold")
    runtime.add_column("Value")
    runtime.add_row("host", info["host"])
    runtime.add_row("platform", info["platform"])
    runtime.add_row("python", info["python"])
    runtime.add_row("interpreter", info["python_executable"])
    runtime.add_row("R", info["r_version"] if info["r_version"] else NO)
    runtime.add_row("C++17", info["cpp_version"] if info["cpp_version"] else NO)
    console.print(runtime)
    packages = Table(box=box.SIMPLE_HEAD, title="Gate packages")
    packages.add_column("Package", style="bold")
    packages.add_column("Version")
    for name, version in info["packages"].items():
        packages.add_row(name, version if version else NO)
    console.print(packages)
    missing = [name for name, version in info["packages"].items() if version is None]
    if not info["r_version"]:
        missing.append("Rscript")
    if not info["cpp_version"]:
        missing.append("C++17 compiler")
    if missing:
        console.print(f"[red]Missing: {', '.join(missing)}[/red]")
    else:
        console.print("[green]Environment complete.[/green]")
    return not missing


def render_plan(plan) -> None:
    """Render a compiled plan: steps, matched constructs, and tickets."""
    console.print(_banner(f"Plan: {len(plan.steps)} steps, {len(plan.tickets)} tickets"))
    if plan.steps:
        steps = Table(box=box.SIMPLE_HEAD, title="Steps")
        steps.add_column("Line", justify="right")
        steps.add_column("Kind", style="bold")
        steps.add_column("Name")
        steps.add_column("Inputs")
        steps.add_column("Ops", justify="right")
        for step in plan.steps:
            steps.add_row(
                str(step.line),
                step.kind,
                step.name,
                ", ".join(step.inputs) if step.inputs else "-",
                str(len(step.operations)),
            )
        console.print(steps)
    if plan.matched:
        matched = Table(box=box.SIMPLE_HEAD, title="Matched constructs")
        matched.add_column("Kind", style="bold")
        matched.add_column("Rule")
        matched.add_column("Line", justify="right")
        for kind, rule, line in plan.matched:
            matched.add_row(kind, rule, str(line))
        console.print(matched)
    if plan.tickets:
        tickets = Table(box=box.SIMPLE_HEAD, title="Tickets")
        tickets.add_column("Line", justify="right")
        tickets.add_column("Construct", style="bold")
        tickets.add_column("Reason")
        for ticket in plan.tickets:
            tickets.add_row(str(ticket.line), ticket.construct, ticket.reason)
        console.print(tickets)
    if plan.blocked:
        console.print("[red]BLOCKED: the program cannot execute as written.[/red]")
    else:
        console.print("[green]Clean: every statement is accounted for.[/green]")


def render_translation(translation, target: str) -> None:
    """Render a translation result: status, tickets, and emitted code."""
    console.print(_banner(f"Translation: {target}"))
    if translation.blocked:
        console.print("[red]BLOCKED: inspection artifact only; nothing executes.[/red]")
    else:
        console.print("[green]Accepted: the program translated without tickets.[/green]")
    if translation.tickets:
        tickets = Table(box=box.SIMPLE_HEAD, title="Tickets")
        tickets.add_column("Line", justify="right")
        tickets.add_column("Construct", style="bold")
        tickets.add_column("Reason")
        for ticket in translation.tickets:
            tickets.add_row(str(ticket.line), ticket.construct, ticket.reason)
        console.print(tickets)
    language = "python" if target == "python" else "cpp"
    console.print(Panel(Syntax(translation.code, language, line_numbers=True), title="Emitted code"))


def render_receipt(receipt: dict) -> None:
    """Render a run receipt: acceptance, comparison, and provenance."""
    accepted = bool(receipt.get("accepted"))
    title = "ACCEPTED" if accepted else "NOT ACCEPTED"
    style = "green" if accepted else "red"
    console.print(_banner(f"Run: [{style}]{title}[/{style}]"))
    table = Table(box=box.SIMPLE_HEAD)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("comparison", receipt.get("comparison", "not requested"))
    table.add_row("target", receipt.get("target", "-"))
    table.add_row("package", receipt.get("package_version", "-"))
    table.add_row("timestamp", receipt.get("ts_utc", "-"))
    source_hash = receipt.get("source_sha256") or "-"
    table.add_row("source sha256", source_hash[:16])
    if receipt.get("error"):
        table.add_row("error", receipt["error"])
    console.print(table)
    tickets = receipt.get("tickets") or []
    if tickets:
        ticket_table = Table(box=box.SIMPLE_HEAD, title="Tickets")
        ticket_table.add_column("Line", justify="right")
        ticket_table.add_column("Construct", style="bold")
        ticket_table.add_column("Reason")
        for ticket in tickets:
            ticket_table.add_row(
                str(ticket.get("line", "-")),
                ticket.get("construct", "-"),
                ticket.get("reason", "-"),
            )
        console.print(ticket_table)


def _run(source: Path, inputs, expect, output: Path) -> int:
    """Execute a bounded workflow through the canonical CLI and render its receipt."""
    from .cli import execute_job

    args = Namespace(source=source, inputs=inputs, expect=expect, output=output)
    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            code = execute_job(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    receipt_path = output.resolve() / "receipt.json"
    if receipt_path.is_file():
        render_receipt(json.loads(receipt_path.read_text(encoding="utf-8")))
        console.print(f"receipt: {receipt_path}")
    return code


def _choose_target() -> str:
    return Prompt.ask("target", choices=["python", "cpp"], default="python")


def _inspect_file(path: Path) -> int:
    plan = compile_plan(path.read_text(encoding="utf-8"))
    render_plan(plan)
    return 2 if plan.blocked else 0


def _translate_file(path: Path, target: str) -> int:
    source = path.read_text(encoding="utf-8")
    translation = (py_translate if target == "python" else cpp_translate)(source)
    render_translation(translation, target)
    return 2 if translation.blocked else 0


def _run_file(path: Path) -> int:
    inputs = Prompt.ask("inputs json (optional, enter to skip)") or None
    expect = Prompt.ask("expect json (optional, enter to skip)") or None
    stamp = datetime.now().strftime("%H%M%S")
    default = str(path.with_suffix(f".receipt-{stamp}"))
    output = Path(Prompt.ask("output directory", default=default))
    return _run(path, Path(inputs) if inputs else None, Path(expect) if expect else None, output)


def _file_loop(path: Path) -> int:
    while True:
        console.print(_banner(f"File: {path}"))
        console.print("  [bold]i[/bold]nspect   plan and tickets")
        console.print("  [bold]t[/bold]ranslate emit translation")
        console.print("  [bold]r[/bold]un       execute and write a receipt")
        console.print("  [bold]d[/bold]octor   environment")
        console.print("  [bold]q[/bold]uit     leave")
        choice = Prompt.ask("choose", choices=["i", "t", "r", "d", "q"], default="i")
        if choice == "q":
            return 0
        if choice == "d":
            render_doctor()
        elif choice == "i":
            _inspect_file(path)
        elif choice == "t":
            _translate_file(path, _choose_target())
        elif choice == "r":
            _run_file(path)


def _menu() -> int:
    while True:
        console.print(_banner("SASchi-Go"))
        console.print("  [bold]d[/bold]octor    environment")
        console.print("  [bold]o[/bold]pen      a .sas file")
        console.print("  [bold]q[/bold]uit      leave")
        choice = Prompt.ask("choose", choices=["d", "o", "q"], default="o")
        if choice == "q":
            return 0
        if choice == "d":
            render_doctor()
        elif choice == "o":
            path = Path(Prompt.ask("path to .sas file"))
            if not path.is_file():
                console.print(f"[red]{path} is not a file.[/red]")
                continue
            _file_loop(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="saschi tui")
    parser.add_argument("source", nargs="?", type=Path, help="a .sas file to open in context")
    parser.add_argument(
        "--command",
        choices=("doctor", "inspect", "translate", "run"),
        help="render one command and exit",
    )
    parser.add_argument("--target", choices=("python", "cpp"), default="python")
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--expect", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return 0 if render_doctor() else 1
    if args.command in ("inspect", "translate", "run") and args.source is None:
        console.print("[red]this command needs a source file.[/red]")
        return 2
    if args.command == "inspect":
        return _inspect_file(args.source)
    if args.command == "translate":
        return _translate_file(args.source, args.target)
    if args.command == "run":
        if args.output is None:
            console.print("[red]run needs --output.[/red]")
            return 2
        return _run(args.source, args.inputs, args.expect, args.output)
    if args.source is not None:
        return _file_loop(args.source)
    return _menu()


if __name__ == "__main__":
    raise SystemExit(main())
