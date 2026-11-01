# Bounded grouped statistics and logical reports

Status: ST-017/018 repository and independent base-R source evidence for maintainer
review. The arithmetic, metadata and report layout are named repository policies,
not live SAS capture, native procedure accumulation, ODS or physical page fidelity.
The approved continuation and decisions live under
`telemetry/cluster-d1b-d4b-20261031/`. DECISION-03 assigns new unused rule IDs;
the earlier ST-001..016 objects remain unchanged.

## Source profile and existing SORT

Existing ascending `PROC SORT DATA=name [OUT=name] [NODUPKEY]` is reused without
changing its parser, helper, runtime or serialized contract. Source DESCENDING,
NOTSORTED and implicit last-dataset SORT remain outside that earlier profile.
The new source forms require every semicolon, fixed statement order and explicit
RUN, with no ignored options or clauses:

```sas
proc means data=ordered noprint vardef=df;
  by g;
  var x;
  output out=summary n=nobs nmiss=nmissing mean=avg var=variance / noinherit;
run;
proc print data=summary noobs;
  var g _type_ _freq_ nobs nmissing avg variance;
run;
```

MEANS requires one distinct BY and analysis variable, each ordinary numeric with
no nonempty attached format. Its four statistics must occur once each, with unique
explicit destination names outside BY, `_TYPE_` and `_FREQ_`. Their source order
is the generated statistic-column order. The output dataset must be new, including
when an existing destination has no rows. PRINT requires one explicit ordered list
of1..32 unique unformatted numeric columns. Empty format attributes are valid.
Only one PRINT may occur in a complete program, across all intervening profiles.
The existing whole-program one-FILE limit also survives these procedure joins.
Comments, literals and opaque inline data do not select procedure code.

Every new procedure Step has the existing exact field set and integer version2.
`proc_means` has one same-kind operation marked `grouped-integer-means-df-v1`;
`proc_print` has one same-kind operation marked `numeric-print-v1`. Strict portable
validation runs independently of compilation, including source-line positions and
empty inputs. Older Step kinds refuse hidden new procedure operations. No new
function registration, numeric expression grammar or earlier marker is added.
The procedure source statement cap is16384 canonical ASCII characters, separate
from selected-data and report bounds.

## Primary SAS facts and bounded numerical policy

SAS defines BY processing as separate statistics on sorted or appropriately indexed
groups. NOTSORTED changes this requirement and remains deferred here. See the
[MEANS BY reference](https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a000146730.htm).
Missing analysis values are excluded independently. Missing BY values form their
own group. `_FREQ_` counts group observations, whereas N counts nonmissing analysis
values. Without CLASS, `_TYPE_` is zero. See
[MEANS results](https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a002473538.htm).

The source explicitly selects NOPRINT and VARDEF=DF. SAS documents DF as the
`n-1` divisor and NOPRINT for creating an output dataset without the displayed
analysis. See [MEANS options](https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a000146729.htm).
NOINHERIT prevents statistics from inheriting the analysis variable's label and
format; it does not discard the BY descriptor. See
[MEANS OUTPUT](https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a000146734.htm).

Repository policy: selected MEANS values are ordinary missing or integers of
magnitude at most1000, with at most1000 input rows. Every selected descriptor and
value validates eagerly before grouping. Missing BY forms the first group;
nonmissing groups ascend. All remaining imported catalog content retains prior
generic normalization and preservation, including unselected fractional numbers,
character encodings and tagged missing values.

For each group, n counts nonmissing analysis values, S is their integer sum and
Q is their integer squared sum. S has magnitude at most1e6, Q at most1e9 and
both nQ and S squared at most1e12. These intermediate integers are exact in base-R
binary64 as well as Python integer arithmetic. The implementation converts the
exact rational S/n and `(nQ-S*S)/(n*(n-1))` once to binary64. The R oracle computes
its own exact-integer sufficient statistics and divisions. Missing mean at n0,
missing sample variance at n0/1, N0 and NMISS counts are explicit pins. This is a
bounded mathematical procedure policy, not a native SAS algorithm or parallel
reduction claim. Fractional MEANS inputs and STD/SQRT remain deferred.

Output schema order is BY, `_type_`, `_freq_`, then explicit statistics in source
order. BY descriptor representation, label, empty format and key order are cloned
after generic normalization. Generated descriptors are fresh
`{"type":"number","length":8}` without label/format keys. The new table has only
schema and rows; source table labels/encoding are not copied. This canonical typed
representation is repository metadata policy. Empty BY input has no groups and
produces zero output rows with the full schema, an explicitly recorded inference.

## Logical PRINT and atomic artifact comparison

SAS NOOBS suppresses observation numbers, VAR selects column order and, without
LABEL, variable names supply headings. See the
[PRINT statement](https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a002291718.htm)
and [PRINT VAR reference](https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a000064125.htm).
The following logical rendering is repository policy, not that physical layout.

`numeric-space-fixed12-v1` returns one optional result channel:

```json
{"reports":{"print.txt":"x y\n1 .\n"}}
```

The header uses normalized lowercase selected names, never labels. Header and
rows join fields with one ASCII space, with no edge blanks and LF after every
record. Empty input still returns the header and final LF. Each scalar uses the
unchanged binary64 numeric validator and fixed-decimal renderer, removing exactly
its one trailing separator. Existing magnitude, normal-value, carry and exact
16ULP midpoint refusals remain. The report has its own combined width: at most
1055 header bytes,415 body bytes,1001 LF records and417056 total bytes. PRINT does
not inherit the combined64-column DATA PUT limit. Selected values and descriptors
are validated even when rows are empty or later execution fails.

No-PRINT programs keep their old result and receipt shapes. `--expect` retains its
existing exact typed dataset comparison. `--expect-reports` independently compares
the entire basename set and exact UTF8 bytes, under
`exact-basename-set-utf8-bytes-v1`; expected JSON is bounded to one MiB. Wrong safe
basenames, headings, whitespace, values, multiplicity and final newlines cannot
normalize into acceptance. DATA logs and CSV exports remain separate channels.

Runtime and emitted Python return private buffers. Accepted CLI jobs stage
`reports/print.txt` beside result, exports and receipt under the existing single
atomic rename. Failed execution, dataset/report/export comparison, report write or
rename cannot publish accepted report/export files. An observed diagnostic JSON
may describe rejected buffers; it is not accepted publication.

## Independent evidence and boundaries

The original `examples/procedures_capture.sas` has11 language statements. Its
12 supplied rows sort stably, form6 groups and create6 summary rows. The hand/R/
runtime/emitted schedule has19 events and produces128 report bytes,7 records
including the header. It covers a missing BY group, all-missing analysis group,
singleton sample variance, tied values, missing N versus `_FREQ_`, descriptor
preservation and fresh NOINHERIT metadata. No external corpus source is copied or
new whole-corpus proof claimed.

Separate `proc-means` and `proc-print` gates exercise10/8 hand cases,160 generated
full-source/R schedules each,37/27 shared source/input refusals and6 actual wrong
CLI dataset/report comparisons each. The independent R program parses complete
SORT/MEANS/PRINT source, computes group sufficient statistics, output descriptors,
report text and event accounting without reading Python plans. Its scanner and
generic catalog wire reuse earlier first-party routines. An independently authored
binary-digit calculation implements the declared decimal-midpoint boundary.
The exact417056-byte report and header-only empty report are positive witnesses.
The source suite also attacks malformed portable plans, static/empty metadata,
cycles, domain/resource boundaries, profile joins and late failures.

Procedure-context catalog routing reads source, not Plan internals. Only exact
recognized MEANS/PRINT headers establish it; DATA, any PROC and RUN reset it.
VAR/OUTPUT are not globally rerouted, and the broader ST-001 route remains.
Earlier rules,149 helpers/reference bytes,19 accepted serialized examples and all
existing gates remain separate preserved evidence. The procedure reference
universe remains unenumerated, so these gates do not create a SAS coverage fraction.

CLASS/TYPES/WAYS, WEIGHT/FREQ, other statistics/VARDEF values, quantiles, RNG,
character or formatted PRINT, labels as headings, ODS, pages, arbitrary report
filenames/paths and native physical logs remain deferred. No D1 fractional
statistics composition is implied. The cumulative-SD and fivenum corpus programs
retain additional source, indexed-input, STD/VARDEF=N, implicit-SORT, quantile or
random-stream blockers; this slice promises neither whole-file unlock.
