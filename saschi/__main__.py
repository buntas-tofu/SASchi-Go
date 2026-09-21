"""saschi.__main__: the interface.

`python -m saschi` opens the interactive console; `python -m saschi <command>`
runs one step of the pipeline. Commands:

  analyze FILE.sas     parse, recognize functions, route; print the
                       completeness report without emitting code
  translate FILE.sas   the full pipeline: emit translated code and the report
  check                environment readiness (python, gate deps, R, rulebook)
  verify               run the fixture gate suite (verify_all.py)

Exit status: analyze and translate exit 1 when the translation is blocked
(any ticket), so a script can detect an incomplete conversion; check exits 1
when any dependency is missing; verify forwards the gate suite's own code.
Rich renders the reports when it is installed and falls back to plain text
otherwise, so the subcommands never depend on the presentation library.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from saschi.pipeline import PipelineResult, run

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read_source(path: str | None) -> tuple[str, str]:
    """Return (source_text, display_name) for a path or stdin."""
    if path and path != "-":
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(path)
        return p.read_text(encoding="utf-8"), p.name
    return sys.stdin.read(), "<stdin>"


def result_to_dict(result: PipelineResult, include_code: bool = False) -> dict:
    c = result.completeness
    return {
        "file": result.file,
        "target": result.target,
        "rule_count": result.rule_count,
        "completeness": {
            "n_statements": c.n_statements,
            "n_terminated": c.n_terminated,
            "n_routed": c.n_routed,
            "n_unrouted": c.n_unrouted,
            "n_functions": c.n_functions,
            "n_matched": c.n_matched,
            "n_tickets": c.n_tickets,
            "blocked": c.blocked,
            "coverage": c.coverage,
            "complete": c.complete,
            "tickets_by_construct": c.tickets_by_construct,
        },
        "functions": [
            {"line": f.line, "name": f.name, "construct": f.construct,
             "rule_id": f.rule_id}
            for f in result.functions
        ],
        "tickets": [
            {"line": t.line, "construct": t.construct, "reason": t.reason}
            for t in result.translation.tickets
        ],
        **({"code": result.translation.code} if include_code else {}),
    }


def _render_plain(result: PipelineResult, show_code: bool) -> None:
    c = result.completeness
    print(f"file: {result.file}  target: {result.target}")
    print(f"verdict: {'COMPLETE' if c.complete else 'BLOCKED'}")
    print(f"statements: {c.n_statements} ({c.n_terminated} terminated)")
    print(f"functions recognized: {c.n_functions}")
    print(f"emitted: {c.n_matched}")
    print(f"tickets: {c.n_tickets}")
    print(f"coverage: {c.coverage:.0%}")
    if c.tickets_by_construct:
        print("tickets by construct:")
        for k, v in c.tickets_by_construct.items():
            print(f"  {k}: {v}")
    if c.n_tickets:
        print("tickets:")
        for tk in result.translation.tickets:
            print(f"  line {tk.line}: {tk.construct} - {tk.reason}")
    if result.functions:
        print("recognized functions:")
        for f in result.functions:
            print(f"  line {f.line}: {f.name} -> {f.construct} ({f.rule_id})")
    if show_code:
        print("--- translated code ---")
        sys.stdout.write(result.translation.code)


def _render(result: PipelineResult, *, show_code: bool,
            rich: bool, stream=None) -> None:
    if rich:
        from saschi.tui import render_report
        render_report(result, show_code=show_code, stream=stream)
    else:
        _render_plain(result, show_code)


def _render_check(rows, rich: bool) -> None:
    if rich:
        from saschi.tui import render_check
        render_check(rows)
    else:
        for name, ok, detail in rows:
            print(f"{'[ok]' if ok else '[missing]'} {name}: {detail}")


def _has_rich() -> bool:
    try:
        import rich  # noqa: F401
        return True
    except ImportError:
        return False


def _run_verify() -> int:
    r = subprocess.run([sys.executable, str(REPO_ROOT / "verify_all.py")],
                       cwd=str(REPO_ROOT))
    return r.returncode


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="saschi",
        description="SAS-to-open-language translation pipeline (Track A).",
    )
    sub = ap.add_subparsers(dest="command")

    a = sub.add_parser(
        "analyze",
        help="parse, recognize functions, and route a SAS program; print the "
             "completeness report without emitting code",
    )
    a.add_argument("file", nargs="?",
                   help="path to a .sas program (default: read stdin)")
    a.add_argument("--catalog", help="persist the analysis to a DuckDB file")
    a.add_argument("--json", action="store_true",
                   help="print the report as JSON instead of a table")

    t = sub.add_parser(
        "translate",
        help="run the full pipeline and write the translated program plus the "
             "report",
    )
    t.add_argument("file", nargs="?",
                   help="path to a .sas program (default: read stdin)")
    t.add_argument("-o", "--output",
                   help="write the translated code to this path "
                        "(default: print code to stdout, report to stderr)")
    t.add_argument("--lang", choices=["python"], default="python",
                   help="target language (only python emits today)")
    t.add_argument("--allow-partial", action="store_true",
                   help="when blocked, emit the partial body as an inspection "
                        "artifact instead of the refusing module")
    t.add_argument("--catalog", help="persist the analysis to a DuckDB file")
    t.add_argument("--json", action="store_true",
                   help="print the report as JSON instead of a table")

    sub.add_parser("check", help="report environment readiness")

    v = sub.add_parser("verify", help="run the fixture gate suite "
                                      "(verify_all.py)")
    v.add_argument("--receipt", action="store_true",
                   help="after a green run, print the newest receipt path")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rich = _has_rich()

    if args.command is None:
        if not rich:
            build_parser().print_help()
            print("\n[missing] rich: install `pip install rich` for the "
                  "interactive console, or pass a subcommand.")
            return 1
        from saschi.tui import interactive
        return interactive()

    if args.command == "check":
        from saschi.envcheck import diagnose
        rows = diagnose()
        _render_check(rows, rich)
        return 0 if all(ok for _, ok, _ in rows) else 1

    if args.command == "verify":
        return _run_verify()

    if args.command in ("analyze", "translate"):
        if args.file is None and sys.stdin.isatty():
            build_parser().parse_args([args.command, "--help"])
            return 2
        try:
            source, name = _read_source(args.file)
        except FileNotFoundError as exc:
            print(f"error: cannot read {exc}", file=sys.stderr)
            return 2

        result = run(source, file=name, target=getattr(args, "lang", "python"),
                     allow_partial=getattr(args, "allow_partial", False),
                     catalog_path=args.catalog)

        if args.json:
            print(json.dumps(result_to_dict(
                result, include_code=(args.command == "translate")), indent=2))
        elif args.command == "translate" and args.output:
            Path(args.output).write_text(result.translation.code, encoding="utf-8")
            _render(result, show_code=False, rich=rich)
            print(f"translated code -> {args.output}")
        elif args.command == "translate":
            # Code to stdout (piped), report to stderr so the code stays clean.
            sys.stdout.write(result.translation.code)
            _render(result, show_code=False, rich=rich, stream=_stderr_console(rich))
        else:
            _render(result, show_code=False, rich=rich)

        return 0 if result.completeness.complete else 1

    build_parser().print_help()
    return 2


def _stderr_console(rich: bool):
    if not rich:
        return None
    from rich.console import Console
    return Console(stderr=True)


if __name__ == "__main__":
    raise SystemExit(main())
