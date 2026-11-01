# Explicit bitwise output and job-local informat reports

Status: Bounded repository/base-R contracts for maintainer review, conditional
on the current source-bound full receipt. No live SAS, complete language or
physical SAS log/page-layout equivalence. Bounds and logical text spellings below
are explicit project policies, rather than inferred native output guarantees.

The three implementation lanes have separate gates and share two complete-source
targets. Existing source profiles, semantic helpers and default receipt fields
remain unchanged.

## Explicit bitwise diagnostic record

`--output-contract bitwise-put-all-67-v1` selects DS-070 for inspect, translate and
run. The equivalent Python keyword is `output_contract`. One scalar DATA _NULL_
step assigns finite unsigned32 integers, uses at least one existing bitwise
function and ends with PUT _ALL_. The new portable family is `bitwise_data`,
with one final `put_all_67` operation. The selected source is limited to64
assignments,16 variables,128 expression nodes and nesting depth32.

The exact record preserves source spelling and PDV order, integer values and
the existing automatic-variable tail with its trailing space. Its cap is67
ASCII bytes excluding LF. The old default PUT _ALL_ helper stays at64 bytes;
the unchanged bitwise corpus program still refuses under that default. Its
complete-program proof requires the explicit new selection. C++ refuses this
family. `--expect-log` optionally compares an ordered JSON list of logical log
records, including trailing spaces. Only requested comparisons add the named
`ascii-log-records-v1` receipt fields. Emitted stdout's final LF is checked
separately from the logical records.

## Numeric literal definitions and physical pointer input

DS-071 accepts bare PROC FORMAT, one numeric INVALUE and explicit RUN. Definitions
are local to one job. At most8 unique custom names are accepted: `eval` or an
ordinary `usr_` name, at most31 characters and ending in a nondigit. This namespace
is deliberately conservative. It does not enumerate built-in informats.

Each definition has1..32 exact-case printable ASCII literal keys of1..32 bytes,
without outer spaces, quotes or macro markers, mapped to integers[-1000,1000].
The longest key determines the read width. Lookup removes right padding only.
Unmapped nonblank numeric tokens use the unchanged exact numeric converter and
must be integral within the same bound. Blank, missing and invalid values refuse.
The SAS INVALUE reference explains the default width; the official example
documents numeric fallback. These references explain behavior, rather than
providing a live execution golden.

DS-072 requires a fresh named DATA destination, one INPUT, DATALINES, opaque
physical cards, an unindented standalone semicolon and RUN. The first field is
simple character list input with storage8. Every later field has an explicit
absolute pointer@1..80 and either `$w.` with width1..32 or a preceding custom
numeric definition. At least one custom read is required. Limits are32 fields,
1000 records and80 printable ASCII bytes per card, without quotes or semicolons.
Every fixed span must physically exist. There is no cross-record read or padding
past the card. `$w.` removes leading blanks, turns a period-only field into blank
and pads storage. A period-only first simple-list token conservatively refuses.
Descriptors contain only type and length, with no persisted labels or informats.

## Logical reports and title state

ST-021 accepts PROC PRINT DATA=name LABEL NOOBS, one nonempty LABEL statement and
RUN. Labels affect that procedure only. Headers JSON-quote each supplied label
or lowercase column name. Rows JSON-quote characters after removing right storage
padding and render numeric integers or periods. There is no observation column.

ST-022 accepts PROC MEANS DATA=name and RUN without other options. It analyzes all
1..8 numeric columns in descriptor order, with N, MEAN, sample STD, MIN and MAX.
There is no statistics output dataset. Mean uses exact rational sufficient
statistics; STD uses exact rational sample variance and integer-square midpoint
comparison. Both render fixed8 decimals with half-away rounding and normalized
negative zero. Missing values are excluded. Empty statistics and STD below N2
are periods. The independent R witness uses pairwise differences and separate
decimal-limb comparisons for rounding boundaries.

ST-023 uses distinct `informat_title` Steps. Literal TITLE sets local state and
bare TITLE resets it. The state persists into both report procedures and starts
fresh for every run. Literals contain1..128 printable ASCII bytes, at least one
nonspace and no macro markers.

The report contract is `ascii-informat-reports-v1`, with `print_01.txt` and
`means_01.txt`, at most one each. Exact comparison checks the entire basename set
and UTF8 bytes. Independent limits are1000 rows,32 columns,1055 header bytes,
415 data-record bytes and417056 total bytes per report. They do not promise the
Cartesian product of every cap. Final LF is required. A complete formatted
program has at most64 Steps,8 definitions,8 fresh producers and32 titles, with
empty initial catalog and definitions. All values and descriptors are validated
before row shortcuts. Later rendering failures publish no partial accepted
datasets or report files.

## Complete-source evidence and boundaries

The unchanged469-byte Roku bitwise program has a separate explicit-contract
whole-file gate. The second vendor benchmark is the unchanged1802-byte official
INVALUE example at the commit and content pins in
[the vendor manifest](vendor-benchmark-manifest.json). Its eight rows exercise
literal lookup, numeric fallback, leading-zero character IDs, repeated absolute
pointers, procedure-local labels and title persistence into both reports. The
hand and independent source-reading R oracle agree on complete datasets, both
report artifacts,13 language statements plus one opaque payload and36 events.
Whole runtime, emitted Python and actual CLI comparisons include wrong expected
values, descriptors, reports and an actual late-rendering atomicity control.

Vendor bodies and complete derived vendor results remain outside this repository.
Prepare their pinned external cache before offline verification:

```sh
python tools/prepare_vendor_sources.py
python verify_all.py
```

These gates do not promote DATA-step LABEL, general PROC FORMAT/INPUT/MEANS,
quoted CSV, missing-data recovery, physical ODS layout or an unenumerated reference
universe. Source references are recorded per rule in the rulebook.
