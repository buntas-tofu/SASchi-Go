# Second DATA step function wave

Status: bounded implementation evidence for principal and maintainer review.
Acceptance requires a complete source-stable golden receipt and both unchanged
1k workloads for the final source. Original hand/base-R witnesses support the
contracts below. No native SAS comparison or new external-program proof is
implied.

The principal approved 29 selected function names, a separately bounded
consumer profile and two complete composition programs. Each family has its
own source witness, independent R implementation, hand expectations and gate.
The acceptance sequence retains the earlier profiles and appends new gates
without changing their order. Nine original program gates cover the six
families, the separate consumer profile and both final compositions. The selected matrix is not a SAS-wide
denominator.

| Family | Selected names | Rule and source gate | Source and portable scope |
| --- | --- | --- | --- |
| Whitespace/alignment | LEFT, RIGHT, COMPBL, TRIMN | DS-102, verify_whitespace_alignment.py | Printable ASCII, stored-width assignment |
| Concatenation | CAT, CATS, CATT | DS-103, verify_cat_functions.py | Character arguments, default 200 bytes, explicit buffer refusals |
| Validation | VERIFY, ANYALPHA, ANYDIGIT, ANYALNUM, ANYSPACE, NOTDIGIT | DS-104, verify_character_validation.py | One-based ASCII positions, signed/missing starts |
| Search/extraction | FINDC, FINDW, INDEXC, INDEXW, SUBSTRN | DS-105, verify_search_extraction.py | Explicit controls, whole-word substring boundaries, clipped extraction |
| Row statistics | MEDIAN, RANGE, VAR, STD | DS-106, verify_row_statistics.py | Up to 32 bounded integral/missing inputs, sample variance |
| Datetime | QTR, DHMS, DATEPART, TIMEPART, HOUR, MINUTE, SECOND | DS-107, verify_datetime_components.py | Supplied integral epoch values, 1753..3999, civil decomposition |

All 29 names have canonical reference helpers and direct ordinary version 2 DATA
source/portable assignments within their documented bounds. The separately
marked DS-108 consumer profile admits two or three normalization calls from
UPCASE, LOWCASE, TRIM, STRIP, TRIMN and COMPBL over one primitive leaf. Root CATS
can take primitive items or one primitive-argument call from UPCASE, LOWCASE,
TRIM, STRIP, LEFT, RIGHT, COMPBL, TRIMN and SUBSTRN. Selected validator and
MISSING calls can appear on the left of an IF comparison with a numeric literal. Other nested, filtering, loop, array,
BY, RETAIN, C++, SQL and specialized-profile combinations remain held under
this new profile. Earlier direct-call profiles retain their own contracts.

## Complete programs

The distinct twelve-statement consumer witness validates six records before
the final compositions. Its complete hand/R expectations cover every table,
field, descriptor, row and logical record. Another 30 fixed-seed complete input
catalogs compare R, runtime and emitted Python. Independent supplemental kernels
freeze 1008 normalization results, 154 predicate/operator results and 235 identifier
results, including 19 identifier hand pins.

The [record-cleaning composition](../examples/record_cleaning_composition_capture.sas)
is a sixteen-statement original with six hand
records and 30 generated complete catalogs. It combines normalized padded labels,
CATS identifiers with SUBSTRN and LOWCASE items, COUNTW/SCAN token dataflow,
COMPRESS, exact validator positions and IF decisions. Every one of 11 stored
columns participates in the complete comparison. Blank records retain an
explicit nonblank identifier separator within the existing PUT contract.

The [timestamp/measurement composition](../examples/timestamp_measurement_composition_capture.sas)
is a twenty-seven-statement original
with seven hand records and 30 generated complete catalogs. Supplied date/time
parts construct a datetime and recover civil components; stored values feed
YEAR/MONTH/DAY, calendar intervals, missing classification, MEDIAN/RANGE/VAR/STD,
MEAN and ABS. Existing DATE9 storage/reporting remains its own contract. All
28 columns and every logical record compare. Epoch boundaries, leap days,
all-missing/singleton statistics and high-offset samples are represented.

The complete program gates are
[record cleaning](../examples/verify_record_cleaning_composition.py) and
[timestamp/measurement](../examples/verify_timestamp_measurement_composition.py).
Each original also compares runtime, emitted Python and the actual CLI. Wrong
value/type/order/metadata/column-order and logical-output expectations use fresh
CLI directories and require the intended comparison-failure receipt. Late
invalid input must publish no result artifact or partial logical output.

## Evidence limits

Row VAR/STD independent numerical qualification uses 32 normalized binary64
epsilon units, while CLI values remain exact. Negative datetime decomposition
is the explicitly qualified civil-time derivation from SAS epoch definitions;
it is not a native SAS observation. No system clock, host timezone or new
runtime dependency is introduced.

The capability manifest retains a null functions/CALL universe. Reference
helpers, routed names, registry entries and compile-clean corpus files cannot
serve as a semantic coverage percentage. A fresh final external inventory is
compile-only evidence; promoting another external program requires its own
complete unchanged-source execution and independent comparison.

Raw source hashes, oracle qualification, failed attempts and acceptance receipts
remain in ignored telemetry. Publishable code and documentation use relative
paths and generic examples; the source snapshot must pass the invariant linter
and strict sanitization gate.
