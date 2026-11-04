# Date PICTURE and ordered PRINT fields

Status: bounded source/runtime repository/base-R evidence for maintainer review,
conditional on the current source-bound full receipt. The unchanged official
example has its own complete-program gate. No live SAS, physical layout, native
DEFAULT width or unspecified session-casing equivalence is claimed.

DS-082, DS-083 and ST-026 implement the separate `picture-date-fields-v1` family.
It reuses canonical DATE9 CARDS ingestion through unique `picture_data` Steps,
then joins `date_picture`, `picture_print` and existing literal/reset TITLE.
The prior [date profile](DATE_PROGRAM.md) keeps its own admission and shapes.
Exact version2 fields, empty initial catalog and an unticketed complete program
are required. Bounds are64 Steps,8 fresh producers,8 unique definitions,32 title
changes including inside PRINT, and2 PRINTs. C++ and unqualified joins refuse.

DATE9/character/integer records, storage, calendar and refusal bounds are inherited
only through this explicit new composition:1..32 columns,0..1000 complete unquoted
ASCII records of at most80 bytes, character widths1..64 and signed integers of
magnitude at most2147483647. Dates use English DDMMMYYYY in1753..3999, or ordinary
missing, with numeric SAS-epoch storage and type/length descriptors. All producers
are validated eagerly, including unused and empty paths.

PROC FORMAT has exactly one PICTURE and RUN. Names are `hirefmt`, `mrg` or ordinary
`usr_` names ending in a nondigit. Define1..32 ordered nonoverlapping calendar
ranges, with LOW/HIGH or four-digit date endpoints. `-<` excludes an upper endpoint.
Optional OTHER is last and covers gaps and missing. Without OTHER, cover the full
qualified calendar. Each single-quoted printable ASCII template has1..40 bytes;
maximal expansion is128 bytes, even for unused definitions. DATATYPE=DATE enables
only `%d`, `%0d`, `%b`, `%B`, `%Y` and `%%`. English C-locale title-case month names
are explicit repository policy. Other date/time directives and macro text refuse.
Non-date literal alternatives contain no digit selectors, directives or macro
markers. A missing date without OTHER renders ERROR; an OTHER literal can instead
cover missing. [SAS PICTURE reference](https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a002473467.htm).

PRINT requires DATA=name, optional `(OBS=N)` for N1..1000, a unique ordered VAR
list, one FORMAT binding of selected DATE9 columns to a preceding definition,
optional literal/reset TITLE, and RUN. VAR affects report order only; OBS takes
a prefix without mutating stored rows. Procedure TITLE changes persist locally.
`ascii-picture-date-v1` artifacts are `print_01.txt` and optionally `print_02.txt`.
Rows use observation numbers, JSON-quoted formatted text and right-trimmed stored
characters, plus integer/period unformatted numbers. Remove template trailing
padding as a named logical mapping. This is separate from native field width or
physical page output. Retain1055-byte header,415-byte row and417056-byte report
caps. Preflight does not render. Late failure publishes no accepted partial job.

The [original fixture](../examples/picture_dates.sas),
[hand oracle](../examples/picture_dates_hand.py) and
[base-R witness](../examples/picture_dates.R) were qualified before the translator.
The [original gate](../examples/verify_picture_dates.py) covers17 complete R cases,
including empty/1000-row inputs, missing dates, calendar/range boundaries, VAR
order and literal percent text. The [boundary suite](../saschi/test_picture_dates.py)
checks strict source/portable refusals, eager validation, state reset, limits,
old-profile preservation and a real late second-renderer failure.

The [separate vendor gate](../examples/verify_vendor_picture_dates.py) reads the
unchanged3775-byte Using date directives on the PICTURE statement program from
the pinned external cache. Its complete21 language statements,1 opaque payload,
20 rows/21 INPUT attempts,5 Steps,2 title sets,2 reports and full trace have frozen
hand/base-R expectations. Runtime, emitted Python and actualCLI agree with those
expectations; nine deliberately wrong dataset/report comparisons refuse.
Source/LICENSE bodies and complete derived vendor results remain outside Go.
The source identity is in [the benchmark manifest](vendor-benchmark-manifest.json).
This is one separate conditional vendor proof, not a Roku completion or native
capture. H11 remains open and the original nested-width target remains held.

Symbolic-bound admission: LOW is only a closed lower endpoint and HIGH only a
closed upper endpoint. Qualified exclusions apply to numeric/date literal
endpoints, not symbolic extremes. This avoids interpreting a native symbolic
extreme as a finite domain value. Frozen original/vendor results are unchanged.
