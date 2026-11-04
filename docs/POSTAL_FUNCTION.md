# Postal formats and a bounded country function

Status: bounded original and unchanged vendor repository/base-R evidence for
maintainer review, conditional on the current source-bound full receipt, under
the principal-approved pinned
USPS and finite-ZIP policy. Repository behavior, not live SAS zone-table parity,
universal address validation, official postal findings or physical REPORT pages.

Use a separate postal-function-report-v1 source family. Exact version2 portable
plans, empty initial catalog,64Steps, one character-format block, one FCMP block,
one CMPLIB activation, up to8fresh quoted-input producers, one owned ascending
country replacement SORT, up to2computed REPORTs and32title changes. No implicit
join with week-callback, old CSV profiles, C++ or arbitrary FCMP. All definitions,
unused paths and empty report schemas validate eagerly. State is job-local.

Character VALUE names postabb or usr_ names ending in a nondigit, with a leading
$. Each range is four ASCII digits, inclusive lexical endpoints of equal width.
Comma-separated range groups share one literal uppercase alphabetic label1..3.
Ranges are nonoverlapping; source order may differ from lexical order. Singletons
may be admitted explicitly. No LOW,HIGH,OTHER,exclusions,macro labels,nested
formats or general collation. The country callback trims only trailing padding
and requires AU input exactly four digits covered by a declared range. An
uncovered AU code refuses, rather than inferring SAS default-format behavior.
AU labels derive from source-defined ranges, not a universal postal database.

FCMP requires OUTLIB=work.functions.package and one function StateProv or usr_
ending in a nondigit, two declared character arguments and character return5.
Its exact structure is IF UPCASE(country)='AU' THEN local=PUT(code,$format.);
ELSE IF UPCASE(country)='US' THEN local=ZIPSTATE(code);
ELSE local=' '; RETURN(local); ENDSUB; QUIT. Arguments are distinct, local is
fresh, the named character format is preceding, and the CMPLIB activation is
exactly work.functions after FCMP. Country UPCASE applies to padded character2
values; code is character5. US ZIPSTATE accepts exactly five ASCII digit text
characters, preserving leading zeros. Numeric arguments,ZIP+4,missing or unknown
US ZIPs refuse. Other countries return blank character5 without a postal lookup.
No host library files, arbitrary statements, eval or callback recursion.

The USPS workbook is the dated2026-10-01 official ZIP Locale Detail XLSX, pinned
by exact4380487bytes and SHA256. All reference bodies and derived ZIP/state maps
stay outside Go and outside Git. The declared19ZIP identities and raw/semantic
mapping hashes may be metadata in Go. Require every matching delivery-ZIP row to
agree on physical state. For six original codes served by an office with another
physical ZIP, prior direct official Cities by ZIP observations corroborate the
state. The accepted compact map hash fixes those19values; changed reference
content or uncovered codes refuse. Preparation is explicit before offline gates;
runtime and verification never fetch. No additional runtime package is needed.
Reference access verifies the external path, no symlink/Git/repository storage,
raw digest and finite semantic map before use. No state values are hardcoded.
First-party or vendor full expected reports containing derived postal values
also stay external. Oracle/result pins and counts are permitted metadata.

DATA requires INFILE CARDS DLM=',' DSD and INPUT of1..8unique character variables,
colon:$w. with widths1..64, then CARDS, opaque records and RUN. At most1000rows,
256ASCII bytes per record, exactly one physical CSV record per row, no blank or
missing fields,controls,macros,overwidth values or FLOWOVER. Decoded fields must have no edge blanks and cannot be period-only. Quoted fields
may contain commas and escaped double quotes; unquoted fields cannot contain
quotes. A closing quote must be immediately followed by a comma or record end.
Do not infer old unquoted CSV admission. Values retain declared right padding.
Every record must contain the callback's character2country and character5code
columns when a report invokes it. Descriptors remain ordered type/length only.

SORT requires DATA=owned-name, BY one character2country column and RUN. It
replaces that owned table, with stable ASCII ascending order preserving ties,
padding and all columns. Preflight validates schemas and forwards data without
executing sorting, callback rendering or report formatting. Only one replacement
sort; reports must follow it and BY the same country. No dates,descending,
DUPOUT,NODUP,WHERE or external initial catalog.

REPORT requires DATA=name NOWD,COLUMN/COLUMNS of simple unaliased data names and
one fresh computed column, BY the country, DEFINE computed / COMPUTED literal
label, COMPUTE computed / CHAR LENGTH=5, computed=function(country,code), ENDCOMP,
optional inline TITLE/reset and RUN. The two argument source columns must occur
to the left of the computed column, matching left-to-right row evaluation.
Every displayed source column is character storage. No general expressions,
other DEFINEs,ORDER,GROUP,ACROSS,aggregation,COMPUTE BEFORE/AFTER or dynamictypes.
Keep each source observation and add the computed text only to report cells,
not the stored dataset. Every row's callback is executed once in report order.

ascii-postal-function-report-v1 uses report_01/02.txt. One optional TITLE line,
JSON-quoted column labels, then a BY country="value" line at each new country
run and JSON-quoted trimmed character row cells. Computed values are right-padded
to5during callback execution, then trimmed for logical text. No observation
column or native page-layout inference. Retain1055header/415row/417056report byte
caps and1000data rows, allowing at most1000additional BY lines. Preflight must
not call actual sort/callback/render execution. Actual late report failure must
publish no accepted partial result, reports or copied reference data.

One or two computed REPORTs are required. The source parser requires exact
case-sensitive quoted AU/US branch constants, independently of case-insensitive
keywords and names. Preflight checks lexical/domain membership without sorting,
calling ZIPSTATE, executing the callback or rendering. Runtime calls ZIPSTATE
only in the US branch and executes one callback per report row. The job receipt
adds postal_reference metadata after successful execution, naming the policy,
source/map hashes and19-code domain, with its explicit evidence limit.

[The independent reference gate](../examples/verify_postal_reference.py) compares
all19values against a separate base-R workbook extraction and verifies leading
zeros and nine rejected input forms. [The original program gate](../examples/verify_postal_function.py)
compares12whole-source R cases, including empty input, all19ZIPs,1000rows, quoted
commas/escaped quotes, AU boundaries, unknown-country fallback, complete traces,
runtime/generated Python and actual CLI with nine wrong comparison controls.
The original source, hand and R witnesses were qualified before implementation.
There is intentionally no expected-result JSON in Go for this reference-derived
fixture. All complete results are produced in external temporary directories.

[The vendor gate](../examples/verify_vendor_postal_function.py) binds the
unchanged3902-byte source and LICENSE in the
[benchmark manifest](vendor-benchmark-manifest.json):31language statements plus
1opaque payload,25records/26attempts,25callback cells,2BYruns and one whole report.
Its postal values follow this approved reference policy, not a native SAS capture.
[Boundary tests](../saschi/test_postal_function.py) include exact portable shapes,
reference-injection refusal, namespace state and a real second-report row
overflow after the first succeeds, with no accepted partial publication.
[Provider tests](../saschi/test_postal_reference.py) enforce raw/semantic pins,
unknown ZIP refusal, path isolation, no symlinks, immutable caller copies and
rechecking the raw file even after a decoded-cache hit.

Prepare with python tools/prepare_postal_reference.py; add --check for offline
verification. SASCHI_POSTAL_CACHE may name an external cache directory.
The default is the system temporary directory plus saschi-postal-cache/2026-10-01.
The base-R witness takes SASCHI_POSTAL_REFERENCE as the workbook file path; the
gates set it explicitly to the verified file. Runtime never fetches or guesses
a substitute. CI prepares the exact reference before running the unchanged gate
order. No runtime dependency beyond the established set is added.

Reference metadata: [ZIP Locale Detail](https://postalpro.usps.com/ZIP_Locale_Detail),
dated2026-10-01,4380487bytes,raw SHA256
6e923786b70a5ab7ed93fd89cf0ffee3633c6daa58c86c6d4c8702dcd860bc07.
Qualified compact sorted JSON map plus LF SHA256
47dd0c9d0afcd3eabdc35bddf56f8d496d0017814d50ff9fe77dc6545bb89f2e.
The original16USZIPs plus01040,27511,90049 form the finite domain. The metadata
and [provider constants](../saschi/postal_reference.py) list identities and pins,
not state values. Six serving-office mismatches were independently corroborated
through official USPS Cities by ZIP observations, retained outside Go.
City labels in input are display data and never lookup evidence.

Primary REPORT reference, citation-only:
[Left-to-right computed columns](https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a002473631.htm).

All FORMAT gate source/witness/expectation/CLI temporary directories are checked
to stay outside Go and Git before writing complete data. A temporary-directory
configuration pointing inside Go refuses, rather than leaking reference-derived
results into ignored telemetry.
