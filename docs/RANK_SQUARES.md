# Ranks and sums of squares

Status: bounded DS-112 implementation for maintainer review. Acceptance requires matching source-stable full verification and both unchanged workloads. Independent hand/base-R evidence, no native SAS validation.

1..32 bounded integral values within +/-1000000 or ordinary missing. Validate all values eagerly. Rank is an integral k in 1..argument-count; missing, zero, negative, fractional and above-total ranks refuse error state. A valid rank above nonmissing count returns ordinary missing; ties occupy distinct ranks. All-missing CSS/USS return missing, singleton CSS zero. USS exact integer sum-of-squares. CSS canonical binary64 quotient of exact integer n*sum(x*x)-sum(x)^2 divided by n. Independent R uses pairwise squared differences divided by n; all intermediate integers remain below 2^51. Exact structure/CLI results and exact numeric equality in this domain, with no transfer of VAR/STD tolerance.

Held forms: OF lists, tagged missing, fractional measurements, wider bounds, arbitrary numerical statistics and unqualified consumers.

The original [rank_squares program](../examples/rank_squares_capture.sas) has 10 statements and complete hand/base-R expectations. The [registered gate](../examples/verify_rank_squares.py) compares canonical helpers, source/runtime, emitted Python and actual CLI, including six receipt-verified wrong comparisons. The source suite checks empty and skipped paths, descriptor/metadata/order preservation, caller nonmutation and late atomic failure.

Behavior sections are pinned to the externally cached [SAS 9.4 Functions and CALL Routines: Reference, Fifth Edition](https://documentation.sas.com/api/docsets/lefunctionsref/9.4/content/lefunctionsref.pdf?locale=en). Documentary and independent executable evidence do not establish native SAS validation.
