# Workload testing

Status: exploratory repository/base-R evidence for maintainer review. No live
SAS observation or production throughput claim. The existing fixture gates and
their acceptance policies are unchanged. Run receipts, including failed attempts,
are written to ignored telemetry directories.

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
Timings include startup and file I/O; they are single observations without a
performance threshold. Row counts are bounded to 100000 and processes have an
explicit timeout.

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
