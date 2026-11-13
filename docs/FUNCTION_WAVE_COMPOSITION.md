# DATA step function wave evidence

Status: implementation and independent hand/base-R integration evidence for
maintainer review. Final acceptance requires the matching full verification and
workload receipts. No native SAS comparison,release or publication is implied.

The approved wave covers25 named functions through six bounded source profiles.
Each profile has an original complete program,hand expectations,an independent
R twin and a registered gate. Bounds and held forms remain part of each contract.

| Rule | Profile | Functions | Gate |
| --- | --- | --- | --- |
| DS-096 | [Case/search](CASE_SEARCH.md) | UPCASE,LOWCASE,INDEX,FIND | `examples/verify_case_search.py` |
| DS-097 | [Word parsing](WORD_FUNCTIONS.md) | SCAN,COUNTW | `examples/verify_word_functions.py` |
| DS-098 | [Rewriting](CHARACTER_REWRITING.md) | COMPRESS,TRANSLATE,TRANWRD | `examples/verify_character_rewriting.py` |
| DS-099 | [Missing/summary](MISSING_SUMMARIES.md) | MISSING,N,NMISS,CMISS,COALESCE,COALESCEC,MEAN | `examples/verify_missing_summaries.py` |
| DS-100 | [Numeric](NUMERIC_HELPERS.md) | ABS,SIGN,CEIL,FLOOR | `examples/verify_numeric_helpers.py` |
| DS-101 | [Calendar](CALENDAR_INTERVALS.md) | YEAR,MONTH,DAY,INTCK,INTNX | `examples/verify_calendar_intervals.py` |

These are25 selected names,not25 entirely new reference semantics or a percentage
of SAS. The capability manifest's functions/CALL universe remains unenumerated.
Existing source,reference and specialized-profile boundaries remain distinct.

## Complete composition programs

The final two programs add evidence using the admitted stored-value data flow;
they introduce no additional function or consumer admission.

| Original program | Independent witness | Required comparison |
| --- | --- | --- |
| `examples/character_composition_capture.sas`,18statements | `examples/character_composition.R` | Case/search,word parsing,rewriting and missing handling; all tables,descriptors,rows and three logical records |
| `examples/numeric_calendar_composition_capture.sas`,21statements | `examples/numeric_calendar_composition.R` | Summaries,numeric fuzz and calendar intervals; all tables,descriptors,rows and six logical records |

The numeric calendar fixture has a distinct filename. The earlier multiplication
composition retains its original source. Each new program has independently
frozen hand expectations and30generated complete R/runtime/emitted catalogs.
The gates exercise actual CLI success and six receipt-verified negative controls:
values,types,row order,column order,metadata and logical records. Every negative
control uses a fresh output directory and requires the relevant comparison to
fail in its receipt. Earlier exitcode-only claims are withdrawn in the
[verification correction](NEXT_FUNCTION_WAVE.md#verification-history-correction).

The composition suite additionally checks empty input,caller-input immutability,
family provenance,deterministic plan/emission hashes across three Python hash
seeds and held WHERE,RETAIN,array,nested-call and C++ contexts. Late invalid rows
are exercised separately for all six families through runtime,emitted Python
and actual CLI. A runtime failure must publish no accepted or observed result;
emitted execution must produce no partial logical output. Valid comparison
failures may retain a complete observed result for diagnosis.

## Acceptance and limits

The golden command now registers137fixtures,101suites and one synthesis runner,
including the subsequent approved continuation slices.
Registration counts are not passing outcomes. A source-stable ALL VERIFIED
receipt and matching18ledger/21text workload checks decide acceptance. Receipts
regenerate under ignored `telemetry/`; local filesystem and environment details
are excluded from the publication set.

The original103888-byte semantics reference prefix remains hash-pinned. Approved
helpers are appended,and the current canonical reference is hash-pinned in full.
`sas_semantics.py` remains the single reference in this tree; readable twins
belong in the external reference home under the current repository policy.
Earlier rule objects and golden-runner order are retained,including the four
existing desktop and saved-evidence suites.

This wave adds eight original complete-program gates. It does not add unchanged
official-example or Roku completions. Live SAS validation,broader modifiers,
nested temporary consumers,additional numeric domains,calendar methods and
cross-profile forms remain separate work.

The [second function wave](FUNCTION_WAVE_2_COMPOSITION.md) supplies separate
bounded evidence for 29 further selected names, typed consumers and two more
original programs. The 25-name register above remains its own historical scope.
