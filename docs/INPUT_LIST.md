# Bounded numeric inline INPUT

Status: DS-044 repository/base-R evidence for principal/maintainer review.
The profile proves bounded values, DATA observations and logical output records.
Live-SAS validation, diagnostic recovery and physical SAS log fidelity remain
outstanding. Wider syntax or values require separate evidence.

## Characterization and representation

The primary [SAS INPUT reference](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n0oaql83drile0n141pdacojq97s.htm)
defines INPUT as executable, assigns fields to variables and distinguishes line
holding with `@` or `@@`. A read without those controls releases the record.
Attempting to read past EOF stops DATA execution. Invalid numeric input normally
involves missing values and error-state diagnostics; this profile refuses that
case instead of claiming to emulate the recovery.

[SAS list-input concepts](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a003209907.htm)
describe ordered fields separated by blanks. Repeated blanks are delimiters;
ordinary numeric missing needs a period. Modified input and informats are
separate forms. The [INFILE reference](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n1rill4udj0tfun1fvce3j401plo.htm)
establishes FLOWOVER as the default: a short record continues at the next record
until the INPUT is satisfied. MISSOVER and TRUNCOVER change that behavior and are
not silently substituted here. SAS can issue notes for record flow; this tool's
logical log contains supported PUT records only.

The [DATALINES reference](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/p0114gachtut3nn1and4ap8ke9nf.htm)
identifies CARDS as an alias, requires one final inline block per DATA step and
uses a null semicolon statement to terminate it. CARDIMAGE processes80-byte
records; NOCARDIMAGE allows longer lines. The separate DATALINES4 family admits
embedded semicolons. Sources consulted2026-10-29.

Design inference: retain physical records in one version2 `input_list` operation
with `names`, `records` and `data_line`. Decode complete observations before row
execution, then use the existing PDV, retained state and OUTPUT machinery.
Requiring INPUT first makes incomplete-EOF termination observable without needing
to emulate work performed before a failing read. Older plans acquire no new
default fields. Raw data bypasses code, string, comment and macro interpretation.

## Accepted profile

One top-level numeric INPUT is the first executable statement, following optional
declarations. It lists1..32 unique ordinary variable names. One bare CARDS or
DATALINES block follows the scalar program, with data starting on the next line.
The terminator ends the step; RUN may follow. Input names declare numeric columns
in source order and overwrite their retained values on every complete read.

At most10000 physical records,80 printable ASCII bytes per record, spaces as
delimiters, and no embedded semicolon. Blank records supply no fields. Once all
variables are assigned, unused fields on that last record are discarded, without
numeric conversion. An incomplete final observation is discarded. For example,
two variables reading `1`, then `2 99`, then `3 4`, then `5` produce exactly
`(1,2)` and `(3,4)`. The99 and incomplete5 do not become observations.

Numeric tokens accept ordinary missing `.`, signed decimal spellings and E
exponents. Limits are32 token bytes,15 significand digits, exponent magnitude15,
exact binary64 representation and magnitude at most2147483647. Zero is normalized.
Examples1.25, -2.5 and5e-1 pass;0.1 requires rounding and refuses. These bounds are
implementation policy, not SAS language limits. Python checks exact rational
conversion; independent R factors powers of five out of decimal denominators.

Scalar assignments, numeric RETAIN and sum statements, simple IF/ELSE, subset IF,
LAG occurrence queues and existing numeric/literal PUT and OUTPUT keep their
contracts. Scratch values reset on each complete read; `_N_` counts those reads.
Explicit OUTPUT snapshots current values and suppresses implicit output even
when skipped. Empty input retains a fully discovered schema. Source and forged
plans validate independently. Static types and shapes check even on skipped or
empty paths. Consumed invalid tokens refuse eagerly, including before incomplete
EOF. Late execution failures publish no accepted result or buffered stdout.
No input cursor, buffer or synthetic iteration variable becomes a column.

Character, named, formatted and modified INPUT; variable lists; arrays and loops
in the inline step; SET/MERGE/BY/WHERE; INFILE and external files; pointer and line
controls; `@`/`@@`; LINES and the *4 aliases; special missing tags; inexact decimals;
tabs, non-ASCII and control bytes; PUT _ALL_; and C++ remain refused. Unrelated
scalar and supplied-catalog steps retain their earlier behavior.

## Evidence

The appended gate checks12 hand pins,600 constructive source/runtime/R cases,
24 shared refusals and4 wrong-interpretation controls. The31-test suite adds
record and row limits, static/empty/skipped schema, state reset, snapshots,
malformed plans, atomic failure, comparator controls and actual CLI execution.
An installed wheel exercises inline input without site packages or new runtime
dependencies. The original `examples/input_capture.sas` has13 statements, three
complete reads and five snapshots. Hand accounting and an independent R parser
agree on every schema, row and log record.

The entire unchanged sibling `integer_comparison.sas` has18 executable/declarative
statements and three complete reads. Each row tests13 comparison spellings. The
less-than and greater-than rows each emit eight records; equality emits seven,
for23 logical records and no datasets. The hand truth table, independent R
whole-source interpreter, source/runtime, emitted Python and CLI all agree. This
is the thirteenth complete external-program proof. Corpus source is read from
the sibling repository and is not copied into this tree.

| Program | Pin | SHA-256 |
| --- | --- | --- |
|integer_comparison.sas|source|bfe81fc2f69fbf081a4687c63ff1732f8cc3e2e4a495330dc9583a20ccab2497|
|integer_comparison.sas|complete result|cdde22b438ef225e6c0113b14f6d9eba102e183968b1068d4bfa7cd32bf9691f|
|integer_comparison.sas|stdout|9de674d4d85a9a8f3ff66e3f93269d2e37df804d85a15b4c186a53c887e18c3a|
|input_capture.sas|source|86eca29a62b7672013c29d31d5ed3f664561bc3538100048d4100dcaa618edaf|
|input_capture.sas|complete result|df9454f43db2e0546118993f66d9843610b1242a3b00ffe33a8ec12b263774ba|
|input_capture.sas|stdout|66b5baec970c71d09eda39dbd16da8501f5b173278c03d76b573ada7bdf69d31|

Result pins use sorted compact JSON; stdout includes every newline. Dataset
comparators do not compare logs, so exact result/stdout pins and log-order and
multiplicity controls supply that separate evidence. All previous registrations
remain in order. Exact commits, receipts, workload compatibility and ownership
are recorded in ignored `telemetry/SESSION_HANDOFF.md`.
