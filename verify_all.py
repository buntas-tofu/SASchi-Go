#!/usr/bin/env python3
"""verify_all.py : run every fixture gate, emit a checksummed receipt to telemetry.

Runs each verifier as a subprocess (with the R runtime on PATH), captures
pass or fail, writes a receipt JSON to the telemetry drive, and appends a run
record. The receipt is the deliverable: per construct, proven against the SAS
rule and agreed across Python and R, traceable to the tool commit that made it.

It also runs the translator suites. Until 2026-09-14 this file covered the 21
fixture gates and nothing that translates: the parser, the router, and the
emitter all sat outside the unified command, and CI ran only the governance
linter and the manifest check. A change that broke translation could pass every
gate here and both CI jobs, which is a gate that says nothing about the thing
it appears to cover. ALL VERIFIED now means the translator is covered too.
"""

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from saschi.provenance import environment, source_state
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEL = Path(os.environ.get("ROSETTA_TELEMETRY", "telemetry"))
def _rbin() -> Path:
    env = os.environ.get("ROSETTA_RBIN")
    if env:
        return Path(env)
    r = shutil.which("Rscript")
    return Path(r).parent if r else Path("")
RBIN = _rbin()

VERIFIERS = [
    ("rounding_n", HERE / "examples" / "verify_rounding.py"),
    ("rounding_n_R", HERE / "examples" / "verify_rounding_r.py"),
    ("intck", HERE / "examples" / "verify_intck.py"),
    ("funcs", HERE / "examples" / "verify_funcs.py"),
    ("bygroup", HERE / "examples" / "verify_bygroup.py"),
    ("sort", HERE / "examples" / "verify_sort.py"),
    ("numfmt", HERE / "examples" / "verify_numfmt.py"),
    ("numstat", HERE / "examples" / "verify_numstat.py"),
    ("weights", HERE / "examples" / "verify_weights.py"),
    ("missarith", HERE / "examples" / "verify_missarith.py"),
    ("merge", HERE / "examples" / "verify_merge.py"),
    ("transpose", HERE / "examples" / "verify_transpose.py"),
    ("intnx", HERE / "examples" / "verify_intnx.py"),
    ("formats", HERE / "examples" / "verify_formats.py"),
    ("arrays", HERE / "examples" / "verify_arrays.py"),
    ("fisher", HERE / "examples" / "verify_fisher.py"),
    ("sigfig", HERE / "examples" / "verify_sigfig.py"),
    ("csvimport", HERE / "examples" / "verify_csvimport.py"),
    ("freq", HERE / "examples" / "verify_freq.py"),
    ("laplace", HERE / "examples" / "verify_laplace.py"),
    ("matrix", HERE / "examples" / "verify_matrix.py"),
]

# The translator suites, run as unittest modules. They carry the same weight as
# a fixture gate in the verdict: a receipt that says ALL VERIFIED says the
# translator was covered, not only the fixture surface.
SUITES = [
    ("suite-parser", "saschi.test_parser"),
    ("suite-rules", "saschi.test_rules"),
    ("suite-emitter", "saschi.test_emit_py"),
    ("suite-rulebook", "saschi.test_rulebook"),
    ("suite-plan", "saschi.test_plan"),
    ("suite-cpp", "saschi.test_cpp"),
    ("suite-operations", "saschi.test_operations"),
]


def git_sha() -> str:
    r = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--short", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() or "NA"


def run_check(name, command, kind, env):
    started = time.monotonic()
    try:
        run = subprocess.run(command, capture_output=True, text=True, cwd=HERE,
                             env=env, timeout=900)
        code, stdout, stderr = run.returncode, run.stdout, run.stderr
    except subprocess.TimeoutExpired as exc:
        code = 124
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        stdout = stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout
        stderr = (stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr) + "\nverification timeout"
    except OSError as exc:
        code, stdout, stderr = 127, "", str(exc)
    combined = (stdout + "\n" + stderr).strip()
    summary = (combined.splitlines() or [""])[-1]
    print(f"[{'PASS' if code == 0 else 'FAIL'}] {name}: {summary}", flush=True)
    return {"construct": name, "verifier": command[-1], "kind": kind,
            "passed": code == 0, "returncode": code, "summary": summary,
            "duration_seconds": time.monotonic() - started,
            "stdout": stdout, "stderr": stderr}


def main() -> int:
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:12]
    env = {**os.environ, "PATH": f"{RBIN}:{os.environ.get('PATH', '')}"}
    runtime, source = environment(), source_state(HERE)
    results = []
    for name, path in VERIFIERS:
        results.append(run_check(name, [sys.executable, str(path)], "fixture", env))
    for name, module in SUITES:
        results.append(run_check(name, [sys.executable, "-m", "unittest", module], "suite", env))
    synth_env = {**env, "K": "10", "ROSETTA_TESTBED": str(TEL.resolve() / "synthesis")}
    results.append(run_check("synthesis", [sys.executable, str(HERE / "synth.py")], "synthesis", synth_env))
    from saschi.test_parser import ROKU_CORPUS
    corpus = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROKU_CORPUS.glob("*.sas"))}
    end_source = source_state(HERE)
    # Generated receipts live in ignored paths and cannot change the source hash.
    stable = source["source_sha256"] == end_source["source_sha256"]
    receipt = {"schema_version": 2, "run_id": run_id, "ts_utc": ts,
               "host": runtime["host"], "tool_git": source["git_commit"],
               "environment": runtime, "source": source, "source_stable": stable,
               "corpus": {"files": corpus, "present": bool(corpus)},
               "evidence": "repository fixtures and cross-language comparisons; no live SAS",
               "constructs": results, "all_passed": stable and all(x["passed"] for x in results)}
    (TEL / "verify").mkdir(parents=True, exist_ok=True)
    (TEL / "runs").mkdir(parents=True, exist_ok=True)
    rp = TEL / "verify" / f"receipt_{run_id}.json"
    rp.write_text(json.dumps(receipt, indent=2) + "\n")
    rec = {"run_id": run_id, "ts_utc": ts, "host": runtime["host"], "op": "verify",
           "tool": "saschi-go/verify_all.py", "tool_git": source["git_commit"],
           "output": str(rp.resolve()), "output_sha256": hashlib.sha256(rp.read_bytes()).hexdigest(),
           "all_passed": receipt["all_passed"]}
    with (TEL / "runs" / "runs.jsonl").open("a") as handle:
        handle.write(json.dumps(rec) + "\n")
    print(f"\nreceipt -> {rp}")
    print("ALL VERIFIED" if receipt["all_passed"] else "SOME FAILED")
    return 0 if receipt["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
