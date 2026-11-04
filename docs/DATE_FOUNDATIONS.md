# FMT-01 date reference foundations

Status: bounded original reference-helper evidence for principal/maintainer use.
The current full receipt decides acceptance. These helpers alone do not admit source forms. The separate
[date source profile](DATE_PROGRAM.md) defines DATE9, date literal, VALUE, nested
format and PRINT admission. No whole-vendor
proof or live-SAS validation is claimed. FMT-01's original target remains on H11.

`saschi.date_foundations.sas_input_date9` accepts exact ASCII DDMMMYYYY tokens,
case-insensitive English month abbreviations and valid Gregorian dates in
1753 through 3999. A period returns ordinary missing. Other types, blanks,
surrounding whitespace, separators, shorter forms, two-digit years and invalid
dates refuse. This is a canonical subset of the DATE informat, not its full
vocabulary, YEARCUTOFF behavior or invalid-input recovery. Results are integer
days since 1960-01-01, or None for ordinary missing.

`saschi.date_foundations.sas_date_field` accepts integral finite numeric SAS days
in that same calendar, or ordinary missing. WEEKDATE widths 29 through 37 and
WORDDATE widths 18 through 32 render complete English names, a decimal day and
four-digit year, right-aligned with ASCII blanks. WEEKDATE includes the weekday.
Missing is a right-aligned period. Width is an integer excluding booleans; names
are ASCII and case-insensitive. Abbreviated widths, wider fields, coercion, tagged
missing and other formats require separate work. Width validation also applies
to missing values.

The original [Python gate](../examples/verify_date_foundations.py) and
[base-R witness](../examples/date_foundations.R) cover hand pins, separate
Gregorian ordinal calculations, C-locale date rendering, type checks and known
wrong epoch/weekday/alignment controls. Expectations were qualified before helper
implementation. The existing semantics reference and plain-text mirror remain
byte-for-byte unchanged; the new helper module is separately gated.

The unchanged original Using Nested Formats source requests WEEKDATE50. The
SAS 9.4 references document widths 3 through 37, so the helpers refuse width 50.
This refusal is a bounded repository policy and does not establish native
handling of that nested request. H11 requires independent resolution; no clamping,
implicit correction or whole-program expected report has been manufactured.
See [the source holds](SOURCE_HOLDS.md) and [ordered plan](FORMAT_CANDIDATE_PLAN.md).

Primary references, citation-only:

- [DATE informat](https://support.sas.com/documentation/cdl/en/leforinforref/63324/HTML/default/p106m1k307c61in1hyfymetc7uh3.htm).
- [WEEKDATE, SAS 9.4](https://support.sas.com/documentation/cdl/en/leforinforref/64790/HTML/default/p1rib2891qxd4yn18x1myfkmxeet.htm).
- [Current SAS 9.4 format reference](https://documentation.sas.com/api/docsets/leforinforref/9.4/content/leforinforref.pdf).
