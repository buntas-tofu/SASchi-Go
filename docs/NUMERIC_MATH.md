# Bounded numeric mathematics

Status: DS-066..068 repository/base-R evidence for maintainer review. This is a
separate finite numeric source profile, not live-SAS validation or physical SAS
log equivalence. Optional independent MPFR labs are review evidence, not runtime
or CI dependencies. The original measurement workflow adds no complete external
corpus proof.

`binary64-math-v1` is a first `numeric_profile` operation on an ordinary version2
DATA step. It adds no Step fields, result channels or receipt fields. Actual
SQRT/LOG calls select it; scalar argument SUM selects it only with an existing
rounded trigger in the same executable DATA step. Plain `sum(1,2)` keeps its old
call plan. Function-shaped literals, comments, opaque records and names do not
select a profile. Metadata cannot supply the semantic trigger. Global function,
array and binary64 registries remain unchanged, including legal arrays named
`sqrt` and `log`. A function call colliding with a declared array name refuses.

## Values and domains

[SAS SQRT](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000245950.htm)
requires a nonnegative argument;
[SAS LOG](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p0urbseuxrkrlyn1tr04y30nt25s.htm)
is the natural logarithm and requires a positive argument. This profile accepts
ordinary missing, normal finite binary64 and zero under the prior absolute
2147483647 operand/result limit. SQRT admits zero; LOG refuses zero and negatives.
Ordinary missing propagates. Boolean, tagged, character, nonfinite and subnormal
operands remain refused. Nonzero arithmetic underflow remains refused before a
function can hide it. Arguments evaluate with existing rounded arithmetic first.

The repository deliberately refuses invalid domains. Native SAS can instead
[return missing and a diagnostic](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p07c8e0ktns1c7n1vtowjev5g724.htm).
Static literal errors refuse on empty, skipped and zero-trip paths. Dynamic errors
refuse when reached; a skipped dynamic call stays lazy. No SAS diagnostic state is
simulated. LOG near1 can yield a valid dataset value while the unchanged numeric
PUT policy refuses its tiny textual value.

[SAS SUM](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000245953.htm)
ignores missing arguments. This scalar composition accepts1..1024 arguments,
validates every argument eagerly, and returns ordinary missing when all arguments
are missing. It adds nonmissing values left to right, checking every rounded
partial against the existing numeric bounds. `sum(1000000000,.1,-1000000000)` is
0.10000002384185791. Vectorized summation, reassociation and cancellation that
rescues an overflowing partial are excluded. Existing array SUM OF and semantic
reference helpers are unchanged.

## Composition and limits

The profile reuses [numeric pipelines](NUMERIC_PIPELINES.md): one exact inline
space INPUT or selected numeric SET source, fixed arrays and active aliases,
existing counted/WHILE/UNTIL nesting, retained sums, full-PDV snapshots and output
projection. Selected SET descriptors and every selected value validate eagerly,
even when output drops them. Prior source metadata/order and caller nonmutation
remain. Ordinary INPUT conversion stays exact; this slice does not admit decimal
0.1 as an input token.

Array indices and counted controls remain on their earlier exact evaluators and
do not gain SQRT/LOG or rounded argument SUM. Expressions retain32 levels and128
arithmetic/call nodes, operations1024, earlier array/reference/column limits,
converter limits, counted/conditional trip budgets and output/event limits.
Logical numeric rendering remains the prior conservative fixed-decimal policy.
Failure publishes no accepted result or buffered stdout.

Comma/range INPUT, FILE exports, scalar-flow jumps, new functions, wider trig
arguments, RNG, macros, character values, formats and C++ remain outside this
profile. All older marker and unmarked portable-call refusals remain explicit.

## Evidence

Three appended gates separately cover SQRT, LOG and rounded argument SUM. Each
runs120 deterministic complete-source cases against the independent base-R
interpreter, with4/4/5 hand pins and10/10/9 shared refusals. Decimal90 targets use
6 SQRT and7 LOG binary64 inputs, including the minimum normal and neighboring
values around1. Python/R comparison permits32 normalized epsilon units; missing
masks, schema/row order and logical text compare exactly.

The complete original [measurement source](../examples/numeric_math_capture.sas)
has29 language statements, three input observations and a fresh second DATA step.
It combines0,3 and missing input with SQRT, LOG, scalar and array SUM, aliasing,
retention, both conditional loops, projection and six ordered snapshots. The R
accounting pins6 loop trips and a separate fresh-step iteration. Its source hash,
hand values and exact logical records are frozen in the gate. It is not a new
external corpus claim.

The unary gates each reject two actual CLI dataset damages. The composition
gate rejects eight damaged dataset expectations, including rounded
SUM order, missing, snapshots, retained reset, fresh-step reset and descriptor
order. A separate exact-text control rejects a lost trailing blank. Two actual
CLI failures cover static empty-input and late dynamic errors with no accepted
result or observed partial. Emitted Python returns the same data and exact stdout.
The27-test source suite covers portable markers, cycles, resource/domain/state
boundaries and the previously accepted20001-operation legacy plan.

Four literal older source frontiers are preserved with new hand/R positives,
old independent R refusal and forced old-marker/unmarked runtime negatives. The
older array-pipeline gate reports eight shared refusals plus one older-profile
control, retaining its original nine boundary units. Broader old refusals remain.
