# Bounded numeric helpers

Status: bounded implementation with a prequalified independent hand/base-R oracle.
Acceptance requires its own full source-bound receipt; no live SAS comparison.

Accept ordinary missing,zero and normal finite binary64 numeric operands with
magnitude at most2147483647. Bool,character,tagged,nonfinite and subnormal values
refuse. ABS preserves magnitude; SIGN returns-1,0or1. Ordinary missing propagates.
CEIL/FLOOR follow the pinned SAS9.4 P11 absolute1E-12 near-integer fuzz rule,
returning the nearest integer within that band, otherwise directional ceiling or
floor. Original exact-binary values and independent boundary pins distinguish
fuzzed results from host ceiling/floor defaults. No CEILZ/FLOORZ,INT widening,
implicit conversions or arbitrary argument expressions.

Reuse wave ordinary DATA direct assignments and primitive numeric literals or
variables. Validate static shape/literals even when skipped or empty; defer dynamic
value errors until reached and publish atomically. Existing numeric profiles and
array names remain distinct. The original stores results before existing w.d PUT
formatting and produces four independently pinned logical character records.
Reference: pinned SAS9.4 Functions and CALL Routines Fifth Edition P11 entries
ABS,SIGN,CEIL,FLOOR.
