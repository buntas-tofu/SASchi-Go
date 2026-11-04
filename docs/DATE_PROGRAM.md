# Canonical DATE9 and nested date logical reports

Status: bounded original repository/base-R evidence for principal/maintainer use,
conditional on the current source-bound full verification receipt. This is source
execution of original fixtures, not acceptance of the held vendor target or a
live-SAS comparison. The principal selected valid-width work while retaining H11.

DS-080, DS-081 and ST-025 define a separate `date-format-fields-v1` family.
Selection requires an actual DATA block with a colon-modified DATE9 INPUT.
No older profile acquires date syntax implicitly. An empty initial catalog,
version 2, exact portable fields and a complete unticketed program are required.
The family permits up to64 Steps,8 fresh DATA destinations,8 unique local format
names,32 literal/reset TITLEs and2 PRINTs. C++ refuses this family.

DATA contains only its header, INFILE CARDS, one INPUT, CARDS, opaque physical
records and RUN. Declare1..32 unique ordinary names as bare signed integer fields,
colon:$w. character fields of width1..64, or colon:DATE9 dates. At least one date
column is required. Integers have magnitude at most2147483647; periods mean
ordinary numeric/date missing. Characters must fit their storage width and
cannot be a period. Each of0..1000 unquoted printable ASCII records has at most80
bytes and exactly one complete field set. Short/extra records, FLOWOVER, quoted
input, controls, truncation and invalid-data recovery remain refused.

DATE9 accepts canonical DDMMMYYYY in the calendar1753..3999, with case-insensitive
English month abbreviations. Values are numeric days since1960-01-01. Descriptors
retain only ordered type and length, numbers8 and the declared character width.
This descriptor policy does not claim persisted native informat/format metadata.
The [reference foundations](DATE_FOUNDATIONS.md) separately qualify date decoding
and complete English date fields.

PROC FORMAT contains one numeric VALUE and RUN. Its unique name is `cohort`,
`benefit` or an ordinary `usr_` name ending in a nondigit. This conservative
namespace does not enumerate builtins. Define1..32 ordered contiguous inclusive
ranges covering the qualified calendar, using LOW/HIGH or four-digit date
literals. Each output is a nonmacro printable ASCII literal of1..128 bytes without
edge blanks, or nested WEEKDATE29..37/WORDDATE18..32. Two-digit year literals,
gaps, overlaps, missing ranges, recursion, options and unsupported widths refuse.
Validation includes unused definitions and empty tables.

PROC PRINT has only DATA=name, one FORMAT binding of unique DATE9 columns to a
preceding custom definition, and RUN. Existing literal TITLE and bare reset apply.
The logical contract `ascii-date-fields-v1` emits `print_01.txt` and optionally
`print_02.txt`, retaining earlier snapshots. It adds an observation column, quotes
formatted date strings and right-trimmed stored characters with JSON, and renders
unformatted numbers as integers or periods. A missing formatted date is a quoted
period outside LOW/HIGH dispatch. Nested field alignment blanks are removed as
an explicit logical mapping. This does not establish physical SAS layout or a
custom format's native DEFAULT width. Storage remains independent of display.

Existing1055-byte header,415-byte row and417056-byte report limits apply.
Preflight validates definitions, descriptors and every input record without
rendering reports. Later rendering or comparison failure publishes no accepted
partial job or report files. Formats and titles start fresh for each job.

The [original source fixture](../examples/date_profile.sas),
[hand expectation](../examples/date_profile_expected.json) and
[base-R witness](../examples/date_profile.R) were qualified before the source
executor. Their byte identities are pinned by the
[whole-program gate](../examples/verify_date_profile.py). It compares18 complete
R cases, including empty input, missing dates, range/calendar endpoints and1000
records, through runtime and emitted Python. Actual CLI comparisons cover the
complete ordered typed table, log and exact report bytes. Ten deliberately wrong
controls distinguish epochs, missing storage, descriptor/row order, date types,
range selection, weekday names, alignment, final LF and report artifact sets.
The [boundary suite](../saschi/test_date_program.py) checks source/portable refusals,
limits, state reset, C++ refusal, preserved old rule/capability objects and a late
second-report failure after an earlier report rendered successfully.

The original Using Nested Formats source still requests WEEKDATE50. That request
exceeds the documented maximum37, and native handling remains unresolved.
[H11](SOURCE_HOLDS.md) is open. No source repair, native behavior inference or new
vendor proof is included. FMT-02 through FMT-06 remain queued in the
[selected order](FORMAT_CANDIDATE_PLAN.md); human interface testing remains staged.

Symbolic-bound admission: LOW is only a closed lower endpoint and HIGH only a
closed upper endpoint. Qualified exclusions apply to numeric/date literal
endpoints, not symbolic extremes. This avoids interpreting a native symbolic
extreme as a finite domain value. Frozen original/vendor results are unchanged.
