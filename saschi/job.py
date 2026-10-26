"""Shared job execution: compile, translate, run, compare, receipt.

The run command, the web workbench, and the showcase all render from this
single path, so the artifacts a job produces are the artifacts a viewer
reads. Nothing here talks to a network, a terminal, or a file outside the
three paths a caller hands in.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .compare import table_equal
from .emit_cpp import translate as cpp_translate
from .emit_py import Translation, translate as python_translate
from .plan import Plan, compile_plan
from .parser import ParseError
from .provenance import environment, implementation_hashes
from .runtime import run_plan


@dataclass
class Job:
    source: str
    source_sha256: str
    plan: Plan
    translation: Translation
    receipt: dict
    result: "dict | None"
    code: int


def _completeness_record(source: str, plan, target: str, ts_utc: str) -> dict:
    """The analysis accounting for this pass, or an explicit unavailable status.

    duckdb lives in the verify extra, not in the base install, so the job path
    must keep working on a machine that has only the package. Silence is not an
    option: the receipt says which case it is, the same way every other claim in
    it carries its own status.
    """
    try:
        from .catalog import record_pass
    except ImportError as exc:
        return {'status': 'unavailable',
                'reason': f'catalog requires duckdb (verify extra): {exc}'}
    try:
        cat, completeness = record_pass(source, plan, file='<job>', target=target,
                                        ts_utc=ts_utc)
    except ParseError as exc:
        # The compiler already carries the lexical ticket. Accounting cannot
        # split malformed source, but must not prevent its blocked receipt.
        return {'status': 'unavailable', 'reason': f'source parsing failed: {exc}'}
    try:
        return completeness.as_record()
    finally:
        cat.close()


def _read_expected(path: Path) -> tuple[object, str]:
    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    text = raw.decode(json.detect_encoding(raw), 'surrogatepass')
    del raw
    # Match json.loads(bytes), including encoding detection and BOM errors,
    # while releasing raw bytes before allocating the parsed table graph.
    return json.JSONDecoder().decode(text), checksum


def build_job(source: str, inputs: "Path | None" = None, expect: "Path | None" = None,
              target: str = "python") -> Job:
    """Run one program through the full treatment and return every artifact."""
    plan = compile_plan(source)
    translation = (python_translate if target == 'python' else cpp_translate)(source)
    # Target-specific refusals must block execution and appear in the receipt,
    # just like source-plan tickets. A Python-supported call can exceed C++.
    plan.tickets = list(translation.tickets)
    receipt = {'schema_version': 1, 'package_version': __version__,
               'ts_utc': datetime.now(timezone.utc).isoformat(), 'target': target,
               'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(), 'environment': environment(),
               'implementation_sha256': implementation_hashes(),
               'evidence': 'repository behavior contracts; no live SAS',
               'plan_sha256': hashlib.sha256(json.dumps(plan.to_dict(), sort_keys=True).encode()).hexdigest(),
               'tickets': [vars(t) for t in plan.tickets], 'accepted': False,
               'comparison': 'not requested', 'comparison_contract': 'typed-exact-values-ordered-rows-and-columns-metadata-v1'}
    receipt['completeness'] = _completeness_record(source, plan, target, receipt['ts_utc'])
    result, code = None, 2 if plan.blocked else 1
    try:
        if plan.blocked:
            raise ValueError('translation blocked by unsupported statements')
        input_bytes = inputs.read_bytes() if inputs else None
        catalog = json.loads(input_bytes) if input_bytes is not None else {}
        receipt['input_sha256'] = hashlib.sha256(input_bytes).hexdigest() if input_bytes is not None else None
        result = run_plan(plan.to_dict(), catalog)
        del input_bytes, catalog
        if expect:
            expected, expected_sha256 = _read_expected(expect)
            receipt['expected_sha256'] = expected_sha256
            if not isinstance(expected, dict) or not expected:
                raise ValueError('expected output must name at least one dataset')
            for name, table in expected.items():
                if not table_equal(result['datasets'].get(name), table):
                    receipt['comparison'] = 'failed'
                    raise ValueError(f'expected dataset differs: {name}')
            receipt['comparison'] = 'passed'
        receipt['accepted'], code = True, 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        receipt['error'] = str(exc)
    return Job(source, receipt['source_sha256'], plan, translation, receipt, result, code)
