# Fifth DATA step wave: expressions with state and snapshots

Status: principal-approved local implementation scope, approved 2026-11-14,
from merged PR79 commit `d25b2e748969e2fa18127557a7081734c61a2714`. The principal
approved all four stages and BOTH complete target programs, with hand/base-R
oracles frozen first and full verification plus both unchanged workloads passing
at every stage. The body retains the reviewed planning proposal; registrations
and matching source-stable receipts decide acceptance. No native SAS validation,
new external-program proof or publication authority is implied by approval.
UI changes are explicitly deferred.

## Implemented scope and evidence map

All four components and BOTH unchanged complete originals are registered in the
separate bounded profile. All six complete hand/base-R originals qualified before
translator changes, with 30 whole generated catalogs each. Every row requires
its own matching source-stable full verification and both unchanged 1k workloads;
this map records implementation and registrations, not a substitute verdict.
The [current contract](STATEFUL_EXPRESSIONS.md) states the implemented limits.

| Order | Complete original | Registered gate | Source suite |
| --- | --- | --- | --- |
| 1 | [Decision groups/output](../examples/stateful_decisions_capture.sas) | [Gate](../examples/verify_stateful_decisions.py) | [Suite](../saschi/test_stateful_decisions.py) |
| 2 | [Numeric retention](../examples/stateful_retention_capture.sas) | [Gate](../examples/verify_stateful_retention.py) | [Suite](../saschi/test_stateful_retention.py) |
| 3 | [Expression sums](../examples/stateful_sums_capture.sas) | [Gate](../examples/verify_stateful_sums.py) | [Suite](../saschi/test_stateful_sums.py) |
| 4 | [Ordered BY groups](../examples/stateful_groups_capture.sas) | [Gate](../examples/verify_stateful_groups.py) | [Suite](../saschi/test_stateful_groups.py) |
| 5 | [Record-quality audit/review queue](../examples/record_quality_audit_capture.sas) | [Gate](../examples/verify_record_quality_audit.py) | [Suite](../saschi/test_record_quality_audit.py) |
| 6 | [Batch reconciliation/review list](../examples/batch_reconciliation_capture.sas) | [Gate](../examples/verify_batch_reconciliation.py) | [Suite](../saschi/test_batch_reconciliation.py) |

The sections below preserve the reviewed planning proposal and its entry-source
measurements. Historical refusals and provisional hand-design labels describe
that planning point. The unchanged target source bytes are now the registered
originals above. UI changes remain deferred.

The principal selected continuing composition and requested two useful complete
target programs. Interface simplification is a separate, secondary review of the
desktop/browser workflows, with all features preserved. That review does not
expand or gate the language proposal.

## Recommendation and accepted entry

Engineering recommendation: join a small cohort of existing pure expressions to
existing grouped actions, explicit snapshots, numeric state and ordered groups.
Choose two original analyst workflows: a record-quality audit with a review queue,
and per-batch reconciliation with a separate review list. These are complete
first-party programs over synthetic supplied catalogs, not excerpts of corpus or
vendor programs. Their usefulness is an engineering inference, not measured demand.

The accepted entry passed 146 fixture gates, 110 suites, 2,154 tests, zero skips,
synthesis and both unchanged 1k workloads, ledger 18 and text 21 checks. The
composition source SHA-256 is
`0ab6f0fa8a28ce6f98d313c03382b982a19b0a8ebec7e57876815d735c04f35a`.
The accepted receipt SHA-256 is
`3e9fea6aba47a450e731e67c13a20a9d2cddc261390a55fd63eb79f6538c7e18`.
Planning observations were collected against that exact source before these
planning documents were added. They are not a fresh full run for this edited tree.

[Typed expressions](FUNCTION_EXPRESSIONS.md), [grouped control](GROUPED_CONTROL.md),
[nested counted loops](COUNTED_LOOPS.md) and the earlier event witnesses already
prove separate building blocks. Existing full receipts remain evidence for their
recorded source. This proposal changes no runtime, rule, fixture, dependency or
capability registration.

## Why these two targets

A fresh compile-only screen checked six unchanged pinned sibling programs:
loops_break, primality_by_trial_division, ISIN validation, cumulative standard
deviation, fivenum and merge_and_aggregate_datasets. Their source hashes match the
accepted inventory; all six remain blocked. Inspection found additional random
streams, callback/control/array joins, external input or procedure requirements.
For example, the one-ticket loops_break program calls UNIFORM; the short ISIN
validator also needs RANK, indexed state, sum statements and LINK/RETURN.
Low ticket counts do not establish a small complete-program contract.

Inference: two original workflows isolate a useful state/composition join more
cleanly than promising two new external completions. The existing 22 complete
Roku proofs among 56 pins and separate vendor proofs remain unchanged.

## Target 1: record-quality audit and review queue

Purpose, an engineering inference: normalize identifiers, evaluate independent
quality rules and retain every applicable reason in encounter order. A record
with two failed rules produces two audit observations. Valid records produce one
ACCEPT observation. A second DATA step derives the review queue from that audit.
This preserves why a record failed rather than reducing all failures to one flag.

The synthetic input `submissions` has ordered fields row_id, raw_id, value, lower,
upper. raw_id is printable ASCII with a 24-byte character descriptor; the other
fields are bounded integers or ordinary numeric missing. Supplied identifiers
may contain surrounding blanks and quotes. No external file or inline INPUT is
required.

Complete proposed source:

```sas
data quality_audit;
  length record_key $24;
  length reason $12;
  set submissions;
  record_key=upcase(compbl(dequote(strip(raw_id))));
  bad_id=notalnum(strip(record_key))>0 or lengthn(strip(record_key))=0;
  bad_measure=n(value,lower,upper)<3 or lower>upper or value<lower or value>upper;
  if bad_id then do;
    reason='IDENTIFIER';
    output;
  end;
  if bad_measure then do;
    reason='MEASUREMENT';
    output;
  end;
  if not bad_id and not bad_measure then do;
    reason='ACCEPT';
    output;
  end;
run;

data review_queue;
  set quality_audit;
  where reason^='ACCEPT';
run;
```

Provisional hand design, not a qualified oracle or execution result:

| Input row | raw_id | value | lower | upper | Intended audit reasons, in order |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | ` "a1" ` | 5 | 0 | 10 | ACCEPT |
| 2 | `b-2` | 12 | 0 | 10 | IDENTIFIER, MEASUREMENT |
| 3 | three blanks | . | 0 | 10 | IDENTIFIER, MEASUREMENT |
| 4 | `c3` | 7 | 10 | 5 | MEASUREMENT |
| 5 | `"d4"` | . | 0 | 10 | MEASUREMENT |
| 6 | ` e5 ` | 0 | 0 | 10 | ACCEPT |
| 7 | `'F6'` | 5 | 0 | 10 | ACCEPT |

The hand design expects 9 audit observations and 6 review observations. The
normalized stored keys have width 24; the empty key becomes a stored blank.
NOTALNUM therefore inspects STRIP(record_key), not its padded storage. STRIP
also precedes DEQUOTE so leading blanks do not prevent quote removal. The deepest
normalization path uses the existing four-call limit.

The first draft exposed that padding mistake in an existing-profile control:
observed identifier flags were both false where the draft expected a valid
identifier to pass. The failed control and original draft are retained locally.
The corrected pure expression kernel matches all seven selected hand rows on
the unchanged runtime. That is a supplemental kernel observation only; the full
two-step target still refuses and needs independent whole-program R qualification.

## Target 2: grouped batch reconciliation and review list

Purpose, an engineering inference: compare supplied amounts with expected values,
accumulate accepted/rejected counts, net discrepancy, total absolute discrepancy
and worst discrepancy, then emit one summary at each batch boundary. A second
step lists batches needing review. This tests state lifetime and output timing,
not merely whether a normalization expression compiles.

The synthetic input `ledger` is ordered by one ascending numeric batch key. Its
remaining ordered fields are label, amount, expected and limit. label is printable
ASCII of width 16; numeric values are bounded integers or ordinary missing.
Output batch_label and limit reflect the last input observation of the group;
no group-constant configuration is inferred. Retained accumulators are fresh names
that do not collide with input columns.

Complete proposed source:

```sas
data batch_summary;
  length batch_label $24;
  length status $8;
  retain seen 0;
  retain accepted 0;
  retain rejected 0;
  retain net 0;
  retain magnitude 0;
  retain worst 0;
  set ledger;
  by batch;
  batch_label=upcase(compbl(strip(label)));
  if first.batch then do;
    seen=0;
    accepted=0;
    rejected=0;
    net=0;
    magnitude=0;
    worst=0;
  end;
  seen+1;
  if n(amount,expected)=2 then do;
    delta=amount-expected;
    accepted+1;
    net+delta;
    magnitude+abs(delta);
    worst=max(worst,abs(delta));
  end;
  else rejected+1;
  if last.batch then do;
    status=ifc(rejected=0 and worst<=limit,'READY','REVIEW');
    output;
  end;
run;

data review_batches;
  set batch_summary;
  where status='REVIEW';
run;
```

Provisional hand design for the prepared nine-observation input:

| Batch | Seen | Accepted | Rejected | Net | Magnitude | Worst | Last-row delta | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 101 | 3 | 2 | 1 | -1 | 5 | 3 | -3 | REVIEW |
| 102 | 2 | 2 | 0 | 0 | 2 | 1 | -1 | READY |
| 103 | 1 | 0 | 1 | 0 | 0 | 0 | missing | REVIEW |
| 104 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | READY |
| 105 | 2 | 1 | 1 | 2 | 2 | 2 | missing | REVIEW |

The raw amount/expected pairs are 101: (100,98), (.,4), (91,94);
102: (5,4), (8,9); 103: (.,.); 104: (3,3); 105: (7,5), (.,4).
All sample limits are 2. The intended outputs are 5 summaries and 3 review rows.
The last invalid row in batch 105 makes delta missing, while retained net and
magnitude stay 2. A stale scratch delta must not masquerade as retained state.
All stored fields and descriptors, including the inherited last input values,
must be checked by the future whole-program oracle, not only the columns above.

## Measured blockers and working controls

Both complete sources currently refuse at their DATA header under grouped-control
routing: the first diagnostic is that the character LENGTH declaration lies
outside the bounded numeric grouped-control contract. That diagnostic masks later
joins. Six smaller source probes expose the other boundaries:

| Join probe | Actual current refusal |
| --- | --- |
| Character expressions and a compound decision ending in OUTPUT | IF THEN requires a simple assignment, OUTPUT or bounded PUT action; older function-consumer validation also refuses the ticketed program |
| Character expression inside IF/THEN DO | Grouped control admits integer +/-/* without numeric calls |
| MAX/ABS expression assigned to a retained accumulator | Function-wave WHERE, BY, RETAIN and multiple inputs require separate composition |
| ABS expression in a sum statement | Same function-wave state/composition refusal |
| ABS expression in a BY step with last-group OUTPUT | Same function-wave state/composition refusal |
| FIRST flag in a compound function predicate | IF THEN requires a simple assignment, OUTPUT or bounded PUT action |

These are compiler observations, not conclusions that the proposed combinations
would be safe after removing a guard. Six separate positive controls compile and
execute on the unchanged runtime: pure expressions, conditional OUTPUT, numeric
RETAIN/BY totals, numeric grouped actions, a sum statement and ABS subtraction.
The controls check selected hand values and caller nonmutation. They do not add
independent R, emitted-code, CLI or full acceptance evidence for this proposal.

Source inspection confirms the boundary in the
[expression validator](../saschi/function_expressions.py): it rejects nonempty
BY or retained fields, limits IF actions to assignment/IF, and admits no grouped
action, explicit OUTPUT or sum-statement operation. The older grouped-control
profile admits numeric integer bodies. The missing work is independent source,
portable, scheduling and emission qualification across those boundaries;
removing the existing refusal checks would not supply it.

## Proposed bounded contract

Engineering proposal: a distinct ordinary version 2 `stateful-expressions-v1`
profile, selected only for an actual newly qualified join. Preserve old profile
selection, portable fields, plans, emitted bytes and refusal contracts. Reuse the
typed expression machinery and existing state primitives through explicitly
validated argument roles; do not make old markers authorize the new combinations.

The initial contextual cohort is exactly 10 existing names: UPCASE, COMPBL,
STRIP, DEQUOTE, NOTALNUM, LENGTHN, N, ABS, MAX and IFC. No scalar name is added.
The existing 46-name pure expression profile remains independently available;
other names do not silently enter the new stateful profile.

Proposed admission:

- One driving ordinary SET and one fresh named DATA destination per marked step.
  Supplied or prior-step catalogs use the existing ordered typed input contract.
- Character declarations and assignments, typed comparisons and Boolean choices,
  IF/THEN/ELSE, nested simple DO/END groups and unnamed or same-destination OUTPUT.
  Grouping adds no iteration. Explicit OUTPUT captures the complete current row;
  its static presence suppresses implicit output, even when never reached.
- Fresh numeric RETAIN names with one explicit literal initializer each, numeric
  expression assignments, and sum statements with qualified numeric contributions.
  Scratch variables reset each input observation. Retained state resets per step/run.
- One ascending numeric BY key with reached FIRST.key/LAST.key reads. Ordered input
  is validated, not silently sorted. Missing keys follow the existing missing-first
  numeric policy. Flags stay temporary and do not become output columns.
- Existing type, width, missing, eager selector, Boolean admission and +/- policies.
  Retained values and sum contributions are ordinary missing or exact integers of
  magnitude at most 1,000,000; every reached accumulated result obeys that bound.
  Input collisions with retained names refuse in this initial profile.
- Proposed caps: 16 steps, 256 operations per marked step, 128 call sites, four
  nested calls, expression/action depth 16, structural depth 64, 16,384 containers,
  4,096 provenance rows, 16 retained names, 64 stored columns, 10,000 input and
  output observations per marked step, and 1,000,000 scheduled actions per step.
  Freeze exact counting and boundary cases before implementation. These are tool
  limits, not SAS language limits.

Numeric literals, static type/width errors, declarations and portable shapes are
validated on skipped and empty paths. Dynamic invalid values in unreached IF
bodies stay unreached; reached selector arguments retain eager validation. Earlier
snapshots must not be retroactively changed. A later fault discards the entire
job's accepted result and emitted stdout, including earlier completed steps.

Keep loops, arrays, LAG/DIF, character retention, MERGE, lookup/multiple SET, named
multiple destinations, replacement, new projection joins, INPUT/INFILE, macros,
callbacks, procedures, SQL and C++ outside this profile. WHERE and subsetting IF
inside a marked stateful step remain held; ordinary later filtering steps in the
two targets keep their already qualified behavior. Multiplication, division,
powers, broader fractional accumulation and new function names are not proposed.
Legacy <> and bare NOT semantic-review questions remain separate decisions.

## Four stages and both complete finish programs

Each row receives a distinct original complete program, hand/base-R oracle,
registered gate, source suite, source-stable full run and both unchanged workloads.
The proposed order is an engineering dependency inference, not a schedule.

| Order | Scope | Discriminating evidence |
| --- | --- | --- |
| 1 | Mixed typed decision groups and explicit snapshots | Two reasons for one input; skipped OUTPUT suppresses implicit output; snapshots before/after assignment; empty input still discovers complete descriptors |
| 2 | Fresh numeric retained state with typed expressions | Scratch versus retained values; per-step/run reset; missing initializer; all-skipped assignment; input collision refusal; overflow after a working prefix |
| 3 | Sum-statement reducers over qualified expressions | Implicit zero initialization/retention; missing contribution versus ordinary addition; signed cancellation; no retained state written to the caller |
| 4 | One ordered numeric BY group | Singleton and missing-key groups; first-row reset and last-row snapshot; unsorted refusal; mixed predicates reading flags; no flag leakage |
| 5 | Complete record-quality audit and review queue | All ordered fields, duplicate reason rows, metadata and downstream queue across both original steps |
| 6 | Complete batch reconciliation and review list | All summaries, scratch reset on the last invalid row, retained counters/totals and downstream review list |

Do not stop after the component stages. Both complete original programs remain
the proposed finish line. At least six new gates/suites follow this split; actual
registry counts follow implementation and passing receipts, not this forecast.

## Characterization and acceptance before implementation

Primary documentation was checked on 2026-11-14. SAS describes OUTPUT as an
immediate observation write that replaces automatic output, including conditional
use. This anchors snapshot timing and static suppression.
[OUTPUT statement](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n1lltvbis7ye1an1eryo4leh2mck.htm).

The DATA-step execution reference distinguishes default reset, IF actions and
output timing. Retention changes selected state lifetimes; it does not make every
scratch variable persistent.
[DATA-step execution](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a001331122.htm).

The sum-statement reference specifies initial zero, retained accumulator state
and a missing contribution treated as zero. Its behavior must be distinguished
from ordinary missing-propagating addition.
[Sum statement](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n1dfiqj146yi2cn1maeju9wo7ijs.htm).

The BY reference describes first/last temporary flags, including singleton groups;
the next observation determines the last flag. Whole-group timing must therefore
be qualified, not inferred from evaluating a scalar predicate.
[BY-group identification](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a000761931.htm).

Before any translator changes:

1. Obtain an explicit scope decision on this concrete proposal. Continuing
   composition is a planning direction, not approval of these six stages.
2. Recheck AGENTS, merged main, the locked environment, pinned sibling corpus and
   explicit external caches. Obtain a fresh unchanged golden baseline and both
   unchanged workloads on one stable source.
3. Freeze the profile/operation/node/read-order grammar, retained-name ownership,
   numeric contribution rules, descriptor formation and resource counting. Pin
   exact primary sections and any source contradictions; resolve before admission.
4. Independently author and qualify complete hand/base-R witnesses for all four
   stages and both two-step originals before implementing the corresponding join.
   The small hand designs above are not complete qualified oracles. Require at
   least 30 generated complete catalogs per program, including empty and adversarial
   groups, and contextual pins for all 10 selected names.
5. For every stage, check complete runtime, emitted Python and actual CLI results;
   every stored field, schema/column/row order, widths, labels, formats and logical
   output must agree. Each wrong value/type/metadata/row/column/log comparison
   gets a fresh output root and a receipt naming the intended mismatch.
6. Test malformed/cyclic portable plans, exact budgets, skipped/empty paths,
   eager static versus reached dynamic faults, deterministic emission, input/plan
   nonmutation, no hidden globals, source lines and late whole-job atomic failure.
7. Preserve the old 146 fixture registrations and 110 suites in order, all 172
   rule objects, 80 runtime-capability objects, 319 scalar names, prior reference
   bytes, profile modules, accepted programs, locks and corpus. Reconcile any
   overlapping refusal test with its exact old-profile negative and a separately
   gated new-profile positive; retain failed attempts.
8. Accept each component and each finish program separately with source-stable
   ALL VERIFIED and both unchanged 1k workloads before advancing. No publishable
   edits during a full acceptance run. Re-screen external inventories at completion
   without counting a compile result as a new execution proof.

No new runtime dependency is proposed. Keep raw receipts, source-reference bodies
and local planning records outside publication. Validate documentation with the
invariant linter, strict sanitization, manifest schema and local links. Publishing,
merging, releasing and refreshing a sibling lane are separate instructions.
