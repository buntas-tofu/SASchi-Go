"""saschi.envcheck: environment readiness for the interface.

Answers "can this machine run the pipeline" before a person discovers the
answer mid-run: the python version, the gate dependencies, the R interpreter,
and the rulebook. Used by `saschi check` and the interactive console. Rich is
reported separately because it is a presentation dependency, not a gate
dependency: the subcommands run without it, the TUI does not.
"""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

from saschi.rules import RulebookError, load_rulebook

REPO_ROOT = Path(__file__).resolve().parent.parent


def _version(module) -> str:
    return getattr(module, "__version__", "installed")


def diagnose() -> list[tuple[str, bool, str]]:
    """Return (label, ok, detail) rows for every environment check."""
    checks: list[tuple[str, bool, str]] = []

    py_ok = sys.version_info >= (3, 11)
    checks.append(("python", py_ok, f"{sys.version.split()[0]} (need 3.11+)"))
    if not py_ok:
        checks[-1] = ("python", False, f"{sys.version.split()[0]} is below 3.11")

    for name in ("yaml", "numpy", "pandas", "scipy", "duckdb"):
        try:
            mod = importlib.import_module(name)
            checks.append((name, True, _version(mod)))
        except Exception as exc:  # noqa: BLE001 - readiness wants the class name
            checks.append((name, False, f"missing ({type(exc).__name__})"))

    try:
        importlib.import_module("rich")
        checks.append(("rich", True, "presentation (TUI)"))
    except Exception as exc:  # noqa: BLE001
        checks.append(
            ("rich", False,
             f"missing ({type(exc).__name__}); the TUI needs it, subcommands do not")
        )

    rscript = shutil.which("Rscript")
    checks.append(
        ("Rscript", rscript is not None,
         rscript or "not on PATH (needed for the R halves of the gold pairs)")
    )

    try:
        rules = load_rulebook(REPO_ROOT / "docs" / "sasconversionrulebook.yaml")
        checks.append(("rulebook", True, f"{len(rules)} rules loaded"))
    except RulebookError as exc:
        checks.append(("rulebook", False, str(exc)))

    return checks
