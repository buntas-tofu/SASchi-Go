# Calendar constructors

Status: bounded DS-114 implementation for maintainer review. Acceptance requires matching source-stable full verification and both unchanged workloads. Independent hand/base-R evidence, no native SAS validation.

Integral HMS hours0..23, minutes/seconds0..59, resulting seconds0..86399. YYQ uses explicit four-digit years1753..3999 and quarters1..4, first civil day of the quarter. DATEJUL uses strict integral seven-digit yyyyddd with valid day-of-year and leap-year checks in1753..3999. JULDATE7 accepts integral SAS epoch days in the same civil date range and returns numeric yyyyddd. Ordinary missing propagates after every operand is validated; invalid components refuse. Full ordered original output has independent hand/base-R expectations.

Held forms: Two-digit years, YEARCUTOFF, JULDATE, system clocks, timezones, fractional/normalized time components and new consumers.

The original [calendar_constructors program](../examples/calendar_constructors_capture.sas) has 11 statements and complete hand/base-R expectations. The [registered gate](../examples/verify_calendar_constructors.py) compares canonical helpers, source/runtime, emitted Python and actual CLI, including six receipt-verified wrong comparisons. The source suite checks empty and skipped paths, descriptor/metadata/order preservation, caller nonmutation and late atomic failure.

Behavior sections are pinned to the externally cached [SAS 9.4 Functions and CALL Routines: Reference, Fifth Edition](https://documentation.sas.com/api/docsets/lefunctionsref/9.4/content/lefunctionsref.pdf?locale=en). Documentary and independent executable evidence do not establish native SAS validation.
