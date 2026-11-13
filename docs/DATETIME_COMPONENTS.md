# Supplied datetime components

Status: DS-107 bounded implementation with an independently qualified original
hand/base-R oracle. Maintainer acceptance requires the matching full verification
and workload receipts. Negative-epoch decomposition is a labeled derivation
from SAS epoch and civil-time definitions, not a native SAS observation.

QTR source admission belongs to DS-107; the earlier MDY/WEEKDAY dispatcher
continues to reject QTR and retains its original behavior. HMS remains unwired.

QTR accepts an integral SAS date in the existing Gregorian 1753 through 3999
domain and returns its quarter. DHMS accepts that date plus integral hours
0 through 23, minutes 0 through 59 and seconds 0 through 59. It constructs
supplied datetime seconds since 1960-01-01. Every component validates before
ordinary missing propagates. Out-of-range normalization and fractional seconds
remain held.

DATEPART and TIMEPART recover the civil day and nonnegative seconds since its
midnight. HOUR, MINUTE and SECOND recover those clock components from a supplied
integer datetime in the same date range. Canonical time values 0 through 86399
are a subset. An input of 90000 to HOUR returns 1, and SECOND(65) returns 5;
these are timestamp decomposition, separate from DHMS component validation.

The admitted datetime range runs from the first second of 1753-01-01 through
the last second of 3999-12-31. Whole-second decomposition uses floor division
and a nonnegative daily remainder. For example, -1 denotes date -1 at 23:59:59;
-86401 denotes date -2 at 23:59:59. This is the explicitly qualified derivation
used by the independent civil UTC R witness and integer Python implementation.
It does not use a system clock or host timezone.

Source calls initially require direct ordinary version2 DATA assignments and
primitive numeric or ordinary missing operands. Static literals and empty
input descriptors validate eagerly. Dynamic values validate when reached;
a late failure publishes no partial tables or logical output. Tagged missing,
character conversion, fractions, wider date ranges, additional formats and
unqualified nested or specialized-profile consumers remain separate work.
Timestamp literals use this family's wider bound without broadening earlier
numeric helper domains.

The thirteen-statement original checks eight supplied rows, every timestamp
component and the existing stored DATE9 reporting contract. Thirty-eight hand
pins and 560 generated cases cover epoch boundaries, leap days, missing
components and domain limits. The independent full-program witness compares
runtime, emitted Python and actual CLI values, metadata/order and logical
records, plus six receipt-verified wrong comparisons. Source tests cover
process timezone independence, eager and lazy checks, immutable inputs and
seven late actual CLI failures.

Behavioral reference: SAS 9.4 Functions and CALL Routines, Fifth Edition P11,
QTR, DHMS, DATEPART, TIMEPART, HOUR, MINUTE and SECOND, together with SAS's
published date, time and datetime epoch definitions. No new live SAS comparison
or general datetime formatting claim is made.
