# Next DATA step function wave after PR76

This wave merged through [PR77](https://github.com/buntas-tofu/SASchi-Go/pull/77)
as `044b44311816a21d0032f5c1fa2900ca02ba91eb` on 2026-11-13 after all five PR
checks passed. The [third-wave plan](NEXT_DATA_STEP_WAVE_3.md) now has its own approval and
[implementation register](FUNCTION_WAVE_3_COMPOSITION.md), covering 31 selected
names, a separate finite consumer phase and both complete originals. The
approval below still applies to this completed 29-function wave.

Status: principal-approved implementation plan, based on merged commit
`6cdaea41002c002aba49be84ecac00c05f4717f7` on 2026-11-12. The principal approved
all 29 selected functions, nested calls, IF conditions and both composition
programs: "Signing off on the full 29-function plan, including nested calls,
IF conditions, and both composition programs. Free to engage!"
All 29 selected names are implemented within six bounded families, followed
by the separate consumer profile and both original composition programs. See
the [implementation register](FUNCTION_WAVE_2_COMPOSITION.md). Acceptance
requires the matching source-bound full verification and workload receipts;
no native SAS comparison is implied by approval. The plan below retains its
merged-baseline observations and approved acceptance sequence.

Recommendation, an engineering inference: implement six more families covering
29 selected source-call names, then add a separately gated set of nested calls
and IF consumers. Finish with two original complete programs. This builds on
the preceding wave's character storage, missing-value and calendar foundations
while making the functions useful together in ordinary programs.

## Merged baseline

[PR76](https://github.com/buntas-tofu/SASchi-Go/pull/76) landed the preceding
[25-name wave](FUNCTION_WAVE_COMPOSITION.md), including six bounded profiles
and two original composition programs. Its accepted source passed 119 fixture
gates, 84 suites, 1,811 tests with zero skips, synthesis and both unchanged
1k workloads. The workloads retain 18 ledger checks and 21 text checks. All
five PR checks passed before the squash merge. These are recorded outcomes
for that source, not a fresh verification of subsequent planning edits.

The foundations at that merged baseline included:

| Area | Bounded source support already present |
| --- | --- |
| Character storage and editing | LENGTH, LENGTHN, LENGTHC, SUBSTR, REVERSE, TRIM, STRIP, CATX and COUNT |
| Prior character wave | UPCASE, LOWCASE, INDEX, FIND, SCAN, COUNTW, COMPRESS, TRANSLATE and TRANWRD |
| Missing values and summaries | MISSING, N, NMISS, CMISS, COALESCE, COALESCEC, MEAN, SUM, MIN and MAX |
| Numeric work | ABS, SIGN, CEIL, FLOOR, INT, MOD and ROUND; separate bounded arithmetic, trigonometric and SQRT/LOG profiles |
| Dates | MDY, WEEKDAY, YEAR, MONTH, DAY and selected INTCK/INTNX forms |
| Other execution models | Unsigned bitwise operations and occurrence-based LAG/DIF queues; finite week and postal callback programs under their own contracts |

These are supported slices, not blanket admission of every signature or
consumer. The previous wave requires direct assignment calls with primitive
arguments. Its WHERE, nested-call, BY, RETAIN, array and C++ joins remain held.
SQRT and LOG already execute through `binary64-math-v1`; their absence from the
general scalar registry does not make them missing functions. STD has numerical
reference evidence in `examples/verify_numstat.py`, but no scalar source
admission. Reusing that helper would require a separate row-function contract.

At the merged baseline, all 29 selected candidate forms below were absent from
the general scalar registry and blocked by compile-only probes. The probes
also confirmed refusal of `UPCASE(STRIP(txt))` and a MISSING call in an IF
comparison, while direct SQRT and LOG controls compiled. Those observations
apply to the exact probed forms; they are not an exhaustive signature census.

The [capability manifest](capability-manifest.json) still has a null
functions/CALL universe. Keep that denominator unchanged. Maintain a selected
admission matrix distinguishing reference helpers, specialized profiles,
general source calls, portable plans and consumers. A complete edition-specific
reference index is separate work.

## Proposed family order

The order and expected usefulness are engineering judgments based on reuse and
contract isolation. They are not measured corpus frequencies or projected
external-program completions. Each row begins with direct assignment and a
bounded argument set; consumer expansion follows separately.

| Order | Family and names | Contract questions to settle before implementation | Original program witness |
| --- | --- | --- | --- |
| 1 | Whitespace and alignment: LEFT, RIGHT, COMPBL, TRIMN | Printable ASCII and stored widths; leading, trailing and repeated blanks; TRIMN's zero-length temporary versus padded assignment | Normalize padded labels while retaining exact descriptors and output bytes |
| 2 | Concatenation: CAT, CATS, CATT | Character inputs first; distinct blank handling; inferred destination widths, existing destinations and insufficient-buffer refusal | Construct record identifiers and distinguish all three functions from CATX and the concatenation operator |
| 3 | Character validation: VERIFY, ANYALPHA, ANYDIGIT, ANYALNUM, ANYSPACE, NOTDIGIT | Position results rather than Boolean results; ASCII classes, padding, no match and empty input; start arguments only where the function defines them | Classify supplied identifiers and retain the precise position of each accepted or rejected character |
| 4 | Positional search and extraction: FINDC, FINDW, INDEXC, INDEXW, SUBSTRN | Explicit character/delimiter sets; word boundaries, search direction and a qualified modifier subset; SUBSTRN's clipping and zero-length behavior | Parse mixed label/code records with exact search positions and extracted stored values |
| 5 | Row statistics: MEDIAN, RANGE, VAR, STD | Bounded numeric arguments and ordinary missing first; all-missing and singleton rows; variance divisor and independently qualified rounding/tolerances | Reconcile complete measurement rows and expose population-versus-sample and missing-value mistakes |
| 6 | Calendar and datetime components: QTR, DHMS, DATEPART, TIMEPART, HOUR, MINUTE, SECOND | Date days versus datetime seconds; accepted domains for each function, midnight, negative epoch values, leap days and fractional-second policy | Construct supplied timestamps, recover their components and compare complete calendar summaries |

The counts are 4 + 3 + 6 + 5 + 4 + 7 = 29 distinct names. Admission may split a
family into several accepted slices if widths, numerical policy or oracle
qualification differ. These names are planning targets, not 29 completed gates
or entirely new reference semantics.

Character work starts with printable ASCII and explicit delimiters rather than
host locale defaults. Numeric-to-character CAT conversion and general BEST
formatting remain separate. FINDW and SCAN must not share a word parser merely
because their interfaces look related. Row statistics need independent formulas
and declared numerical comparison rules before implementation; reference-level
STD evidence cannot supply source scheduling, typing or missing-state proof.

Datetime work uses supplied values and integer epoch arithmetic first. Freeze
pre-1960 and midnight behavior before accepting negative datetime values. Hold
fractional seconds, out-of-range component normalization and wider domains until
their individual contracts are qualified. No system clock or timezone service
is needed for this family.

## Nested calls and IF consumers

Treat this as its own acceptance phase after the six families. Freeze a finite
typed admission list and nesting/resource bounds before changing the parser,
width analysis, runtime or portable validator.

The proposed initial forms are character chains such as
`UPCASE(COMPBL(STRIP(label)))`, identifier construction such as
`CATS(SUBSTRN(code,1,3),'-',LOWCASE(tag))`, and IF comparisons against numeric
results from the selected validators and MISSING with primitive arguments.
Temporary character length must remain distinct from the width of a stored
variable. Qualify literal arguments even on empty or skipped paths, preserve
reached-only dynamic evaluation and retain atomic failure.

Add an independent original program for these consumers. General WHERE needs
its own input-filter timing contract and stays outside this wave, along with
new array, BY, RETAIN, C++, SQL and specialized-profile joins. A new function
must not silently broaden an older profile or reserve an existing array name.

## Complete program finish line

1. **Record cleaning and validation.** Combine the previous character wave,
   whitespace handling, CAT functions, validation and positional extraction.
   Exercise the admitted nested calls and IF decisions over padded, blank,
   malformed and valid records. Compare every table, column, descriptor, row
   and separately characterized logical record.
2. **Timestamp and measurement reconciliation.** Combine supplied datetime
   construction/decomposition, existing date intervals, missing handling and
   row statistics through stored values. Cover epoch boundaries, month/quarter
   transitions and missing or undersized statistical samples. Keep formatted
   output within an existing separately characterized reporting contract.

Each complete program gets an independently frozen hand/base-R oracle before
its composition implementation. Six family witnesses, a distinct consumer
witness and these two final programs provide at least nine original program
contracts; actual gate and suite counts follow the accepted splits.

## Acceptance sequence

1. Confirm the current mainline, gate environment and external cache identities.
   Run the unchanged golden command and both workloads for a stable entry
   source. Preserve failed attempts and resolve their actual causes.
2. Freeze each bounded contract, reference edition/page identities, hand pins
   and independently authored R twin before implementing that slice. Include
   cases that distinguish plausible wrong translations.
3. Add source, portable-plan and complete-program comparisons through runtime,
   emitted Python and the actual CLI. Check values, types, schema/column/row
   order, widths, metadata and logical output. Include empty inputs, skipped
   branches, invalid dynamic values and late atomic failures.
4. Give every negative CLI comparator a fresh output directory and require a
   receipt identifying the intended dataset or log comparison failure. A
   nonzero exit alone is insufficient. Keep deterministic emission and caller
   input immutability checks.
5. Retain existing rule objects, prior evidence and refusal tests. Keep
   `sas_semantics.py` canonical, add the required R twins and gates, and add
   no runtime dependency beyond the existing gate set.
6. Require source-stable ALL VERIFIED and both unchanged workload suites for
   each accepted slice before advancing. Protect the existing desktop suites.
   Re-screen external inventories only after the final composition passes;
   promote a program only after its entire unchanged source has its own proof.

Keep receipts under ignored `telemetry/`. Apply the invariant linter and
sanitization gate to publishable content. Public code, documentation, commit/PR
text and attachments use repository-relative paths and generic examples;
host details, credentials and raw receipts remain outside publication.

## Families after this wave

This is a non-exhaustive backlog, not a partition of the full SAS reference.

| Area | Representative remaining work | Contract that drives the next decision |
| --- | --- | --- |
| Richer text | PROPCASE, QUOTE, DEQUOTE, remaining ANY/NOT classes, COUNTC, TRANSTRN, PRX functions, comparison and phonetic functions | Locale/encoding, quote rules, regex engine behavior and temporary widths |
| Selection and additional summaries | IFN, IFC, CHOOSEN, CHOOSEC, WHICHN, WHICHC, LARGEST, SMALLEST, CSS, USS and percentiles | Argument evaluation, tie/missing behavior, rank bounds and numerical policy |
| Further numeric functions | EXP, LOG10, zero-fuzz rounding/remainder variants and special/probability functions | Overflow/underflow, fuzz, tolerances and reference-only helpers versus source execution |
| Broader calendars | HMS, YYQ, DATEJUL, JULDATE, DATDIF, YRDIF, holidays and additional interval methods | Year cutoffs, day-count conventions, normalization and separate interval semantics |
| Conversion and metadata | INPUTN, INPUTC, PUTN, PUTC, VNAME/VTYPE/VLENGTH families | Dynamic format resolution, descriptors and conversion/diagnostic state |
| CALL and stateful work | CALL MISSING, CALL SORTN/SORTC, random streams and additional queue consumers | Side effects, evaluation order, state reset and reproducibility |
| Environment and external services | Session clocks, SYSGET/SYMGET, file/directory and external-engine functions | Explicit environment authority, reproducibility and isolation from host details |

PROC FREQ, broader SQL, macros, general FCMP, DS2 and IML remain separate work
lanes. Their presence in a program is not resolved by adding scalar functions.

## Behavioral reference

Use the [SAS 9.4 Functions and CALL Routines Reference, Fifth Edition](https://documentation.sas.com/api/docsets/lefunctionsref/9.4/content/lefunctionsref.pdf?locale=en)
and the selected per-function sections when freezing contracts. Retain its
edition and content hash externally with each oracle's evidence; do not copy
reference bodies into this repository. The earlier
[function categories](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p0w6napahk6x0an0z2dzozh2ouzm.htm)
and [character return-width discussion](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p07c8e0ktns1c7n1vtowjev5g724.htm)
are discovery aids, not substitutes for the selected SAS 9.4 contract or
independent executable evidence.
