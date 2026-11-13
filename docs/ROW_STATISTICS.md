# Missing-aware row statistics

Status: DS-106 bounded implementation with a separately qualified original
hand/base-R oracle. Maintainer acceptance requires the matching full verification
and workload receipts. Numerical qualification is repository policy; no native
SAS binary64 comparison is claimed.

MEDIAN, RANGE, VAR and STD accept 1 through 32 primitive numeric arguments.
Ordinary missing values are removed only after every argument validates. The
admitted present values are finite integers within magnitude 1000000. Fractional,
tagged, Boolean, nonfinite and implicitly converted values refuse. OF lists,
weights and procedure-level statistics remain separate contracts.

All four functions return ordinary missing for an empty present sample. MEDIAN
sorts the sample and averages its middle pair for even sizes. RANGE is maximum
minus minimum, with a singleton result of zero. VAR and STD require at least two
present values and use the sample divisor n minus 1. The older procedure helper
`sas_std(vals, vardef)` retains its earlier behavior; source STD uses the separate
row wrapper.

The Python variance uses an exact integer numerator and a rational division,
then one conversion to binary64. STD takes the square root of that variance.
The independent R witness uses all pairwise squared differences, with a different
formula. Within the admitted integer and arity bounds, its products and sums
remain exactly representable before division. Independent VAR/STD comparisons
allow 32 normalized binary64 epsilon units. MEDIAN, RANGE, missing masks,
descriptors, order and logical records are exact. The CLI's exact numeric
comparison remains unchanged, including rejection of a one-ULP wrong result.

The nine-statement original checks seven measurement rows and every stored
statistic. Thirty-two hand pins, 404 generated cases and 40 shared refusals
include all-missing, singleton, ties, high offsets and alternating extremes.
The complete original compares runtime, emitted Python and actual CLI results,
including six receipt-verified wrong comparisons. Source tests check decimal
references, eager skipped/empty descriptor checks, reached dynamic faults,
metadata/order, old helper preservation and four late actual CLI failures.

Behavioral reference: SAS 9.4 Functions and CALL Routines, Fifth Edition P11,
MEDIAN, RANGE, VAR and STD. Exact native SAS numerical rounding remains outside
this repository/base-R evidence.
