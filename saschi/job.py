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


def build_job(source: str, inputs: "Path | None" = None, expect: "Path | None" = None,
              target: str = "python") -> Job:
    """Run one program through the full treatment and return every artifact."""
    plan = compile_plan(source)
    receipt = {'schema_version': 1, 'package_version': __version__,
               'ts_utc': datetime.now(timezone.utc).isoformat(), 'target': target,
               'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(), 'environment': environment(),
               'implementation_sha256': implementation_hashes(),
               'evidence': 'repository behavior contracts; no live SAS',
               'plan_sha256': hashlib.sha256(json.dumps(plan.to_dict(), sort_keys=True).encode()).hexdigest(),
               'tickets': [vars(t) for t in plan.tickets], 'accepted': False,
               'comparison': 'not requested', 'comparison_contract': 'typed-exact-values-ordered-rows-and-columns-metadata-v1'}
    translation = (python_translate if target == 'python' else cpp_translate)(source)
    result, code = None, 2 if plan.blocked else 1
    try:
        if plan.blocked:
            raise ValueError('translation blocked by unsupported statements')
        input_bytes = inputs.read_bytes() if inputs else None
        catalog = json.loads(input_bytes) if input_bytes is not None else {}
        receipt['input_sha256'] = hashlib.sha256(input_bytes).hexdigest() if input_bytes is not None else None
        result = run_plan(plan.to_dict(), catalog)
        if expect:
            expected_bytes = expect.read_bytes()
            expected = json.loads(expected_bytes)
            receipt['expected_sha256'] = hashlib.sha256(expected_bytes).hexdigest()
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
