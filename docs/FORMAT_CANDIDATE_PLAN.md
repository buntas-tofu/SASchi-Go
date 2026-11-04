# Ordered FORMAT candidate staging

Status: six principal-selected bounded stages implemented in the recorded order,
for maintainer review against the current source-bound full receipt. Four
unchanged official examples have separate registered whole-source gates.
FMT-01/H11 and FMT-04/H12 retain their original-target holds while their valid
first-party slices are implemented. Every stage's independent oracle was frozen
before translator implementation; prior full verification closed before the next
implementation began. No release, publication or live-SAS validation is claimed.

The durable source identities, byte counts, SHA256/Git blob pins, license pin,
ordering and open holds are in [the staging register](format-candidate-staging.json).
All six originals come from `sassoftware/sas-code-examples` at commit
`579e057f90cd699f744fd6a1c8acaf9243f7ff67`. Source and LICENSE bodies remain in an
external cache. The [source-hold notes](SOURCE_HOLDS.md) retain the ten observations
from the larger review plus H11 and H12 discovered during processing.

## Sequence and shared preparation

| Order | Work stage | Whole unchanged target | Prerequisites and active holds |
| --- | --- | --- | --- |
| 1 | FMT-01 | Using Nested Formats | DATE9/date-literal, range and formatted PRINT contracts; independent oracle; H11 open |
| 2 | FMT-02 | Using date directives on the PICTURE statement | Accepted stage 1 date foundations; separate PICTURE and PRINT-composition evidence |
| 3 | FMT-03 | Using the By Groupformat Statement to Process Data | Accepted date/range foundations; formatted grouping and a bounded REPORT contract |
| 4 | FMT-04 | Using digit selectors in the PICTURE statement | Prior REPORT groundwork where applicable; fixed-width INPUT and PICTURE editing; H01 repository policy, H12 open |
| 5 | FMT-05 | Using Functions to Create Formats | Date foundations; bounded FCMP/CMPLIB, week alignment and callback/report composition |
| 6 | FMT-06 | Using A Format To Create A Function | Qualified FCMP groundwork; character ranges, quoted input, computed reports and independent ZIPSTATE policy |

On 2026-11-03 the principal requested: "Can we please carry out the remain phases
of the plan and then I will review the commit". This authorizes proceeding through
FMT-02..06 in order while retaining the original FMT-01 hold. A held original
remains unaccepted; independently qualified bounded work and subsequent phases
can proceed under this instruction. Prepare a local commit for review after
verification, without publication or a release.

FMT identifiers name work stages, not implemented rules or capabilities. Keep
the selected order: qualify and close one stage before advancing to the next.
A hold pauses admission of its named target; it does not erase the other staged
work. The continuation instruction above records progression past held FMT-01.
For later stages, retain their order and record any remaining target hold. Do not silently defer or reorder a stage.

Before stage 1 implementation, freeze the shared date ingestion/storage policy,
source/portable admission and namespace rules. Record exact locale, widths,
range endpoints, missing/invalid inputs, record consumption and logical report
text. Set numerical and resource bounds from characterized behavior and original
fixtures. Existing profiles do not acquire new forms by implication.

For every stage, qualify separately authored original hand/base-R expectations
and the complete unchanged vendor target before comparing with new translator
output. A compiler result or agreement between implementations is not a qualified
oracle by itself. Name unresolved behavior explicitly rather than supplying an
expected result from the translator under test.

## 1. FMT-01: nested formats

Target: `By Syntax/FORMAT Procedure/Using Nested Formats.sas`, 1997 bytes.

H11: this original requests WEEKDATE50., outside the documented width range
3 through 37. Native handling of that nested request is unresolved. Canonical
DATE9 and valid-width format work can proceed independently; do not infer a
whole-program expected report or silently repair the source.

The principal selected original-target hold and DATE9/valid-width work. The
separate [source profile](DATE_PROGRAM.md) and [reference helpers](DATE_FOUNDATIONS.md)
implement that bounded slice with a prequalified original hand/base-R oracle.
This does not satisfy the whole unchanged-target exit criterion.

Characterize DATE9 list input, date literals and numeric SAS-epoch storage first.
The source combines whitespace CARDS records, colon-modified character input,
integer fields and DATE9 reads. Freeze this mixed record handling and EOF behavior
separately from the existing comma-input profiles.
Then define numeric VALUE range dispatch into nested WEEKDATE/WORDDATE rendering
and procedure-local formatted PRINT. The stored dates and descriptors must remain
independent of their displayed values.

Oracle work: independently derive date values and boundary membership, then pin
locale, weekday/month spelling, field widths and logical text. Cover every source
row and the entire report. Original controls must distinguish inclusive endpoints,
date storage from presentation, format selection and truncation/padding.

Keep FCMP, PICTURE, formatted BY and PROC REPORT outside this first slice. Exit
requires a bounded original contract and full unchanged-source evidence, not a
new DATE9 helper alone.

## 2. FMT-02: date directives in PICTURE

Target: `By Syntax/FORMAT Procedure/Using date directives on the PICTURE statement.sas`,
3775 bytes.

The [implemented date-picture profile](DATE_PICTURES.md) freezes this slice with
original and unchanged vendor hand/base-R evidence. Its corrected40-character
source passed full verification and both CI workloads before FMT-03 implementation.

Reuse the accepted date foundations only where separately witnessed. Characterize
date PICTURE directives, literal padding, ranges and OTHER, then VAR/OBS PRINT
and the source's two report invocations. Freeze case, leading zeros and width
behavior rather than inheriting platform date-format defaults.

Oracle work: independent dates and dispatch boundaries, exact directive/literal
text, both title/report snapshots and unchanged stored input. Exclude general
numeric PICTURE editing and PROC REPORT. Stage 1 acceptance does not establish
this new composition.

## 3. FMT-03: BY GROUPFORMAT

Target: `By Syntax/FORMAT Procedure/Using the By Groupformat Statement to Process Data.sas`,
3828 bytes.

The [implemented GROUPFORMAT profile](GROUPFORMAT.md) has prequalified original
and unchanged vendor hand/base-R results and traces. Its full receipt decides
acceptance before FMT-04 implementation.

Characterize formatted BY grouping independently from raw-key ordering, including
required source order, FIRST/LAST state and the two separate OUTPUT predicates.
Define a bounded logical PROC REPORT contract with the original dollar/date
formats. Existing PRINT support does not establish REPORT support.

Oracle work: independently derive formatted group membership, tied-row identity,
first/last selection and a row selected by both predicates. Compare full datasets,
descriptors, output order and complete report text. Exclude general REPORT,
physical page layout and broader CLASS/statistics behavior.

## 4. FMT-04: PICTURE digit selectors

Target: `By Syntax/FORMAT Procedure/Using digit selectors in the PICTURE statement.sas`,
3214 bytes. H01 has an explicit bounded repository-envelope policy. H12 holds
the original selector-after-message form without NOEDIT. The
[valid numeric-picture profile](NUMERIC_PICTURES.md) supplies independently
qualified first-party evidence without accepting that original.

Resolve BOM admission explicitly before target acceptance. Preserve the original
byte identity and source accounting. Separately characterize fixed-width
character INPUT, digit-selector editing and NOEDIT. Reuse REPORT groundwork only
under new alias/format composition evidence.

Oracle work: distinguish 09, 99 and NOEDIT for negative, zero, single-digit and
boundary values; pin record consumption, character widths and every report alias.
No silent BOM removal, source repair or general picture-editing claim.

## 5. FMT-05: functions used as formats

Target: `By Syntax/FORMAT Procedure/Using Functions to Create Formats.sas`, 3127 bytes.

The separate [week-callback profile](WEEK_CALLBACKS.md) implements the frozen
whole-source original/vendor contract, conditional on its full receipt.

Define bounded FCMP function lookup, CMPLIB state, namespace lifetime, types,
return behavior and callback timing. Characterize both week INTNX alignments and
their date-rendering compositions. Add REPORT aliases and headers under explicit
logical text policies.

Oracle work: independent sequential date/week calculations and callback results,
followed by complete source/state/report accounting. Exclude general FCMP,
recursion and arbitrary callable or macro expansion. Function reference fixtures
alone do not establish source-level function registration and execution.

## 6. FMT-06: a format used by a function

Target: `By Syntax/FORMAT Procedure/Using A Format To Create A Function.sas`, 3902 bytes.

The separate [postal-function profile](POSTAL_FUNCTION.md) implements this frozen
original/vendor contract under the principal-approved bounded USPS policy.
Reference values and complete derived results stay outside Go. Current full
verification decides acceptance; no native SAS zone-table match is claimed.

Characterize character format ranges, bounded FCMP/CMPLIB, UPCASE and ZIPSTATE,
quoted DSD input and computed REPORT columns. This source uses different function
and report compositions from stage 5.

Oracle work: first approve an independent postal reference policy and the exact
lookup domain, including character versus numeric ZIPSTATE argument behavior.
Preserve leading-zero strings, country dispatch, range endpoints,
quoted-field widths and computed-column timing. City labels are not ZIPSTATE
truth. Compare every source row and complete report. No general postal database,
arbitrary FCMP or unrestricted computed REPORT support is inferred.

## Per-stage exit criteria

1. Bind the full original source and license pins; resolve applicable source
   holds with recorded evidence. A changed source is a new target identity.
2. Freeze the bounded contract and independently qualified original/whole-source
   oracles before translator implementation. Record unresolved questions visibly.
3. Provide original fixtures and R witnesses, component and whole-source gates,
   portable/source refusal controls and known-wrong comparisons. Cover empty or
   skipped paths, schema/metadata preservation and applicable namespace resets.
4. Exercise actual runtime, emitted Python and CLI paths, complete reports and
   later-failure atomic publication. Declared logical text is separate from
   physical SAS output; native behavior claims need their own evidence.
5. Preserve existing profile shapes and refusals, semantics/reference lockstep,
   rule/capability identities and old program regressions. Add no unapproved
   runtime dependency or unenumerated language-coverage claim.
6. Run `python verify_all.py` in its unchanged order, with ALL VERIFIED for the
   recorded source. Complete required CI/workload checks before any authorized
   push. Keep failed attempts, receipts and actual source states distinct.
7. Review that stage's complete evidence before advancing in the selected order.
   Publication and release are separate actions; this staging request does not
   publish anything or pre-accept future passing counts.

Vendor bodies, LICENSE bodies and complete derived vendor results stay outside
Go. Receipts regenerate under ignored telemetry. First-party fixtures and gates
remain reproducible in the repository. The eleven registered vendor programs and the
Roku corpus retain separate denominators. Human-interface testing remains queued
separately; none is claimed by these staged contracts.

## Review and later interface session

The [human interface protocol](HUMAN_INTERFACE_TEST_PLAN.md) is staged for later,
completed human sessions n=0. Full verification and workload receipts regenerate
under telemetry/fmt-01-20261103 through telemetry/fmt-06-20261103; each completed
phase has a VALIDATION.json binding its actual source and receipt. Failed attempts
are retained separately. The local review commit records the final receipt and
source hashes. A clean compile alone is not whole-program proof.

The same44-entry official remainder was screened again after implementation:
42compile attempts,4clean,38blocked,1empty entry and1encoding deferral. The four
clean entries are exactly the four new registered whole-source vendor targets;
compile-only screening does not itself admit them. Eleven registered official
programs out of the pinned51-entry inventory leave40entries for later work,
including the two held originals. Source identities and original observations
are preserved.
