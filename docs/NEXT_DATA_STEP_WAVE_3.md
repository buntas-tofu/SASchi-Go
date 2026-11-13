# Third DATA step function wave: selection and reconciliation

Status: principal-approved local implementation contract for maintainer review,
based on merged commit `044b44311816a21d0032f5c1fa2900ca02ba91eb`. On 2026-11-13
the principal approved all 31 selected names, the separate finite nested/IF phase
and both complete original programs. All are implemented within the bounded
contracts in the [evidence register](FUNCTION_WAVE_3_COMPOSITION.md). Acceptance
requires the matching stable full receipt and both unchanged workloads. No
native SAS validation, complete function census or publication is implied.
The body retains the original engineering choices and acceptance sequence.

Recommendation, an engineering inference: add six bounded families covering
31 selected names, qualify a separate nested-call and IF consumer phase, then
finish with two original complete programs. Selection and reconciliation are
the organizing use cases. The ranking reflects contract reuse and isolation;
it is not a measured frequency ranking or a forecast of corpus completions.

## Accepted starting point

[PR77](https://github.com/buntas-tofu/SASchi-Go/pull/77) merged wave 2 after all
five PR checks and both workflows passed. Its source passed 128 fixture gates,
92 suites, 1,925 tests with zero skips, synthesis, and both unchanged 1k
workloads. The workloads retain 18 ledger and 21 text checks. These outcomes
identify the accepted implementation, not a fresh golden run for this planning
document or a later checkout.

The [wave 2 evidence register](FUNCTION_WAVE_2_COMPOSITION.md) covers whitespace,
CAT functions, selected character validators, positional search/extraction,
row statistics and supplied datetime components. The preceding
[wave 1 register](FUNCTION_WAVE_COMPOSITION.md) covers case/search, words,
rewriting, missing summaries, numeric helpers and calendar intervals. Together
the two waves selected 54 names, with separately bounded source contracts.

| Current foundation | Boundary the next wave must preserve |
| --- | --- |
| Direct assignments from both waves | Supported arguments and missing/error policies belong to each family; a registered name does not admit every signature |
| Character storage, padding and metadata | Stored width differs from temporary length; preserve descriptor and output order |
| `function-consumers-v1` | Finite normalization chains, selected CATS items and selected validator/MISSING IF comparisons only; see the [exact consumer contract](FUNCTION_CONSUMERS.md) |
| MEDIAN, RANGE, VAR and STD | Bounded row functions, not arbitrary procedure statistics or a blanket floating-point policy |
| SQRT and LOG | Already supported through `binary64-math-v1`; their absence from the general registry does not make them missing functions |
| Probability reference helpers | Existing reference fixtures do not establish ordinary source or portable-plan admission |
| Calendar and datetime work | Supplied values and explicit domains; no implicit clock, timezone or year-cutoff authority |

Planning probes at the merged source found all 31 selected direct call forms
blocked, absent from the general scalar registry and without corresponding
named canonical reference helpers. Five selected consumer forms are also
blocked. Four existing controls compile within their own profiles: SQRT, LOG,
direct MEDIAN and the accepted UPCASE/STRIP chain. Mixing character setup into
the SQRT/LOG controls remained refused, so those controls do not establish
cross-profile composition. These are compile-only observations, not execution
or complete signature proofs.

The [capability manifest](capability-manifest.json) retains a null
functions/CALL universe. Preserve that denominator. Reference helpers, aliases,
rule counts and selected names are different units and cannot produce a
percentage of all SAS functions.

## Approved implementation order

Each family starts with direct assignment and primitive arguments. Introduce
new consumers only in the later acceptance phase. Split a family when its
oracle, numerical policy or error-state boundary requires separate acceptance.

| Phase | Family and selected names | Contract to freeze before implementation | Original whole-program witness |
| --- | --- | --- | --- |
| 1 | Text and quoting, 5: PROPCASE, QUOTE, DEQUOTE, COUNTC, TRANSTRN | Printable ASCII; explicit PROPCASE delimiters; quote escaping and destination buffers; DEQUOTE termination; explicit COUNTC sets and a qualified modifier subset; replacement length and blank handling | Normalize and quote supplied labels, count selected characters and rewrite record markers, comparing stored bytes and descriptors |
| 2 | Printable ASCII positions, 7: ANYLOWER, ANYUPPER, ANYPUNCT, ANYXDIGIT, NOTALPHA, NOTALNUM, NOTSPACE | Exact character masks, one-based positions, signed starts, stored padding and no-match/missing policies; retain the earlier validation contract | Classify mixed identifiers and preserve the exact first matching or rejected position |
| 3 | Selection and lookup, 6: IFN, IFC, CHOOSEN, CHOOSEC, WHICHN, WHICHC | True/false/missing selection; eager argument evaluation; signed CHOOSE indexes; first-match and duplicate behavior; numeric versus padded character equality; character result widths | Resolve numeric and character classifications from supplied flags and finite lookup lists |
| 4 | Rank and sums of squares, 4: LARGEST, SMALLEST, CSS, USS | Rank versus nonmissing count; ties, all-missing/singleton inputs; independent sums-of-squares formulas, bounds and rounding policy | Reconcile complete measurement rows and distinguish centered from uncentered summaries |
| 5 | Numeric functions without fuzzing, 5: CEILZ, FLOORZ, INTZ, ROUNDZ, MODZ | Finite bounded binary64 operands; dyadic inputs and power-of-two rounding units first; exact ties, adjacent floats, signed remainder, missing and invalid-domain refusals | Reconcile supplied quantities at integer boundaries, half ties and remainder boundaries |
| 6 | Calendar constructors and ordinal dates, 4: HMS, YYQ, DATEJUL, JULDATE7 | Integral time components; four-digit years; strict seven-digit ordinal inputs; leap-day/day-of-year validation; explicit valid date domain and missing policy | Convert supplied quarter, time and ordinal fields and compare complete calendar output |

The selected count is 5 + 7 + 6 + 4 + 5 + 4 = 31 distinct names. It is a
selected inventory count. Six family gates, one consumer gate and two complete
composition gates qualify their bounded forms; they do not enumerate all
signatures of every listed function.

## Decisions that prevent plausible wrong translations

**Text temporaries.** Treat QUOTE buffer exhaustion and DEQUOTE malformed
inputs separately from ordinary truncation. Freeze inferred and predeclared
destination widths. Distinguish a stored blank replacement from the zero-length
temporary needed for TRANSTRN deletion. The proposed initial source deletion
form belongs to the consumer phase: `TRANSTRN(txt,'-',TRIMN(' '))`. Do not
silently treat a SAS empty character literal as a zero-length temporary.
The [QUOTE reference](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p059exu866hqw2n0zw9aoxf3p6oj.htm)
identifies doubled embedded quotes and buffer-dependent diagnostics; freeze
the selected behavior against the pinned edition before implementing it.

**Selectors.** Evaluate every admitted argument of a reached call, including
unselected result arguments. IFN is not a lazy IF/THEN/ELSE translation, as
explained in [SAS's evaluation guidance](https://blogs.sas.com/content/iml/2017/06/07/ifn-function-versus-if-thenelse-sas.html).
This does not require evaluating calls in an unreached statement branch.
Start with primitive selector arguments; nested branches follow only after
their own error and width evidence. Freeze negative CHOOSE indexes rather
than assuming host indexing rules; the [CHOOSEN reference](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p0et55hpbrn2vln14mmqrhzffs64.htm)
documents counting from the end. Classify zero, fractional, missing and
out-of-range indexes individually.

**Rank and numerical domains.** Distinguish an invalid rank from a valid rank
that exceeds the nonmissing count. Begin with explicitly bounded integral row
inputs and ordinary missing, without OF lists or tagged-missing expansion.
Freeze CSS/USS hand pins, independent R calculations and comparison tolerances
before implementation; the VAR/STD policy does not automatically transfer.
Include cancellation-sensitive offsets, repeated values and singleton rows.

**ROUNDZ and MODZ.** A rename of the old ROUND/MOD implementation is insufficient.
The [ROUNDZ reference](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p1u0w0omad7fyxn1unu83odr6vy2.htm)
specifies even-multiple behavior at exact halfway cases. Qualify binary64
neighbors on both sides of a tie, signed zero and negative operands. Freeze
the [MODZ](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p16o2egyjzxmxhn1uwomog96x046.htm)
remainder slice independently. Decimal units, overflow, underflow and arbitrary
fractional domains remain held unless separately qualified in this wave.

**Calendar authority.** Admit YYQ with four-digit years and DATEJUL with valid
seven-digit `yyyyddd` values first. Use JULDATE7 for deterministic ordinal
output. JULDATE remains deferred because its result depends on YEARCUTOFF;
see the [SAS date-function discussion](https://support.sas.com/documentation/cdl/en/etsug/60372/HTML/default/etsug_intervals_sect014.htm).
Keep fractional or normalized HMS components, two-digit years, system clocks
and timezone conversion outside the initial contract. Do not add a hidden
default session option to accommodate them.

## Separate nested-call and IF phase

After all six families pass, freeze a finite typed call/consumer matrix and
resource bounds. Proposed forms for this phase are:

```sas
status = ifc(notalnum(code)=0,'OK','REVIEW');
chosen = ifn(flag,fallback,largest(k,a,b,c));
identifier = cats(propcase(label,' -'),'-',dequote(code));
cleaned = transtrn(label,'-',trimn(' '));
if anyupper(code)>0 then has_upper=1;
else has_upper=0;
```

These snippets are future admission targets, not currently runnable examples.
Freeze their exact argument, operator, width and error bounds before parser
work. The initial scope is these finite shapes and an explicit list of
selected validator IF comparisons, not arbitrary recursive expressions.

Use a separately versioned profile and retain `function-consumers-v1` unchanged.
Qualify source and portable markers, expression shapes, temporary widths,
inferred descriptors and plan resource limits independently. In particular,
an invalid nested LARGEST argument must fail even when IFN selects the other
result. A skipped statement branch must retain its existing reached-only
dynamic evaluation, while literal and descriptor checks still run on empty
or skipped paths. TRANSTRN must distinguish zero-length deletion from blank
replacement through runtime, emitted code and CLI results.

General WHERE, subsetting IF, compound Boolean conditions, deeper nesting,
queues, loops, arrays, BY, RETAIN, C++, SQL and specialized numeric/profile
joins remain outside this new consumer phase. Preserve earlier independently
accepted behavior rather than expanding or narrowing those profiles by name.

## Two complete-program finish lines

1. **Quoted record classification.** Combine PROPCASE, QUOTE/DEQUOTE, COUNTC,
   TRANSTRN deletion, selected ASCII validators, WHICH/CHOOSE lookup and
   IFC/IFN decisions. Include padded and blank records, embedded quotes,
   duplicate lookups, rejected identifiers and empty input. Every stored
   field, descriptor and logical report record needs an independent expected
   value. Keep any export or report path within an existing qualified contract.
2. **Quarterly measurement reconciliation.** Combine supplied HMS/YYQ and
   ordinal conversions with prior calendar components, missing summaries,
   LARGEST/SMALLEST, CSS/USS and the new numeric variants. Use stored values
   wherever nesting is not explicitly admitted. Cover leap years, quarter
   boundaries, tied/missing ranks, all-missing/singleton rows, exact half ties
   and invalid late input. Compare the complete ordered result and logical
   output, not selected cells alone.

Freeze both original hand/base-R program oracles before their composition
implementation. Six family witnesses, one distinct consumer witness and these
two programs give at least nine original program contracts. Gate/suite counts
follow the accepted implementation splits rather than the planning name count.

## Acceptance and preservation

1. Confirm the checkout and approval scope. Record any principal approval for
   this proposal in the session artifacts before implementation; an explicit
   approval in the new session need not be requested again. Recheck the source
   and the current contracts if main has advanced.
2. Restore dependencies from the existing lock as needed, run doctor, verify
   the pinned sibling corpus and explicit vendor/postal caches, then run the
   unchanged golden command and both unchanged 1k workloads on a stable entry
   source. Preserve failed attempts and fix actual causes without weakening,
   skipping or reordering a gate. Keep the desktop checks in the baseline.
3. For each slice, freeze the bounded contract, pinned reference sections,
   hand expectations and independently authored R oracle before translator
   implementation. Choose pins that reject plausible wrong translations.
4. Add canonical reference semantics, an R twin, source/portable admission,
   rules and a registered original program gate. Compare runtime, emitted
   Python and actual CLI values, types, schema, widths, metadata, table/column/
   row order and separately qualified logical output. Test empty input,
   skipped paths, malformed portable plans and late atomic failures.
5. Give every negative CLI comparison a fresh output directory and require its
   receipt to identify the intended value/type/order/metadata/log failure.
   A nonzero exit alone is insufficient. Retain deterministic emission and
   caller-input immutability checks.
6. Preserve all 128 existing fixture registrations in order, the 92 existing
   suites, the 158 prior rule objects, previous reference bytes, oracle/gate
   files, dependency locks and existing refusal contracts. Review overlapping
   refusal tests explicitly when a newly approved profile admits a form.
   Keep `sas_semantics.py` canonical; do not recreate the retired readable
   mirror in this tree or reserve previously valid array names incidentally.
7. Require source-stable ALL VERIFIED and both unchanged workload suites for
   each accepted slice before advancing. Accept the consumer phase next,
   then each final composition separately. Re-screen external inventories
   only after the finish line; promote an external program only after its
   entire unchanged source has independent complete execution evidence.

Add no runtime dependency beyond the existing gate set. Keep receipts in
ignored telemetry. Public source, documents and eventual commit/PR text use
repository-relative paths and generic examples. The publication set must pass
the invariant linter, strict sanitization and local-path/credential review;
raw environment details and external reference bodies remain outside it.
Planning alone does not request a commit, push, PR, merge or release.

## Remaining families after this wave

This stocktake is deliberately non-exhaustive. Selected names do not partition
the full SAS reference; each row still needs its own admission inventory.

| Remaining area | Representative work | Reason to keep a separate contract |
| --- | --- | --- |
| Further character classes and encoding | NOTLOWER, NOTUPPER, NOTPUNCT, NOTXDIGIT, ANYGRAPH, ANYPRINT, control-byte and identifier classes; multilingual/K functions | Locale, byte masks, identifier options and multibyte widths |
| Pattern, comparison and phonetics | PRX family, COMPARE, COMPLEV, COMPGED, SOUNDEX, SPEDIS | Regex engine/state, edit costs, collating rules and independent witnesses |
| Broader numeric and statistical functions | EXP, LOG10, ROUNDE, percentiles, higher moments, distributions and inverses | Domain/rounding policies and specialized-profile joins; eight existing probability helpers remain reference evidence only |
| Calendar and day counts | JULDATE, DATDIF, YRDIF, holidays, additional interval methods and fractional time | Explicit year-cutoff authority, basis conventions, normalization and calendar rules |
| Dynamic conversion and metadata | INPUTN/INPUTC, PUTN/PUTC, VNAME/VTYPE/VLENGTH and related forms | Format resolution, diagnostics, descriptor inspection and schema timing |
| CALL and other stateful functions | CALL MISSING, CALL SORTN/SORTC, random streams, additional LAG/DIF consumers | Mutation order, state reset, reproducibility and side effects |
| Environment and external services | DATE/TODAY/DATETIME, SYSGET/SYMGET, file/directory and external-engine functions | Explicit supplied environment, isolation and deterministic execution |
| Composition of existing functions | General WHERE, richer Boolean conditions, deeper trees and new loop/array/BY/RETAIN/backend joins | Input-filter timing, temporary/error semantics, scheduling and profile isolation |

PROC FREQ, broader SQL, macros, FCMP, DS2 and IML remain separate source lanes.
Adding these scalar functions does not remove other constructs from a program.

## Fresh-session entry

Start with `AGENTS.md`, the [wave 3 register](FUNCTION_WAVE_3_COMPOSITION.md)
and the separate [consumer contract](SELECTION_CONSUMERS.md). The newest
`telemetry/SESSION_HANDOFF.md` entry identifies the final local source and
`telemetry/data-step-wave-3-20261113/FINAL.json`, including the failed attempts,
source-stable acceptance receipts and both workload reports. Those raw files
stay outside publication.

The implementation branch is `codex/data-step-function-wave-3`. The scope was
approved separately from wave 2, and local implementation covers all six
families, the consumer phase and both complete originals. Commit, push, PR,
merge and release require a separate principal instruction. Preserve the
working tree and existing receipts when continuing.

Use the [operating runbook](OPERATIONS.md) for dependencies and the pinned
external caches. A fresh source or publication candidate requires the unchanged
commands below, with fresh workload output paths and loopback access for the
interface suites. Cache preparation alone does not qualify an external program.

```sh
.venv/bin/python tools/prepare_vendor_sources.py
.venv/bin/python tools/prepare_postal_reference.py
.venv/bin/saschi doctor
.venv/bin/python verify_all.py
.venv/bin/python tools/run_workloads.py --output telemetry/wave3-review-01-ledger --sizes 1000
.venv/bin/python tools/run_text_workloads.py --output telemetry/wave3-review-01-text --sizes 1000
```

## Reference identity

The externally cached [SAS 9.4 Functions and CALL Routines: Reference,
Fifth Edition](https://documentation.sas.com/api/docsets/lefunctionsref/9.4/content/lefunctionsref.pdf?locale=en)
was rechecked against the wave 2 pinned identity for planning. Retain that
edition and its PDF/text hashes in each oracle's external evidence, and pin
the selected sections before implementation. Earlier first-party HTML pages
linked above are discovery aids and cross-checks; they do not replace the
pinned edition or independent executable evidence. Do not copy reference
bodies into this repository.

The pinned PDF SHA-256 is
`7ed4ed1d5ac861bfbf5ec6e99803de583549eb86a1e1662c40894dc7cc3468c5`.
If a fresh download differs, resolve the edition/content identity before
freezing new contracts. A local cache path is not part of the portable plan.
