# Coverage reconciliation and next gate series

Status: Repository/base-R planning evidence, originally reconciled at main08eaa7b
on2026-10-27 and updated through DS-047 through DS-051 and A0. The handoff binds current acceptance.
For principal/maintainer prioritization. Counts describe this checkout and the56
pinned sibling corpus files, not all SAS or live-SAS equivalence. Updated for
DS-039 arrays, DS-040 DO OVER and DS-041 nested/computed counted loops after the original
reconciliation. Rankings,
diagnostic categories and projected unlocks are explicitly analyst inferences.
Implementation and publication are not authorized by this planning exercise.

## Inventory reconciled against actual evidence

The golden command registers56 fixture runners,46 translator suites and1
synthesis runner. The current acceptance contains922 tests, zero skips,
60 faithful synthesis checks and60 naive controls. The separate1k workload
checks total39:18 ledger and21 text. These counts have different units. Neither
86 rulebook rules nor103 golden-command runners is a SAS capability denominator.

[The capability manifest](capability-manifest.json) still enumerates108 statements
and40 data-set options. The other7 declared reference areas remain unenumerated:
formats/informats, functions/CALL routines, system options, component objects,
utilities, macros and procedures. Their null universes are not zero.

The reconciled148 entries contain31 GATED,5 RULE,8 HUMAN-REVIEW,22 OUT-OF-SCOPE
and82 UNASSESSED. Among GATED entries,30 have bounded source-execution evidence;
1 has reference fixtures only: IN=. DS-039/DS-040 add bounded source-array evidence; DS-041 adds scoped counted-loop
evidence to the existing iterative-DO entry. DS-044 promotes four bounded entries:
INPUT, INPUT List, CARDS and DATALINES, preserving their prior assessments.
DS-046 extends bounded source evidence on the already-GATED PUT and PUT List entries;
no reference universe or disposition count changes in that slice. DS-047/048 promote KEEP/DROP statements and KEEP=/DROP= options, preserving prior dispositions and separate input/output timing evidence. DS-049/050/051 add bounded numerical and inferred logical-text policies without enumerating any function or format universe. Reference universes remain unchanged. The original reconciliation below
remains its historical assessment event. These are
catalogue-entry counts, not counts of implemented features or supported forms.

| Entry | Previous | Reconciled | Evidence and remaining boundary |
| --- | --- | --- | --- |
| SET | RULE | GATED | data-events, typed-metadata and suite-events execute supplied-input SET and bounded initial lookup; general options/concatenation remain refused |
| RUN | UNASSESSED | GATED | data-events and suite-plan exercise the bare step terminator; interactive variants are not claimed |
| ATTRIB | GATED | UNASSESSED | typed-metadata transports descriptors; ATTRIB source is refused |
| LABEL | GATED | UNASSESSED | typed-metadata transports labels; LABEL source is refused |
| Plain DO | GATED | UNASSESSED | arrays proves helpers; grouped DO source is refused |
| LABEL= data-set option | GATED | UNASSESSED | data-set labels survive transport; LABEL= source option is refused |

The previous assessments and cited gates remain in manifest assessment history
and related evidence. Every surviving GATED entry now declares its evidence
level, registered gates and bounded scope. Existing array reference evidence is
preserved without implying indexed-array source execution. BY, MERGE and RETAIN
now also cite their existing source suites. No capability was implemented or
removed. The manifest gate additionally rejects missing scopes/levels, mismatched
evidence, duplicate entries and stale rollups. It still checks every previous
registration, rule and universe requirement.

All82 unassessed entries receive planning bins in the reproducible inventory:
29 external-environment review,13 separate-scope review,8 input records,
10 data-set options,9 control,7 output,5 descriptor/environment and1 projection.
These bins organize work; they do not promote dispositions or decide exclusions.
The5 RULE entries and8 HUMAN-REVIEW entries retain their review boundaries.

## Unknown blockers classified

The current56-file compile census has19 clean and37 blocked, with648 ticket
occurrences. A2 resolves20 compiler tickets across the corpus. The newly compile-
clean100_doors.sas now passes the DS-042 mixed-output whole-program proof.
B1 resolves two further tickets and adds the complete loops_for.sas proof.
B2 adds the integer_comparison.sas proof. Total tickets fall by9;50 formerly
unknown occurrences now resolve or receive explicit input-profile routing.
B3 removes18 further compiler tickets and one unknown occurrence.
B4/B5 remove37 further compiler tickets and10 unknown occurrences.
The remaining422 occurrences routed
as unknown receive a primary planning category, with file, line, ticket ordinal,
statement hash and classification basis preserved. Classification preserves every
current compiler ticket.

| Primary category for unknown tickets | Occurrences |
| --- | ---: |
| Procedure backend/clauses |228|
| Macro body, invocation or unresolved reference |129|
| Input records, INPUT/INFILE and opaque inline data |3|
| Labels, GOTO/LINK/RETURN/STOP |35|
| Arrays and indexed writes |15|
| External file/engine output |4|
| Descriptor/environment statements |4|
| Corpus prose or printed output |2|
| CALL side effects |2|
| Total |422|

The procedure subtotal includes DS2:95, OPTMODEL:76, IML:31, PRINT:9, MEANS:4,
FCMP:3, SQL:3, SGPLOT:2, TTEST:2 and one each SORT, MULTTEST and UNIVARIATE.
These are diagnostic occurrences under lexical ownership, including cascading
clauses, not independent missing procedures or implementation estimates. Macro
classification likewise groups body fallout under a macro contract. Several
capabilities can be present inside the same grouped category.

Two corpus files mix explanatory prose or printed results with code:
palindrome_detection.sas and strip_a_set_of_characters_from_a_string.sas.
There are4 quality-related tickets across all routes, including2 unknown and2
unterminated tickets. They need an explicit source-boundary decision; silently
discarding those sections would invalidate a complete unmodified-file claim.
No sibling corpus file was changed or copied into this repository.

Eighteen files now have complete-program repository/base-R proofs. B5 adds the unchanged sum_of_a_series.sas and trigonometric_functions.sas under explicit numerical tolerances and an inferred logical decimal text policy. These two proofs do not establish exact SAS BEST12/DECIMALCONV or physical-log equivalence. B3 adds the entire unchanged
sum_and_product_of_an_array.sas, retaining its unassigned c as missing. A0 separately
closes existing hello_world_text.sas and explicit comment-only no-op evidence,
without language expansion. DS-042, DS-043 and DS-044 retain the complete
100_doors.sas, loops_for.sas and integer_comparison.sas proofs. The one other
compile-clean file is bitwise_operations.sas, whose67-column output still refuses
under the unchanged64-column PUT_ALL profile. The original
reconciliation itself did not increase the proof count. Compile tickets also miss
runtime limitations:
earlier numeric-list PUT remains bounded integer output and earlier division requires exact representability. The new syntax explicitly selects the separately bounded binary64/text policy in docs/BINARY64.md; INT retains its conservative near-integer refusal band.

## Prioritized finite backlog

Inference: prioritize a coherent DATA-step composition series that reuses the
existing array reference witnesses and aims at two whole-file targets. Frequency
alone would prioritize priority_queue.sas, whose205 tickets span macros and DS2;
that is a much broader semantic and runtime contract. This is a qualitative
evidence-cost ranking, not a schedule or an estimate of business demand.

| Order | Slice | Dependencies | Target and projected result | Evidence cost |
| --- | --- | --- | --- | --- |
| A0, completed evidence closeout | Hello-world and comment-only whole-file witnesses | Existing behavior | Both complete unchanged sources now have explicit whole-file proofs, no language expansion | Low |
| A1, implemented in DS-039/DS-040 | Numeric array declarations, indexed access/assignment, OF aggregation and DO OVER alias iteration | Existing DS-016 helper witnesses | loops_foreach.sas is now the first accepted full-file target | High: descriptor discovery, alias state and loop scheduling |
| A2, implemented in DS-041 | Nested and computed counted-loop controls | A1 for indexed bodies | Original composition proofs; DS-042 supplies the target output profile | High: captured controls, recursive state and bounded execution |
| A3, implemented in DS-042 | Mixed literal/numeric PUT with a narrow integer profile | Existing PUT profiles; A1+A2 for target |100_doors.sas now passes the complete unmodified-file proof | Medium: separator, width, type and atomic publication contracts |
| B1, implemented in DS-043 | Character TRIM/STRIP composition | A2 | loops_for.sas, including both DATA steps, now passes the complete unmodified-file proof | Medium: fixed-width blank/empty behavior |
| B2, implemented in DS-044 | Numeric list INPUT and CARDS/DATALINES | Separate original input contract | integer_comparison.sas now passes the complete unmodified-file proof | High: record/row scheduling, missing/coercion and static typing |
| B3, implemented in DS-045/DS-046 | Multiplication, output-only uninitialized numeric discovery and array composition | A1 | Entire unchanged sum_and_product_of_an_array.sas proof; c remains missing | High: numeric limits, missing state and output descriptors |
| B4, implemented in DS-047/048 | KEEP/DROP statements and bounded DATA/SET selection options | Separate input/output timing profiles | Working PDV, selected descriptors and snapshots proved independently; no new whole-file claim | Medium; other declarations/options remain separate |
| B5, implemented in DS-049/050/051 | Explicit rounded scalar arithmetic, integer power, Pi/trigonometry and logical fractional output | Separate numerical and inferred text policies | Complete unchanged series and trigonometry programs under stated repository/base-R policies | High; earlier exact arithmetic and INT refusals remain; no exact BEST12/live-SAS claim |

A1 has reviewable sub-slices: bounded numeric array declaration/index/OF
execution is implemented in DS-039; single-level implicit numeric DO OVER is
implemented in DS-040. See [the numeric-array profile](NUMERIC_ARRAYS.md) and
[the DO OVER profile](DO_OVER.md) for exact scopes and evidence. A source parser recognizing ARRAY
without those state and descriptor proofs is insufficient.
[A2](COUNTED_LOOPS.md) captures start/stop/BY per invocation, bounds nested work
and prohibits active-index mutation, with original whole-program and base-R proof. [A3](MIXED_PUT.md) now defines literal blanks, numeric fields and logical record
width in a separate operation, preserving existing PUT paths and the bitwise refusal.

Projected target dependencies are conjunctive. A2 alone adds no claimed corpus
proof; A1+A2+A3 together prove100_doors.sas. DS-043 now proves both DATA steps of
loops_for.sas with fixed descriptors and shortened temporary operands. See the
[B1 profile](TRIM_STRIP.md), [B2 input profile](INPUT_LIST.md) and
[B3 numeric composition](NUMERIC_COMPOSITION.md). The Fibonacci corpus file still needs FCMP recursion after its
first DATA step. Each projection must be rechecked after implementation because
compiler tickets can hide additional runtime refusals. No projected proof is
accepted until the entire pinned file executes and compares successfully.

Every implementation slice requires original hand pins, an independent base-R
witness, a registered semantic gate and source suite, known-wrong comparator
controls, static/empty/skipped-path refusals, descriptor/state checks, atomic
failure diagnostics, emitted/CLI agreement and full verification. A whole-file
target also needs its source hash, complete result/stdout pins and independent
comparison. Existing gates keep their order and strength. RSS/timing remain
informational; no repeat memory-profile work is proposed.

## Deferred contracts and other inventory lanes

Macro expansion, FCMP recursion, DS2 objects, OPTMODEL solvers, IML and broader
procedure execution need separately scoped backends and evidence. The existing
statistical/reference fixtures do not authorize source execution of those PROCs.
CALL memory access, random streams, external file engines and email need explicit
state, reproducibility or side-effect contracts. Preserve their current refusal
paths while defining that work. GOTO/LINK/RETURN, grouped control and validation
string/ASCII functions remain later composition work, not hidden parts of A1-A3.

Reference enumeration is a separate planning lane: functions/CALL routines and
formats/informats first, then macros/procedures/options/component objects and
utilities. This ordering is an inference based on the current function-heavy
execution surface. Enumerate published indices and distinguish observed entries
from the full reference universe; do not infer a universe from routed functions.

The operator percentage QoL report remains its own slice, using audited statement
accounting with explicit refusal reasons. Catalogue fractions and compile-clean
fractions cannot serve as semantic translatability percentages. Optional LLM/SAS
endpoints, live-SAS validation and the professional-lane refresh remain separate
directions. This analysis uses no SAS/AWS access.

## Reproduction and receipts

[tools/coverage_inventory.py](../tools/coverage_inventory.py) accepts a corpus
directory, a successful verification receipt and an output path. It records the
current source inventory, all corpus hashes, every diagnostic and the receipt
source. It explicitly reports whether that receipt matches the current files.
Run the golden command first when obtaining acceptance for a changed tree:

```bash
python verify_all.py
python tools/coverage_inventory.py --corpus ../saschi-roku/corpus \
  --receipt telemetry/verify/receipt_SELECTED.json \
  --output telemetry/coverage-inventory.json
```

Replace receipt_SELECTED.json with the actual generated receipt, not a guessed
filename. The reconciliation session binds its exact receipt, baseline snapshots,
compiler probes, failure controls and exhaustive classification audit under
telemetry/coverage-reconciliation-20261027/. Telemetry remains ignored and local;
the session handoff names the final source and evidence. A compiler/classifier
change or new corpus bytes requires a fresh census and a ranking review.
