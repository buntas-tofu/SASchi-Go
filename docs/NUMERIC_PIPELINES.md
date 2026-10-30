# Bounded rounded numeric DATA pipelines

Status: DS-054..057 repository/base-R policy evidence for principal and maintainer
review. Numerical agreement, exact descriptors, missing masks, row order and
logical records are separate claims. This profile does not establish live-SAS
validation, exact BEST12/DECIMALCONV or physical diagnostic fidelity. No new
complete sibling-program proof is claimed.

## Characterization and marker

The primary [INPUT reference](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n0oaql83drile0n141pdacojq97s.htm)
describes record assignment, record holding and EOF. The unchanged
[inline INPUT contract](INPUT_LIST.md) chooses ordinary numeric list input with
FLOWOVER, record release and incomplete-EOF termination. This slice changes
composition admission, not the input grammar or decimal conversion.

The [SAS array reference](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000203460.htm)
defines declaration-before-reference, indexed aliases and the asterisk list form.
The [DO WHILE reference](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000201927.htm)
distinguishes a test before the body from UNTIL's test after it. These sources
were consulted2026-10-30. Their broader language domains do not define the
implementation's conservative numerical or resource policies.

Design inference: a distinct `numeric_profile` operation named
`binary64-pipeline-v1` admits the four separately gated compositions below.
Require executable power/Pi/trigonometric syntax and at least one actual inline
INPUT, array, DO OVER, WHILE or UNTIL feature. Metadata never supplies a trigger.
The declaration is first at the DATA source line; the existing DATA output
selector can immediately follow it. Old `binary64-v1`, `binary64-rows-v1` and
unmarked evaluators retain their earlier admission, arithmetic and serialized
shapes. No default plan field is added.

## Four evidence lanes

DS-054 composes the unchanged numeric INPUT decoder with rounded scalar state.
One source is the first executable action, after numeric/array declarations and
output selection. It lists1..32 ordinary numeric names; the converter retains
32 token bytes,15 significand digits, exponent magnitude15, exact binary64 and
magnitude2147483647. Physical records retain80 printable ASCII bytes and10000
records. Consumed invalid fields refuse eagerly, including an incomplete final
observation. Inexact decimal input such as0.1 remains refused even though a later
computed0.1 can exist in the rounded expression profile.

DS-055 composes numeric arrays with rounded values, indexed/current aliases and
ordered SUM OF. Existing declaration syntax,1024 total declared references,
overlapping named PDV bindings, one active implicit DO OVER alias, internal _I_
state and the earlier body/nesting restrictions remain. Ordinary writes and
array writes see the same row variables. Members reset as scratch unless an
existing input read supplies them. Explicit RETAIN/sum-target array elements
remain deferred.

Array SUM OF validates every member, ignores ordinary missing and returns missing
if all members are missing. It adds nonmissing values one at a time in declaration
order using the bounded rounded profile. It is not a vectorized compensated sum.
For example, the declared sequence1e9,0.1,-1e9 produces approximately
0.10000002384185791. A retained sum statement over an all-missing SUM OF leaves
its zero-initialized accumulator at zero instead of making SUM OF itself zero.

DS-056 composes rounded scalar and existing indexed bodies with single-level
WHILE and UNTIL. WHILE permits zero trips when its first test is false or missing.
UNTIL executes once before its first test. Both keep10000 body executions per
invocation; a10001st required execution refuses. Counted loops keep their existing
8-level nesting and10000-trip per-observation shared budget. New nesting among
WHILE, UNTIL, DO OVER and counted loops is not admitted.

DS-057 proves an original complete stream crossing numeric INPUT, a fixed array,
rounded reciprocals, ordered SUM OF, both conditional loops, independent retained
and imported sum targets, projection, earlier snapshots and a fresh second step.
One source per step is inline INPUT or the selected numeric SET contract inherited
from [NUMERIC_ROWS.md](NUMERIC_ROWS.md). A separate supplied-SET/array hand pin
proves that origin and eager numeric validation; metadata and output DROP are
preserved. Lookup/BY/WHERE/MERGE remain outside the profile.

## Exact controls and unchanged value/text limits

Numeric values, reached arithmetic, function domains and inferred logical text
retain [BINARY64.md](BINARY64.md). No SQRT, LOG, stochastic functions, wider trig
arguments, scientific text or formatting mode is introduced. Subnormal, tagged,
boolean, character-coerced, nonfinite, overflowing and nonzero-underflow cases
retain their refusals. INT retains its conservative near-integer refusal.

Subscripts remain on the earlier exact array-expression evaluator and must yield
an integral in-bounds index. Counted controls keep the earlier exact integer
parser/evaluator. Rounded value arithmetic cannot make an invalid control appear
valid. The full numeric expression plus an embedded exact subscript shares one
32-level depth bound. Arithmetic/call and array-expression budgets each remain128;
structural container/cycle guards remain in force.

All declarations, literal domains, static index errors and descriptor types
validate on empty, skipped and zero-trip paths. Dynamic indices and values remain
lazy when their statements are skipped. Descriptor discovery and explicit OUTPUT
suppression inspect all statically present bodies. Snapshots read the complete
PDV; output selection preserves descriptor order without removing calculation or
retained state. Failure publishes neither an accepted result nor buffered stdout.
Caller catalogs, portable plans and internal alias offsets remain separate.

## Independent evidence

Each of the four gates has120 generated full-source/runtime/base-R cases.
The separate lanes have2 inline hand pins,3 array hand pins,8 conditional-loop
hand pins and2 complete-composition hand pins. Shared refusals cover conversion,
static/dynamic bounds, masked arithmetic, infinite-loop budgets and eager selected
SET values. Nine competing interpretations are checked with structural/numeric
comparators. Eight dataset damages also fail actual CLI --expect jobs, preserving failed receipts and observed artifacts. Logical-log damage remains on its separate exact comparison because --expect compares datasets only. Emitted Python and actual CLI results are compared independently.
The33-test suite includes both discovered guard regressions: combined outer/index
depth and an indexed write hidden inside a DO OVER IF descendant.

The independent R interpreter consumes every executable statement without reading
a Python plan. It implements its own record cursor, named alias state, ordered
aggregation, loop tests, snapshots and row reset. Numeric comparisons retain the
32-epsilon normalized budget; missing values, schemas, row order and logical
strings compare exactly. Python and R may share host transcendental libraries.
The R text witness uses its inherited independent fixed-decimal stability check.

`examples/numeric_pipeline_capture.sas` contains32 executable/declarative
statements across two DATA steps. Three complete measurement reads produce six
pipeline snapshots. WHILE executes nine bodies and UNTIL six. A fresh array step
produces one further observation. The stream includes an all-missing array sum,
a missing imported sum target, retained accumulation and missing fields in early
snapshots. Appended procedure and truncated-program controls refuse rather than
accepting a partial source proof. Corpus source remains unchanged.

Optional gmpy2/MPFR and Hypothesis experiments are lab evidence only. Neither is
a runtime dependency or a requirement for these gates. Synthesis, workloads and
complete external programs retain their separate units and acceptance records.

The original source SHA-256 is f69124cbbc6aecd2738fdb84ddd96d8bdc67c8f264a5e5e8cf314b5cc84f61fa.
The order-preserving hand-result pin is2e8308bd71e578c1061505cb8d4829c7afc4d23dbc2b816bac7a22fba691ce67;
the emitted logical-stdout pin is2daff53a82fab95e1a7ab39626f24e95718a3720b92353e90865f3a1f50e91fb.
Source and pins are checked by the composition gate.

The D1 source-boundary promotion event preserves the exact earlier C1/C2
ARRAY/WHILE frontier cases and ARRAY/WHILE/UNTIL suite clauses. New-marker
source/R acceptance and forced-old-marker refusal are both required; existing
old-profile R still refuses. See [NUMERIC_ROWS.md](NUMERIC_ROWS.md) for the
unchanged7/21 boundary-control totals and their5/19 shared-source plus2 old-marker
split. No earlier control was deleted, skipped or reordered.
