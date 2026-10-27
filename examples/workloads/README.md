# Workload testing

Status: exploratory repository/base-R evidence for maintainer review. No live
SAS observation or production throughput claim. The existing fixture gates and
their acceptance policies are unchanged. Run receipts, including failed attempts,
are written to ignored telemetry directories.

## Small checks in CI

The existing Verification job runs both runners with `--sizes 1000` after the
unchanged `verify_all.py` command. Each keeps its hand pin, edge cases and all
refusal/comparator controls: 17 ledger checks and 21 character-workload checks.
Both are mandatory steps. Each runs unless the workflow is cancelled, including
after an earlier step fails, and any failed check fails the job. Bash pipefail
preserves the runner's exit status while `tee` records its console transcript.

The always-run `workload-diagnostics` artifact contains `telemetry/workloads/`,
including reports, per-case receipts, CSV/JSON inputs and expected/observed data,
process logs, metrics and the two console transcripts. The existing
`verify-receipt` artifact is unchanged. Diagnostics are attempted even after
failure or cancellation. Missing/failed R and comparison/refusal errors remain
failures. RSS and elapsed time are recorded without performance thresholds;
the existing worker timeout still bounds hung processes.

Larger scales remain available through the standalone commands below. Workload
checks strengthen the existing CI job without changing the 40 fixture gates,
30 suites, synthesis or their execution order. `ALL VERIFIED` still refers to
the registered golden-command checks; CI also requires both workload steps.

## Monthly usage ledger

[The original program](monthly_ledger/job.sas) reads synthetic account readings,
filters excluded records, rounds half-unit readings to whole units, sorts by
account/period/sequence, and performs a numeric one-to-many outer match merge.
An account lookup supplies a fixed adjustment. A final DATA step excludes
lookup-only records before BY groups form, computes LAG/DIF and retained totals,
assigns character categories with CATX, and writes detail and closing snapshots.
Missing readings are queued before they are replaced with zero for totals.
Unmatched account adjustments remain ordinary missing.

[The independent base-R witness](monthly_ledger/reference.R) uses vector and
table operations, with no translator or semantics-reference helpers. A manually
calculated nine-row result additionally pins the small fixture. Inputs are
original and synthetic. No external source program, organization data, or SAS
runtime is required.

From the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/run_workloads.py \
  --output telemetry/workloads/my-first-run --sizes 1000 10000 50000
```

Use a new output path each time. The runner requires base R, fails on unavailable
or failed witnesses, and never skips a case. Each case compares all five generated
tables through the public CLI, then executes the emitted Python in a separate
process. Values, row/column order, descriptors, character padding, and table
metadata compare exactly. Readings are finite half-unit numbers or ordinary
missing, so whole-unit outputs and their bounded totals are exactly representable.
This evidence does not extend to arbitrary decimal rounding or large magnitudes.

The pilot includes empty inputs, all-excluded readings, missing lookups, zero
usage, duplicate periods, shuffled rows, missing values, and increasing row
counts. Sequence numbers provide deterministic order within duplicate periods.
Seed and row counts are recorded. One fresh R, CLI, and emitted-Python process
per case supplies elapsed time and, on Linux with `/usr/bin/time`, peak RSS.
The CLI and emitted Python share the execution engine. The runner also uses the
CLI's JSON writer for its artifacts; the independent behavior witness is base R.
Timings include startup and file I/O; they are single observations without a
performance threshold. Row counts are bounded to 100000 and processes have an
explicit timeout.
On POSIX systems, timeouts stop the timing wrapper and its worker process group,
then drain/reap the process before finalizing logs. The tested verification
profile is Linux. Missing base R writes a failed `report.json` before returning
exit status 1; no workload case runs without its witness.

Boundary probes preserve the unsupported source forms: mixed-width LENGTH groups,
grouped conditional DO, and sum statements. Runtime probes cover many-to-many
MERGE, character MERGE, unsorted MERGE input, CATX destination overflow, and an
invalid numeric value. They require the expected failed exit, a refused receipt,
and no published result or observed table. Two comparator controls change an
expected value or a character width; both must fail comparison and retain an
observed result for inspection.

The first discovery used one mixed-width LENGTH statement and was refused before
execution. The executable program uses three separate declarations. Its
calculation and independent expected values are unchanged; the original spelling
remains a refusal probe. The runner does not add support for that spelling or
alter the translator. Inspect `report.json`, per-case `case.json`, process logs,
the CLI's own receipts, and retained CSV/JSON outputs for the measured results.

## Character events with short groups

[The second original program](grouped_text/job.sas) sorts fixed-width character
group keys and sequence values, filters excluded rows, truncates a payload to
eight bytes, combines trimmed values with CATX, measures stored/significant
length, and reverses the full padded payload. A final DATA step resets numeric
totals and row counts at group boundaries, then writes detail and closing
snapshots. It uses character SET/BY, not character MERGE. The supported language
profile is unchanged.

[The independent base-R witness](grouped_text/reference.R) pads ASCII fields,
orders rows with an explicit source ordinal for ties, and computes the text and
group results without translator or semantics helpers. The R CSV boundary keeps
all text as text, including literal `NA`, leading/trailing spaces, commas and
double quotes. Only numeric columns interpret the missing-value marker. A
hand-calculated ten-row snapshot pin checks the small case independently of
both engines.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/run_text_workloads.py \
  --output telemetry/workloads/my-text-run --sizes 1000 10000 50000 100000
```

The generated input has one to three rows per group before filtering, stable
tied sort keys, a seeded shuffle, and 228 bytes of declared character storage
per row. Payloads are up to 128 bytes. All text is printable ASCII; numeric
values are bounded integers or ordinary missing. The empty, all-filtered,
blank-value, singleton-group, tied-key and maximum-width cases are explicit.
All four tables, the normalized input and three generated tables, compare
against R through the public CLI and emitted Python. Values, row/column order,
descriptors, padding and table metadata are exact. The CLI and emitted Python
share the runtime; R is the independent behavior witness.

With the four sizes above, the runner executes 11 positive cases, seven refusal
probes and six comparator controls. Refusals cover oversized imported text,
invalid numeric input, BY-key width changes, CATX overflow, unsorted BY input,
non-ASCII REVERSE and grouped conditional DO. They require the expected failed
receipt with no published result or observed table. Comparator controls change
a value, width, row order, padding, schema order or table label; each must reject
the job and retain its observed result. Missing/failed R is a failure, never a
skip. The existing process-group timeout and no-clobber output policy are shared
with the ledger runner.

Per-case R, CLI and emitted processes retain exit codes, elapsed time and peak
RSS where available. Measurements include startup/I/O and are single local
observations without a performance threshold. Comparisons between workloads
must account for their different text widths, output multiplicity and serialized
sizes; equal input row counts do not imply equal work. The runner supports both
the small CI profile and standalone scale tests. Small generator, Python hand-pin
and missing-R regressions also run in the existing operations suite. No new
fixture gate or CI workflow was added.
