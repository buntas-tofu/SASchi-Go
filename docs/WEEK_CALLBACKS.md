# Week functions used as formats

Status: bounded original and unchanged vendor repository/base-R evidence for
maintainer review, conditional on the current source-bound full receipt. No arbitrary FCMP, native
library files, physical REPORT pages or live SAS comparison is claimed.

Use a separate week-callback-report-v1 family. Exact complete version2 portable
plans, empty initial catalog,64Steps, up to8fresh date producers, one FCMP block,
one CMPLIB activation, up to8unique callback VALUE definitions, two REPORTs and
32title changes. FCMP, CMPLIB and formats are job-local symbolic state, not host
file paths. Validate unused functions, callbacks and empty-table report metadata.

FCMP requires OUTLIB=work.functions.package,1..8unique ordinary function names
start,end or usr_ names ending in a nondigit. Each has one numeric argument, a
fresh ordinary local dt variable and declared character return width9. Bodies
are exactly dt=INTNX('week.2',argument,0), or
 dt=INTNX('week.7',argument,1)-1, followed by RETURN(PUT(dt,DATE9.)),ENDSUB and
QUIT. Case and whitespace may differ; no other calls, assignment expressions,
recursion, side effects, macros or implicit external library lookup. OPTIONS
CMPLIB=work.functions must follow this block. FCMP QUIT ends its own block;
OPTIONS is a separate statement and Step.

WEEK.2 begins Monday, WEEK.7 begins Saturday. Default alignment is beginning.
START therefore selects the Monday at or before the input; END selects Friday
following the current Saturday-based interval. Sunday is not moved to the next
Monday. Saturday's END is the next Friday. These are specified expressions, not
inferences from the original prose. Independently test each weekday, epoch,
leap/year boundaries and missing. Shifted output must stay in1753..3999. Missing
returns the DATE9 period logical field. Numeric date storage remains unchanged.

PROC FORMAT VALUE name OTHER=[function()] binds an available activated local
function implicitly receiving the formatted date. One or more VALUE statements
per FORMAT block are distinct Steps, not duplicated language statements.
Only this form is accepted. No ranges, DEFAULT or numeric return type. Callback
formats require the declared12-character report width; the character return is
DATE9 width9. Alignment padding is removed in the named logical text mapping.

Reuse canonical DATE9 CARDS producers through separately marked week_data:
1..32typed columns,1000records/80ASCII bytes, canonical four-digit DATE9 or period,
bounded integer reads and colon-modified characters. Fresh tables only.
No numeric source may masquerade as a date callback argument.

REPORT requires DATA=name NOWD, simple source/alias columns followed by one
parenthesized literal spanning heading containing at least one alias. One ORDER
column must be the first, unaliased, numeric non-date column; all values are
nonmissing integers10..99 in ascending order. This bounded source order also
agrees with formatted order and avoids general REPORT sorting. Repeated ORDER
cells are suppressed to an empty quoted string after the first row of each run;
no source row is dropped. At least one explicit DISPLAY, no GROUP/ACROSS/analysis,
COMPUTE or other ordering. DEFINE labels preserve literal slashes as characters.
The header for a spanned column is JSON-quoted span+'/'+label, a declared logical
mapping, not physical stacked headers. Other headers use literal labels/aliases.
One DISPLAY flag per DEFINE is optional, except ORDER cannot also be DISPLAY.

Formats are10. for nonnegative whole numeric storage through9999999999,
WEEKDATE. for genuine date storage using the qualified English29-character full
weekday/month field with alignment stripped, or callback-name12. for genuine
dates. Empty schemas validate even without data. Callback result domains are
checked eagerly for every source date without invoking actual callback/render
execution. Unformatted integer, period and trimmed-character cells retain
qualified logical conventions. Headers/formatted text/ORDER cells are quoted.
One optional inline TITLE/reset and trailing job-local TITLE changes are allowed.

ascii-week-callback-report-v1 has report_01.txt/02.txt,1055header/415row and
417056report byte caps,1000report rows,ASCII LF with final LF. A real late second
report overflow publishes no accepted partial result or artifacts. Preflight
must not execute callback formatting or renderers. Runtime callback calls occur
once per displayed callback cell, with a full independently frozen trace.
Original and unchanged vendor source/license byte identities remain separate;
source bodies and complete vendor-derived results stay external.

Admission refinement: every displayed alias requires exactly one DEFINE.
Non-ORDER numeric columns require an explicit qualified format. One trailing
spanning group uses explicit aliases. This avoids extrapolating native analysis
or default numeric-output behavior. The qualified calendar endpoints happen to
be a Monday at1753-01-01 and Friday at3999-12-31, so both edge dates are valid
for these two exact bodies. Other calendar values retain prior refusal.

[The original gate](../examples/verify_week_callbacks.py) compares16whole-source
independent R cases with six literal calendar pins, empty/missing and1000-row
controls, complete traces, runtime/generated Python and actual CLI with nine
wrong comparison controls. [The boundary suite](../saschi/test_week_callbacks.py)
proves exact source/portable admission, job-local names/titles, eager empty
schemas, one call per callback cell and actual second-header overflow with no
accepted partial result or report publication. Preflight does not render.

[The separate vendor gate](../examples/verify_vendor_week_callbacks.py) binds
the complete unchanged3127-byte source and LICENSE pins from the
[benchmark manifest](vendor-benchmark-manifest.json). It compares30language
statements plus1opaque payload,10records/11attempts,2function definitions,
2callback formats,20actual callback cells and one complete logical report.
All full vendor-derived results and source/LICENSE bodies stay external.
Source accounting excludes FUNCTION declarations, RETURN syntax and COLUMN
spanning parentheses from function calls, while recording INTNX,PUT and the
explicit VALUE callback references under this qualified source context only.

Primary references, citation-only:

- [INTNX default beginning alignment](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p10v3sa3i4kfxfn1sovhi5xzxh8n.htm).
- [WEEK.2 and WEEK.7 intervals](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p0syn64amroombn14vrdzksh459w.htm).
- [REPORT ORDER behavior](https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a000146851.htm).
