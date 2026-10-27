# Coverage reconciliation and next gate series

Status: Repository/base-R planning evidence at main08eaa7b, reconciled2026-10-27.
For principal/maintainer prioritization. Counts describe this checkout and the56
pinned sibling corpus files, not all SAS or live-SAS equivalence. Rankings,
diagnostic categories and projected unlocks are explicitly analyst inferences.
Implementation and publication are not authorized by this planning exercise.

## Inventory reconciled against actual evidence

The golden command registers46 fixture runners,36 translator suites and1
synthesis runner. The latest passing baseline contains608 tests, zero skips,
60 faithful synthesis checks and60 naive controls. The separate1k workload
checks total39:18 ledger and21 text. These counts have different units. Neither
73 rulebook rules nor83 golden-command runners is a SAS capability denominator.

[The capability manifest](capability-manifest.json) still enumerates108 statements
and40 data-set options. The other7 declared reference areas remain unenumerated:
formats/informats, functions/CALL routines, system options, component objects,
utilities, macros and procedures. Their null universes are not zero.

The reconciled148 entries contain23 GATED,5 RULE,8 HUMAN-REVIEW,22 OUT-OF-SCOPE
and90 UNASSESSED. Among GATED entries,20 have bounded source-execution evidence;
3 have reference fixtures only: ARRAY, Array Reference and IN=. These are
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

All90 unassessed entries receive planning bins in the reproducible inventory:
29 external-environment review,13 separate-scope review,12 input records,
12 data-set options,9 control,7 output,5 descriptor/environment and3 projection.
These bins organize work; they do not promote dispositions or decide exclusions.
The5 RULE entries and8 HUMAN-REVIEW entries retain their review boundaries.

## Unknown blockers classified

The current56-file compile census remains12 clean and44 blocked, with754 ticket
occurrences across29 existing route labels. All491 occurrences previously routed
as unknown receive a primary planning category, with file, line, ticket ordinal,
statement hash and classification basis preserved. No compiler ticket is removed.

| Primary category for unknown tickets | Occurrences |
| --- | ---: |
| Procedure backend/clauses |228|
| Macro body, invocation or unresolved reference |129|
| Input records, INPUT/INFILE and opaque inline data |53|
| Labels, GOTO/LINK/RETURN/STOP |35|
| Arrays and indexed writes |24|
| KEEP/DROP projection |8|
| External file/engine output |4|
| Descriptor/environment statements |4|
| Corpus prose or printed output |2|
| Rejected DATA header follow-on diagnostics |2|
| CALL side effects |2|
| Total |491|

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

Nine files retain existing complete-program proofs. The other3 compile-clean
files remain separate: hello_world_text.sas needs a whole-file witness,
comments.sas needs an explicit no-op acceptance witness, and bitwise_operations.sas
retains the67-column refusal under the64-column PUT_ALL profile. No proof count
is increased by this analysis. Compile tickets also miss runtime limitations:
numeric-list PUT is currently bounded integer output; division requires exact
representability; INT has its conservative near-integer refusal band.

## Prioritized finite backlog

Inference: prioritize a coherent DATA-step composition series that reuses the
existing array reference witnesses and aims at two whole-file targets. Frequency
alone would prioritize priority_queue.sas, whose205 tickets span macros and DS2;
that is a much broader semantic and runtime contract. This is a qualitative
evidence-cost ranking, not a schedule or an estimate of business demand.

| Order | Slice | Dependencies | Target and projected result | Evidence cost |
| --- | --- | --- | --- | --- |
| A0, optional evidence closeout | Hello-world and comment-only whole-file witnesses | Existing behavior | At most2 new proofs, no language expansion | Low |
| A1, first implementation milestone | Numeric array declarations, indexed access/assignment, OF aggregation and DO OVER alias iteration | Existing DS-016 helper witnesses | loops_foreach.sas is the first projected full-file target | High: descriptor discovery, alias state and loop scheduling |
| A2, second milestone | Nested and computed counted-loop controls | A1 for indexed bodies | Original composition proofs;100_doors.sas still needs A3 | High: captured controls, recursive state and bounded execution |
| A3, third milestone | Mixed literal/numeric PUT with a narrow integer profile | Existing PUT profiles; A1+A2 for target |100_doors.sas becomes a projected full-file target | Medium: separator, width, type and atomic publication contracts |
| B1 | Character TRIM/STRIP composition | A2 | loops_for.sas, including both DATA steps, becomes a projected target | Medium: fixed-width blank/empty behavior |
| B2 | Numeric list INPUT and CARDS/DATALINES | Separate original input contract | integer_comparison.sas is a projected target | High: record/row scheduling, missing/coercion and static typing |
| B3 | Multiplication, output-only uninitialized numeric discovery and array composition | A1 | sum_and_product_of_an_array.sas is a projected target; its c is uninitialized | High: numeric limits, missing state and output descriptors |
| B4 | KEEP/DROP projection, followed by declarations/options | Separate input/output timing profiles | Broad composition value, no immediate full-file unlock claimed | Medium |
| B5 | Fractional numeric rendering, wider arithmetic and elementary functions | Separate precision/error contracts | sum_of_a_series.sas and trigonometric_functions.sas require several additional slices | High, retain current exact-division and INT refusals until replaced by evidence |

A1 should land as reviewable sub-slices: numeric array declaration/index/OF
execution first, DO OVER scheduling second. A source parser recognizing ARRAY
without those state and descriptor proofs is insufficient. A2 must state how
start/stop/BY expressions are captured, bound nested work and prohibit unsupported
index mutation. A3 must define how literal blanks, numeric fields and record
width interact, without widening existing PUT paths or the bitwise refusal.

Projected target dependencies are conjunctive. A2 alone adds no claimed corpus
proof; A1+A2 alone does not unlock100_doors.sas. loops_for.sas still needs
TRIM/STRIP, and the Fibonacci corpus file still needs FCMP recursion after its
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
