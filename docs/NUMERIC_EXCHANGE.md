# Bounded numeric lists and atomic CSV artifacts

Status: DS-062/063 repository/base-R evidence for principal and maintainer review.
This profile defines exact numeric-list state and a named ASCII/LF artifact
policy. It does not establish live SAS, physical FILE/default-format behavior,
general CSV or arbitrary host I/O. Unified acceptance is source-bound in receipts.

## Characterization and the named byte policy

The [SAS FILE reference](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000171874.htm)
identifies FILE as executable routing for subsequent PUT output. FILE DLM chooses
the first delimiter character for list output; this differs from INFILE delimiter
sets. [PUT List](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/p0jcwhe1ofmb49n1xf1q2kc44b0v.htm)
and [sample24596](https://support.sas.com/kb/24/596.html) distinguish list fields,
missing periods and delimiter selection. Primary sources consulted2026-10-31.
DSD quoting, pointer/holding controls, external reads, formats and wider default
numeric typography remain outside this contract.

Design inference: `ascii-lf-integer-csv-v1` uses printable ASCII records, one comma
between numeric fields, no trailing comma or space, and LF after every written
record. An empty artifact has zero bytes. Literal-only headers preserve the
existing quoted-literal policy, including commas as literal text. Numeric fields
retain the existing whole-number rendering subset and ordinary missing period;
fractions are not silently formatted. Each output record is at most64 bytes.
The no-FILE numeric-list path retains its existing following blank per field.

The consulted primary references do not settle exact physical open timing when
INPUT reaches EOF. Explicit repository policy, separately recorded by the pair's
immutable export-byte decision: a top-level FILE executes before each INPUT
attempt and opens an empty private buffer before the first attempt. Empty,
FIRSTOBS-skipped and incomplete valid input therefore produce an empty named
artifact. A header guarded after INPUT never executes without a complete read.
The same FILE on later iterations and terminal EOF does not truncate prior bytes.
This policy is not relabeled as physical SAS-platform equivalence.

## Source and portable admission

The separate version2 `exchange_data` step starts with `exchange_profile` at the
DATA line, with name `bounded-numeric-exchange-v1`. Actual FILE or numbered ranges
in SUM OF/PUT select it. Old `data`, numeric_profile, control_data and input_numeric
plans retain their shapes and refusals; a marker alone is insufficient.

One optional numeric inline INPUT reuses the earlier space/comma decoder,
FIRSTOBS1..10001, FLOWOVER, unread-suffix release, incomplete-EOF termination,
32 names,80 printable-ASCII bytes per physical record,10000 physical records and
exact decimal conversion. All raw records, including skipped headers, validate
before conversion. Consumed invalid fields refuse even in an incomplete final
observation. Ignored headers and discarded suffixes are not code or converted
values. DSD, quoted/general CSV and external input remain refused.

New lists expand1..64 canonical ordinary names or ascending common-prefix
numbered suffixes1..64, without padding. The complete final run of digits is the
suffix. Expansion precedes duplicate, overlap and size checks. INPUT keeps its
separate32-name cap. List names must already have ordinary numeric descriptors;
a numbered list is not an array object and creates no indexed alias state.

`SUM(OF x1-x3)` is admitted only as the complete unparenthesized ordinary
assignment value. It ignores ordinary missing, returns missing when all members
are missing, and checks each ordered exact partial sum with unchanged helpers.
Nested/predicate SUM and retained sum-statement SUM remain separate frontiers.
Scalar arithmetic, retained totals, simple IF/ELSE, top-level subset IF,
projection and OUTPUT retain the profile's explicitly checked numeric state.
Scalar references require preceding descriptors, apart from their own assignment
target. Scratch variables reset per observation; imported retained targets are
overwritten by the read. Explicit OUTPUT anywhere suppresses implicit output.

FILE is one unconditional top-level prefix before INPUT and other executable
actions. Its sole form is a quoted literal basename with comma DLM. Basenames
preserve ASCII case, contain at most64 characters, begin with a letter or
underscore, and otherwise contain letters/digits/underscores/hyphens plus the
final `.csv` extension. Compare names case-sensitively. Directory components,
traversal, alternate streams, device stems, filerefs, append and extra options
refuse. The fixed CLI `exports` directory and standard JSON filenames cannot
collide with this grammar. Initially only one export destination is admitted in
the entire program; earlier/later legacy steps remain possible.

Portable validation consumes exact fields and checks marker, source lines,
source order, term expansion, descriptors and static domains on empty/dead paths.
Bounds are64 PDV columns,1024 operations,128 expression/list nodes,32 expression
and branch levels,10000 output observations or emitted records, and1000000 step
events. Arithmetic retains the existing exact bounded binary64 helpers and
magnitude2147483647. Arrays, loops, SET/BY/WHERE/MERGE, character variables,
rounded profiles, new functions and numeric domains are not added.

## Pure execution, comparison and publication

`run_plan` and emitted Python perform no source-directed host writes. Programs
with FILE additionally return `exports`, a complete basename-to-text map. Empty
opened buffers remain present as empty strings. No-FILE programs keep the old
`datasets`/`log` result shape. Emitted code prints only logical log records.
Caller catalogs and plans remain unmodified; inherited full catalog normalization
also applies to unused supplied tables before this profile executes.

`build_job` retains its first four positional arguments. `expect_exports` is a
new keyword-only argument. CLI `run --expect-exports expected.json` reads one
complete basename-to-text map. Duplicate/unknown-shaped JSON, invalid names and
nontext values refuse safely. Comparison checks the exact name set and UTF-8
bytes, including order, missing values, record count and final newline. It does
not accept a subset. Dataset `--expect` keeps its earlier contract.

Only new FILE jobs or an explicit export expectation add `export_comparison` and
its `exact-basename-set-utf8-bytes-v1` contract. FILE jobs declare the byte policy;
observed buffer manifests record SHA256, bytes and record counts. Legacy receipt
keys and result JSON serialization remain unchanged without the new feature.

Only accepted CLI success writes physical files at `<new-job>/exports/<basename>`.
Plan, result, receipt and export files remain in the existing private staging
directory until one rename publishes the complete job. Runtime or later-step
failure publishes no accepted result, export files or buffered stdout. Comparison
failure may publish the existing `observed.json` diagnostic, but no exports
directory. Physical open/partial-write/commit failures clean staging and publish
no job directory. Existing output destinations are protected. The API/web/TUI/
showcase may expose pure buffers; this slice adds no separate UI export feature.

## Independent evidence and complete programs

The range gate has6 hand cases,160 generated complete-source/runtime/R cases,
13 shared refusals and4 actual CLI failed dataset comparisons. The export gate
has9 hand cases,160 generated cases,31 shared refusals and6 actual CLI failed
artifact comparisons. Wrong names, bytes, row order/count and final newline are
separate controls. A source suite covers malformed plans, static/empty/dead
paths, exact resource boundaries, old-profile refusal, caller privacy and real
CLI publication faults.

The independent base-R interpreter consumes complete source and opaque records.
It reuses the earlier independent R scanner/decimal decoder, then implements its
own64-name expansion, dyadic bit arithmetic, state, file routing and EOF attempts.
It never receives Python plans, rows or rendered expectations. R cases advertise
an empty supplied catalog only. Generic unused-catalog normalization is separately
tested in Python/emitted execution, with no generic R transport claim.

The first-party `examples/numeric_exchange_capture.sas` has25 language statements
and one opaque data event across three steps. Three complete INPUT observations
produce six early/late snapshots in its first step; the next step adds one row.
Four FILE/INPUT attempts include terminal EOF, and four CSV records include the
header. The first two exchange steps have41 and5 scheduled operations; the final
legacy literal step has one R event. The ordinary log has two exact records.
Source, ordered result and stdout pins are enforced by the gate.

The entire unchanged sibling `csv_data_manipulation.sas` has9 language statements
and one opaque data event. Four complete INPUT observations, five attempts/FILE
executions including EOF, five written records and23 scheduled operations are
independently hand-pinned against both R and Python traces. READS means complete
INPUT observations, not physical records; FLOWOVER may span multiple records.
The exact82-byte `output.csv` has header `C1,C2,C3,C4,C5,Sum` and sums45,50,55,60.
Its SHA256 is26ab6a12a8aeaa2f4e5500c2c40f3e0a81334f530a86f5dcc1af852c036f2fcb.
The gate binds the unchanged source hash and compares independent R, runtime,
emitted pure buffers and actual CLI files. No sibling source is copied or edited.

Only FILE Statement is promoted from UNASSESSED to its bounded source-execution
subset. Seven already-GATED input/output entries gain additive evidence; all148
reference identities, universes, previous histories and gate evidence remain.
Function and format reference universes remain unenumerated. This proof is a
whole-source artifact contract, not a general CSV or physical SAS claim.
