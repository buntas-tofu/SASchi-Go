# SASchi-Go User Guide

Reproducing SAS behavior in open languages (Python, R) with receipts.

This guide is for anyone using SASchi-Go: running the fixture gates,
reading the receipts, and understanding what this repository proves and
does not prove. It is the companion to the [README](../README.md). The
verification method itself is documented in the repository history; the
doctrine lives in the gate suite and the receipts.

## What SASchi-Go proves

SASchi-Go proves that specific SAS constructs behave the way this
repository says they do in Python and R. The proof is executable: every
construct family has a fixture gate that pins hand-derived truth, runs the
Python reference implementation and the R twin, and requires byte-equal
agreement at a documented tolerance. A claim in the README or the rulebook
is only as good as the gate behind it.

The core doctrine: a translated program is accepted because it ran and
its numbers matched, not because it looked right. The receipt is the
evidence; the gate suite is the proof; nothing is verified by assertion.

## Repository layout

- `sas_semantics.py` : the reference implementations of SAS-quirk
  functions. This is the law the verifiers check against.
- `examples/` : the gold pairs. One SAS construct family per fixture:
  a Python verifier (`verify_*.py`), an R twin (`*.R`), and in most cases
  fixture data embedded in the verifier.
- `docs/sasconversionrulebook.yaml` : the machine-consumable translation
  rulebook. 54 rules across data-step (DS), PROC SQL (SQL), statistical
  procs (ST), survey procs (SV), and the macro layer (MC), each with an
  equivalence class (EXACT, EQUIVALENT-WITH-SETTINGS, APPROXIMATE,
  NO-DIRECT-EQUIVALENT), required settings, forbidden patterns, and
  validation tests.
- `docs/macro_surface_census.md` (+ `.csv`) : the macro-surface frequency
  table. Data about code, never code: which macro features appear in the
  licensed public testbed, at what density, and under which licenses.
- `kb01/sas_semantics_reference.txt` : the semantics reference as plain
  text, for humans and for diffs. It stays in lockstep with
  `sas_semantics.py`.
- `manifest.py` : pin a SAS corpus with content hashes and provenance.
- `synth.py` : program-level synthesis across characterized construct
  families, seeded and deterministic. Runs cross-language and reference
  gates; the live-SAS capture stage is optional and license-gated.
- `tools/macro_census.py` : the deterministic, pure-stdlib scanner that
  regenerates the macro-surface census.
- `saschi/` : the program-level translator package (Track A). `rules.py`
  loads the rulebook and routes SAS statements and function calls to rule
  families. Tests in `saschi/test_rules.py`.
- `verify_all.py` : runs every fixture gate, emits a signed receipt JSON.
  One command, the whole proof.
- `telemetry/` : run artifacts (receipts, run records). Gitignored;
  rerun `verify_all.py` to regenerate.

## Requirements

- Python 3.11+ with numpy, pandas, scipy, and PyYAML. The repository's
  own venv (for example `~/besaid/.venv`) carries the gate stack.
- R (for the R halves of the gold pairs). `Rscript` must be on PATH, or
  set `ROSETTA_RSCRIPT` to the full path. The R interpreter is found via
  `ROSETTA_RSCRIPT`, then `Rscript` on PATH.
- No other runtime dependencies. The linter and the census tool are pure
  standard library.

## Running the gates

One command, from the repository root:

```sh
python verify_all.py
```

Use the venv python that has the gate stack, for example:

```sh
~/besaid/.venv/bin/python verify_all.py
```

A bare system python3 without numpy and pandas produces phantom
`ModuleNotFoundError` failures that look like gate regressions; check the
traceback type before chasing a failure.

What you will see:

```text
[PASS] rounding_n: VERIFIED: translation matches SAS semantics on all fixtures
[PASS] merge: VERIFIED: MERGE BY matches the PDV rule and agrees Python/R
...
receipt -> telemetry/verify/receipt_2026-09-10T124918Z.json
ALL VERIFIED
```

`ALL VERIFIED` is the bar. `SOME FAILED` means at least one gate failed;
the failing construct names appear in the output.

Each verifier also runs standalone, for example:

```sh
~/besaid/.venv/bin/python examples/verify_merge.py
```

## Reading the receipts

Each run writes a receipt JSON to `telemetry/verify/` named with the UTC
timestamp:

```json
{
  "ts_utc": "2026-09-10T12:49:18Z",
  "host": "local",
  "tool_git": "826d4d1",
  "constructs": [
    {"construct": "rounding_n", "verifier": "verify_rounding.py",
     "passed": true, "summary": "VERIFIED: ..."}
  ],
  "all_passed": true
}
```

- `tool_git` pins the receipt to the exact commit that produced it.
- `constructs` is one entry per fixture gate with a pass/fail and the
  final summary line.
- `all_passed` is the verdict. Judge by `all_passed` in the newest
  receipt when multiple runs exist; cite receipts by timestamp.
- The same run appends a compact record to `telemetry/runs/runs.jsonl`
  with an output sha256 prefix.

Receipts are run artifacts and are gitignored; they are never committed.
They regenerate every run, so the deliverable is the ability to reproduce
them, not the files themselves.

## Running the translator package tests

The rulebook loader and construct router carry their own unit tests,
run against the shipped YAML:

```sh
~/besaid/.venv/bin/python -m unittest saschi.test_rules -v
```

28 tests: rule count and uniqueness, family counts, ticket semantics for
NO-DIRECT-EQUIVALENT rules, construct-map integrity, statement routing
(PROC SORT, TRANSPOSE, FREQ, SQL with INTO and remerge hints, GLM, macro
statements), and function routing (ROUND, INTCK, LAG, TRANWRD, SUM).

## Running the macro-surface census

```sh
python3 tools/macro_census.py
```

Regenerates `docs/macro_surface_census.csv` and
`docs/macro_surface_census.md` from the licensed public testbed
(`~/besaid/rosetta_testbed/public`). Deterministic: identical output on
identical input. The estate bench under `testbed/local/` is never written
to the shipped output; `--include-local` prints a private comparison to
stdout only.

## What the equivalence classes mean

- `EXACT` : the open-language implementation reproduces SAS output to the
  documented precision (often 1e-10 or tighter) with the settings the rule
  names. No settings negotiation.
- `EQUIVALENT-WITH-SETTINGS` : the open-language implementation matches
  SAS once the rule's required_settings are applied. The settings are
  mandatory, not advisory; omitting one is a defect.
- `APPROXIMATE` : the open-language result is close but not guaranteed
  identical (for example factor rotations, some ESM paths). The rule
  names the tolerance and what may differ.
- `NO-DIRECT-EQUIVALENT` : no open-language construct reproduces SAS here.
  The rule is a ticket: emit a human-review ticket, never generated code.

## What routes to a ticket

The translator's v1 scope is data-step only. Constructs without a direct
equivalent and every family that is not yet gated route to a human-review
ticket rather than generated code:

- Merge with both sides repeating BY values (DS-003): a data property,
  detected by per-key group-size cross-tab at runtime, never by statement
  shape.
- CALL EXECUTE and dynamic code construction (MC-004): detection and
  ticket only, by ruling.
- PROC SQL remerge (SQL-002): flagged by the aggregation-with-detail
  pattern.
- Survey selection at the seed level (SV-006): inclusion probabilities
  validate, individual draws never.
- PROC IML (GP-09): no direct translation target; route to human review.

## Verifying a new construct family

A new family lands as the seven-file change set, and every gate must pass
before it is real:

1. `sas_semantics.py` : the reference function(s), with a section comment
   naming the SAS surface and the landmine.
2. `kb01/sas_semantics_reference.txt` : the same in plain text, same pass.
3. `examples/<fam>.R` : the R twin.
4. `examples/verify_<fam>.py` : the gate. Reference pins first, then R
   lane agreement, then landmine demonstrations.
5. `docs/sasconversionrulebook.yaml` : the rule entry.
6. `verify_all.py` : register the verifier in the VERIFIERS list.
7. `README.md` : one known-landmine bullet.

Pins come from three engines agreeing (pure reference, scipy, R) before
anything is written; a gate whose pins came from one engine is a
tautology. Every family pins at least one landmine case: a value where
SAS and the naive open-language default disagree.

The full recipe lives in the project skill (saschi-gate-families) and the
verifier skeletons in its references.

## The style floor

Every artifact that leaves this repository follows the Inertia-Drift-Framework
floor: no em dashes, no ellipses. The floor is enforced by the linter
(`scripts/inertia-drift-lint`), never by hand. The linter also checks
balanced DMF fences, link-pointer integrity, manifest schema, and
status-line presence. It runs on every push in CI.

```sh
python3 scripts/inertia-drift-lint .
```

## Known landmines (why the gate exists)

The README carries the current list. The shape of the list:

- SAS `round(x, unit)` rounds half away from zero; Python and R round
  half to even by default.
- R `ifelse` evaluates both branches whole-vector; the SAS ladder short
  circuits.
- SAS missing values sort first and compare low; NaN and NA do neither
  consistently.
- Significant digits are a rounding problem, not a format problem.
- PROC IMPORT guesses CSV types from a 20-row window; pandas and R infer
  from the whole file.
- PROC FREQ percents are three separate denominators (cell, row, column).

## Troubleshooting

- `ModuleNotFoundError: No module named 'pandas'` : you are using a bare
  system python3. Use the venv python that carries the gate stack.
- `Rscript not found` : install R (on Debian/Ubuntu:
  `apt-get install r-base-core`) or set `ROSETTA_RSCRIPT` to the full
  path.
- `receipt ... crashed` on a fresh clone : the telemetry directories were
  missing in an older version; run `mkdir -p telemetry/verify telemetry/runs`
  or update past the fix in verify_all.py.
- A gate fails after you changed `sas_semantics.py` : the kb01 plain-text
  mirror must change in the same pass; the two are in lockstep by design.
- The linter flags an em dash in a file you did not touch : the file
  predates the floor; fix the character, do not add an ignore.

## License

MIT. See [LICENSE](../LICENSE).
