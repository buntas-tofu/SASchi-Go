#!/usr/bin/env python3
"""verify_all.py : run every fixture gate, emit a signed receipt to telemetry.

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
]


def git_sha() -> str:
    r = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--short", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() or "NA"


def main() -> int:
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    host, sha = "local", git_sha()
    env = {**os.environ, "PATH": f"{RBIN}:{os.environ.get('PATH', '')}"}

    results = []
    for name, path in VERIFIERS:
        if not path.exists():
            results.append({"construct": name, "verifier": path.name,
                            "kind": "fixture",
                            "passed": False, "summary": "verifier missing"})
            print(f"[MISS] {name}: {path.name} not found")
            continue
        r = subprocess.run([sys.executable, str(path)], capture_output=True,
                           text=True, env=env)
        tail = (r.stdout.strip().splitlines() or [r.stderr.strip()[:120] or ""])[-1]
        results.append({"construct": name, "verifier": path.name,
                        "kind": "fixture",
                        "passed": r.returncode == 0, "summary": tail})
        print(f"[{'PASS' if r.returncode == 0 else 'FAIL'}] {name}: {tail}")

    for name, module in SUITES:
        r = subprocess.run([sys.executable, "-m", "unittest", module],
                           capture_output=True, text=True, cwd=str(HERE), env=env)
        combined = (r.stdout.strip() + "\n" + r.stderr.strip()).strip()
        tail = (combined.splitlines() or [""])[-1]
        results.append({"construct": name, "verifier": module, "kind": "suite",
                        "passed": r.returncode == 0, "summary": tail})
        print(f"[{'PASS' if r.returncode == 0 else 'FAIL'}] {name}: {tail}")

    receipt = {"ts_utc": ts, "host": host, "tool_git": sha,
               "constructs": results,
               "all_passed": all(x["passed"] for x in results)}
    (TEL / "verify").mkdir(parents=True, exist_ok=True)
    (TEL / "runs").mkdir(parents=True, exist_ok=True)
    rp = TEL / "verify" / f"receipt_{ts.replace(':', '')}.json"
    rp.write_text(json.dumps(receipt, indent=2))

    rec = {"run_id": f"verify-{ts}", "ts_utc": ts, "host": host, "op": "verify",
           "tool": "saschi-go/verify_all.py", "tool_git": sha,
           "output": f"telemetry/verify/{rp.name}",
           "output_sha256_16": hashlib.sha256(rp.read_bytes()).hexdigest()[:16],
           "all_passed": receipt["all_passed"]}
    with open(TEL / "runs" / "runs.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")

    print(f"\nreceipt -> {rp}")
    print("ALL VERIFIED" if receipt["all_passed"] else "SOME FAILED")
    return 0 if receipt["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
