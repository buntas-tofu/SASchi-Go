# Operating the bounded workflow

Status: executable repository contract and fixture evidence. No live SAS
comparison is claimed. The maintainer may use this workflow for development
and review; production acceptance requires workload-specific evidence.

## Install and check

The tested verification profile is CPython 3.12 on Linux, base R, and a C++17
compiler. Install base R and g++ using the machine's package manager. Python
runtime support starts at 3.11; the exact lock snapshot is tested on 3.12.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-verify.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/saschi doctor
.venv/bin/python verify_all.py
```

`doctor` describes missing verification dependencies. It does not install them.
`ROSETTA_RSCRIPT` selects an R executable. `CXX` selects a C++ executable, not
a shell command with flags. Verification receipts record executable paths and
versions. They are checksummed, not cryptographically signed.

## Inspect, translate, and run

```sh
saschi inspect examples/workflow/job.sas
saschi translate examples/workflow/job.sas --target python --output output/job.py
saschi run examples/workflow/job.sas --inputs examples/workflow/inputs.json --expect examples/workflow/expected.json --output telemetry/my-first-job
```

Use a new output path for every run. A completed job directory contains its
plan, receipt, and result. A failed comparison writes `observed.json` for review
instead of `result.json`. Unsupported source produces tickets and a failed
receipt without executing the plan. Exit codes are 0 for success, 1 for an
execution/comparison/environment error, and 2 for unsupported translation.

The example rounds numeric amounts, sorts two datasets, and performs a
one-to-many match merge. Its output is pinned and compared with base R in the
unified gates. The external catalog explicitly declares each column as
`number`. Values are JSON numbers or null; the runtime converts numbers to
binary64. Dataset and column lookup is case-insensitive. Result keys and PUT
labels are normalized to lowercase. PUT uses 17 significant digits, not SAS
format typography. Inputs are copied; execution does not modify the caller's
catalog. Empty outputs retain a schema.

The supported source subset includes the numeric workflow above and the
[version 2 stateful contract](STATEFUL_EXECUTION.md): one DATA destination,
explicit OUTPUT snapshots, simple WHERE/IF predicates, retained numeric state,
initial lookup SET, character byte widths, and typed metadata. That document
specifies syntax, catalog descriptors, comparisons, and remaining review cases.
Unsupported source still produces tickets; data-dependent incompatibilities
produce a failed execution receipt. Inline data is preserved but not executed.
Partial API execution remains inspection-only and is not exposed by the CLI.

## Shared plan and additional backends

Plan version 2 stores typed expressions, declarations, read/output events, source
lines, retained state, input dependencies, BY keys, and review tickets. Version 1
serialized plans remain readable. Python
executes the plan. The C++17 pilot emits scalar DATA _NULL_ programs from the same
plan and rejects dataset operations. It uses the same binary64 rounding contract.
The compiled pilot gate compares fixed pins and 40 seeded rounding cases with
Python. This is a bounded backend pilot, not a general C++ SAS translator.

```sh
saschi translate my-scalar-job.sas --target cpp --output output/job.cpp
g++ -std=c++17 -O2 -ffp-contract=off output/job.cpp -o output/job
output/job
```

Run `python tools/benchmark_backends.py` for a local pilot measurement with 128
rounding cases and five fresh processes per target. It checks output parity and
records compilation separately from process startup/execution and peak RSS.
The measurement is not a production throughput comparison.

Julia remains a future backend option. Adding a language must preserve the plan's
contracts and add execution evidence. Algorithm replacements can consume these
operations, but no statistical method change is silently treated as equivalence.
The next stateful algorithm candidate is conditional LAG: retain a queue per call
site and advance it only on invocation. The existing DS-007 target tests pin that
behavior; the source compiler still sends LAG to review.

## Evidence and reproducibility

The unified command retains all original fixture gates in their original order,
runs the translator and operations suites, then runs six synthesized families
with ten deterministic seeds each. Synthesis uses a 17-digit CSV transport with
base R, pandas, and the semantics reference. It requires all 60 cases to execute
and agree under the explicit typed policy in the stateful contract. Its drafts are generated directly, so synthesis is separate evidence
from source translation. Missing runtimes, timeouts, missing output, incomplete
case counts, and numerical divergence fail the gate.

Verification receipts include the full Git commit, dirty state, per-file source
hashes, runtime versions, full subprocess output, corpus file hashes, and a source
stability check. Corpus tests remain optional when the sibling corpus is absent;
the receipt explicitly records presence and unittest output contains skips. CI
checks out the pinned corpus revision to exercise those tests. ALL VERIFIED
means the registered gates passed for the recorded source and environment; it
never means arbitrary SAS programs are equivalent.

## Repository peers

The development host is wutai. At the start of this change, cloud and fahrenheit
both held baseline commit 3a678ef4b50b09bf59c452de5a347ee044bab5cf.

- cloud: SSH alias `cloud`, working checkout at
  `/home/the-pgh-cid/besaid/bunta/saschi-go`.
- fahrenheit: configured remote at
  `the_pgh_cid@fahrenheit.tail1571d6.ts.net:/spira/repos/saschi-go.git`.

Sync a named development branch after the gates pass. A push to cloud must not
replace its checked-out branch. Compare full branch commit IDs on each peer.
Machine paths are configuration, not assumptions inside the execution plan.
Runtime validation performed on one host does not establish runtime parity on
another. Each execution receipt identifies the host that actually ran it.
