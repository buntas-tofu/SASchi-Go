# Zero fuzz numeric

Status: bounded DS-113 implementation for maintainer review. Acceptance requires matching source-stable full verification and both unchanged workloads. Independent hand/base-R evidence, no native SAS validation.

Numeric binary64 operands, absolute value <=1000000 and either zero or >=2^-40; ordinary missing propagates after validating every argument. CEILZ/FLOORZ/INTZ perform mathematical integer rounding with no fuzz. ROUNDZ defaults to unit 1 and otherwise admits positive power-of-two units 2^-10..2^10; exact half ties select an even multiple, adjacent floats remain distinct. MODZ independently admits signed power-of-two divisors with the same magnitudes, nonzero result has dividend sign and no fuzz. This slice has exact scaling and remainders. New helper results canonicalize numeric zero to +0, a stated transport policy with signed-zero tests, not an IEEE zero-sign claim about native SAS. Exact numeric/CLI comparison.

Held forms: Decimal or arbitrary divisors/rounding units, smaller nonzero operands, overflow, underflow, tagged missing, implicit conversions and new consumers.

The original [zero_fuzz_numeric program](../examples/zero_fuzz_numeric_capture.sas) has 11 statements and complete hand/base-R expectations. The [registered gate](../examples/verify_zero_fuzz_numeric.py) compares canonical helpers, source/runtime, emitted Python and actual CLI, including six receipt-verified wrong comparisons. The source suite checks empty and skipped paths, descriptor/metadata/order preservation, caller nonmutation and late atomic failure.

Behavior sections are pinned to the externally cached [SAS 9.4 Functions and CALL Routines: Reference, Fifth Edition](https://documentation.sas.com/api/docsets/lefunctionsref/9.4/content/lefunctionsref.pdf?locale=en). Documentary and independent executable evidence do not establish native SAS validation.
