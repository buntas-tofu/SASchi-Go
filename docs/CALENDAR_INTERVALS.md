# Calendar components and bounded intervals

Status: bounded implementation with a prequalified independent hand/base-R oracle.
Acceptance requires the current full source-bound receipt; no native SAS comparison.

Dates are integral SAS epoch days in1753..3999. YEAR/MONTH/DAY accept one date
argument and return calendar components; ordinary missing propagates. INTCK
accepts literal DAY,MONTH,QTR,YEAR and two dates, optionally literal D/DISCRETE.
Count discrete interval boundaries in either direction, retaining zero within a
single interval. INTNX accepts those four literal intervals, one date and an
integral increment with magnitude at most10000, optionally literal B/BEGINNING,
E/END or S/SAME/SAMEDAY. Default B selects the beginning. SAME preserves month/day
position with clipping for short destination months, quarter month-offsets and
leap-year anniversaries. Result must stay in the same date domain.

All arguments validate before missing propagation. Bool,character dates,tagged
missing,fractions,nonfinite dates,unbounded increments and out-of-domain results
refuse. MIDDLE,continuous methods,WEEK or shifted/multiplied/custom intervals,
datetime,timezones and clocks remain separate. Source interval/method/alignment
controls are literal; dates and increments may be primitive numeric literals or
variables. Reuse wave direct ordinary DATA assignments, static skipped/empty
checks and atomic reached failures. Earlier date helpers and the specialized
week-callback family retain their own scopes. Arrays bearing new names remain
available independently.

Reference: pinned SAS9.4 Functions and CALL Routines Fifth Edition P11, YEAR,
MONTH,DAY,INTCK and INTNX. The original full catalog uses stored dates and a
separate existing DATE9 PUT call to generate three logical records.

DS-101 names this ordinary source admission. DS-011 and the earlier INTCK/INTNX
reference fixtures remain on record with unchanged helper bodies and scope.
