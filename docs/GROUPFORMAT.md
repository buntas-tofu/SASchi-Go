# Numeric GROUPFORMAT and bounded detail REPORT

Status: bounded original and unchanged vendor repository/base-R evidence for
principal/maintainer review, conditional on the current source-bound full receipt. Repository logical behavior, not native
physical pages, persistent format metadata or complete REPORT support.

A separate numeric-groupformat-v1 family joins uniquely marked canonical DATE9
CARDS producers, numeric VALUE definitions, one GROUPFORMAT DATA step, bounded
REPORT and literal/reset TITLE. Exact version2 portable fields, empty initial
catalog and complete unticketed programs are required. Reuse producer contracts
through explicit composition only:1..32 columns,1000 records/80ASCII bytes,
character widths1..64, ordinary integer/date missing, bounded signed integers
and canonical DATE9. Up to8 fresh producers and8 unique format names,1group step,
2REPORTs,32title changes and64Steps. C++ and other family joins refuse.

Numeric VALUE has1..32 contiguous ordered inclusive ranges covering integer
[-2147483647,2147483647], LOW/HIGH or bounded integer endpoints, optional -< upper
exclusion, and literal outputs1..128 edge-blank-free printable nonmacro ASCII.
Names are salgrp or ordinary usr_ names ending in a nondigit. Validate unused
formats and every producer eagerly. No date endpoints, OTHER, options or callbacks.

GROUPFORMAT DATA has a fresh destination, SET of a genuine preceding producer,
BY GROUPFORMAT of one nonmissing numeric integer key, FORMAT of that same key to
a prior numeric VALUE, IF FIRST.key THEN OUTPUT, IF LAST.key THEN OUTPUT, and RUN.
Require at most500 source rows, raw-key ascending order and no chained group step.
This guarantees at most1000 output rows. Use formatted-value equality between
adjacent observations to derive FIRST/LAST, including tied raw values and adjacent
ranges with equal labels. Output twice when both predicates hold. Preserve input
rows, descriptor order and complete derived schema. The public descriptor policy
remains ordered type/length only; native persistent FORMAT attributes are not
claimed. The format is execution state for grouping/reporting, local to the job.
Preflight validates without executing grouping or rendering, propagating source
values conservatively for eager report-type checks even when a row is not selected.

REPORT requires DATA=name NOWD, COLUMN/COLUMNS of1..32 source names or unique
source=alias items, DEFINE declarations for known aliases, optional TITLE/reset,
and RUN. At least one explicit DISPLAY is required, establishing a detail row
per observation without ORDER/GROUP/ACROSS/summary/computed behavior. DEFINE has
optional DISPLAY, one FORMAT and one literal label. Formats are DATE9 on a date
column, DOLLAR12 on nonnegative integral numeric values0..999999999 or missing,
or a prior numeric VALUE on bounded integers or missing. Other fields use integer
or trimmed-character display. DOLLAR negatives/overflow, decimal rounding and
general analysis statistics remain refused. Dataset/alias references validate on
empty tables too. REPORT may read a producer or derived table, without mutation.

ascii-groupformat-report-v1 uses report_01.txt and optionally report_02.txt.
Headers JSON-quote explicit labels or lowercase aliases. There is no observation
column. Rows quote formatted text and trimmed characters, and use unformatted
integer/period tokens. DATE9 is uppercase DDMMMYYYY or period; DOLLAR12 is dollar
sign/comma-separated whole number or period, without alignment padding. This is
a named logical mapping, not physical layout. Titles persist locally. Reuse1055
header/415row/417056report byte caps,1000report rows, ASCII LF and final LF.
Actual late rendering failure must discard earlier reports and publish no
accepted partial job. Validation does not call actual grouping or renderers.

Original source-reading hand/base-R qualification fixes23 language statements,
1opaque payload,6records/7attempts,5Steps,1group step,6explicit outputs including
a duplicated one-row group,2title changes and1report. The unchanged vendor has
23language statements,1opaque payload,45records/46attempts,5Steps,1group step,
8explicit outputs,2title changes and1report. Every row and trace event is compared.
Source/LICENSE bodies and complete vendor-derived results stay external.

Admission refinement before acceptance: on a derived GROUPFORMAT table, every
REPORT alias of the formatted key requires an explicit FORMAT. Native inherited
key-display/default-width behavior remains outside this profile. This preserves
the frozen original/vendor expectations, both of which already bind every key
alias explicitly. It avoids pretending that type/length-only public descriptors
prove an unqualified inherited-format path.

## Evidence and limits

The [original source](../examples/groupformat.sas),
[hand oracle](../examples/groupformat_hand.py) and
[base-R witness](../examples/groupformat.R) were qualified before translator code.
[The original gate](../examples/verify_groupformat.py) covers19complete independent
R cases and full traces, including empty/500-row inputs,raw ties,adjacent equal
labels,calendar boundaries and one-row dual output. Runtime and emitted Python
compare complete results. ActualCLI checks typed/order/descriptor/report/log
comparisons, with nine deliberately wrong controls. The
[boundary suite](../saschi/test_groupformat.py) additionally proves strict
portable/source refusals,one actual grouping execution and a real later report
row overflow with no partial accepted publication.

[The separate vendor gate](../examples/verify_vendor_groupformat.py) binds the
unchanged3828-byte official GROUPFORMAT program, complete statement lines,
45input rows/46attempts,8explicit outputs and its whole logical report/trace.
Its immutable identity and license are in the
[benchmark manifest](vendor-benchmark-manifest.json). It is a separate conditional
vendor proof, not part of the22/56 Roku count and not a native capture.

Primary references, citation-only:

- [BY GROUPFORMAT](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000202968.htm).
- [REPORT detail/display usage](https://support.sas.com/documentation/cdl/en/proc/65145/HTML/default/n0jann0dticnpbn1woe95yuphoaz.htm).
- [DOLLAR format](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000200614.htm).

Symbolic-bound admission: LOW is only a closed lower endpoint and HIGH only a
closed upper endpoint. Qualified exclusions apply to numeric/date literal
endpoints, not symbolic extremes. This avoids interpreting a native symbolic
extreme as a finite domain value. Frozen original/vendor results are unchanged.
