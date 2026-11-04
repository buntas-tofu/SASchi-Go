# Integer PICTURE and explicitly framed input

Status: bounded first-party repository/base-R evidence for maintainer review,
conditional on the source-bound full receipt. The unchanged vendor original
remains held at H12. No native result, source repair or whole vendor proof.

Use a separate numeric-picture-fields-v1 family with number_data,number_picture,
number_report and existing literal/reset TITLE. Exact version2 fields,empty
initial catalog,64Steps,8fresh producers,8total PICTURE definitions,2REPORTs and
32title changes. No implicit joins,DATE/FCMP,CSV or C++ behavior.

One leading UTF8 BOM is an explicit source-envelope policy only for this family.
Keep original source bytes/hash and physical line numbers. Account for3prefix
bytes separately from language statements. Require the remainder to be ASCII;
repeated/embedded BOMs and other families retain refusal. Portable args carry
one consistent source-prefix enum; receipt accounting records the scoped prefix
policy. Independent source accounting reads this frame from source syntax, not
from the plan. Do not globally strip BOMs or alter the old lexer contract.

DATA has a fresh name,INFILE DATALINES,INPUT numeric-name character-name $w.,
DATALINES,opaque payload and RUN. Exactly one bounded signed integer followed by
one ASCII blank and exactlyw ASCII letters, then optional trailing blanks, per
record. w1..8;0..1000records,80bytes each. No numeric missing,fractions,extra fields,
quoted input,truncation,FLOWOVER,controls or ambiguous separators. Public storage
is number8 and characterw in declaration order. This is a narrow fixed-width
mixed-input composition,not general formatted/list input.

PROC FORMAT contains1..8 numeric PICTURE statements and RUN. Names are delgrp,
delgx,delgy or ordinary usr_ names ending in a nondigit. Each definition has1..32
ordered contiguous integer ranges covering[-2147483647,2147483647]. LOW is a
closed lower endpoint only;HIGH is a closed upper endpoint only. Numeric endpoints
may be open on either side; singleton integers are admitted. No OTHER,decimal
ranges,FUZZ,MULTIPLIER,PREFIX,ROUND or DATATYPE. Validate every alternative, even
when unused by records or reports.

Templates are1..40 printable nonmacro ASCII bytes. NOEDIT preserves the literal,
including digits and leading blanks. Without NOEDIT, either a nonblank text
message has no digits,or1..16 contiguous digit selectors begin the template and
are followed only by ASCII letters/blanks. At least one selector is nonzero.
Take integer absolute value,retain the rightmostn decimal digits,pad with zeros,
and suppress leading zeros only until the first nonzero selector or significant
digit. Remove only the resulting leading fill blanks as a logical mapping.
09 and99 therefore differ for single-digit values. All-zero selectors and richer
numeric editing remain outside the profile. Template trailing message text is
preserved. A digit after leading message text without NOEDIT refuses. H12 marks
this exact unresolved source form in the original delGy definition.

Reuse the qualified detail REPORT column/alias/DEFINE/TITLE grammar through this
new composition. At least one explicit DISPLAY; numeric PICTURE names and COMMA12
are the only formats. COMMA12 accepts signed whole numbers of magnitude at most
999999999 and emits comma-separated text without alignment. No dates,ORDER,
GROUP,aggregation,COMPUTE or native page-layout inference. Empty descriptors and
unused definitions validate eagerly. ascii-number-picture-report-v1 uses one or
two report_01/02.txt artifacts,JSON-quoted headers/formatted text/characters and
integer unformatted values,1055header/415row/417056report byte caps and1000rows.
Preflight does not render. Actual late failure publishes no partial accepted job.

Independently qualify original ASCII and BOM programs,all rows,reports,statement
lines,EOF attempts and full traces before translator code. Compare runtime,
emitted Python,actualCLI,wrong outputs and real late failure. The vendor source
is not an expected-output fixture: it remains unchanged outside Go and held at
H12 even when the independent envelope policy resolves the BOM obstacle.

The [original gate](../examples/verify_numeric_pictures.py) compares19 complete
independent hand/base-R cases, including ASCII/BOM framing, empty and1000-record
inputs, negative and zero selector editing, NOEDIT leading blanks, full traces and both runtime/generated Python. Actual CLI comparison has
18 known-wrong controls across the two source frames.
[Boundary tests](../saschi/test_numeric_pictures.py) cover exact portable shapes,
foreign profiles, hidden markers, cycles, eager empty descriptors and a real
second-report row overflow after the first report renders. No partial accepted
result or report directory is published. Independent oracle pins were frozen
before this source family was implemented.

H01 is resolved only as the named repository source-envelope policy. The raw
source digest includes all three BOM bytes; statement lines count only language
and opaque data. Receipts add source_prefix metadata only for the admitted BOM.
Native BOM handling and other families do not inherit this policy.

Primary reference, citation-only: [PICTURE statement](https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a002473467.htm).
