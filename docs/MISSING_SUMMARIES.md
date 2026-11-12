# Typed missing values and row summaries

Status: bounded implementation with a prequalified independent hand/base-R oracle.
Acceptance requires the current full source-bound receipt; no native SAS comparison.

MISSING accepts one typed numeric or ASCII character argument. N/NMISS take
1..32numeric arguments. CMISS accepts1..32mixed arguments without conversion.
Ordinary numeric missing and valid ._,.A..Z tags count as missing. Character
missing is empty or entirely ASCII blanks; a period in character text is present.
All arguments validate, including later arguments after a nonmissing choice.

COALESCE takes1..32ordinary numeric/missing arguments and returns the first
nonmissing value; all ordinary missing gives ordinary missing. Tagged COALESCE
is held to avoid an unqualified tag-return policy. COALESCEC takes1..32ASCII
character arguments, preserves selected edge blanks, returns empty if all are
missing and declares a new destination width200. The selected raw result is
bounded to200bytes; other destinations keep existing assignment storage policy.

MEAN takes1..32ordinary missing or integral numeric values with magnitude at most
2147483647. Nonmissing values sum exactly in this domain; division is the binary64
quotient of that sum and count. All-missing yields ordinary missing. Fractional
inputs and tagged MEAN require separate numerical/return-state contracts. Other
numeric inputs are finite and bounded to2147483647; bool,nonfinite,implicit
coercion and malformed tags refuse. Character arguments are printable ASCII
length0..32767. Calls remain direct ordinary DATA assignments under the wave
contexts. Empty/skipped descriptor/literal checks, reached dynamic errors, atomic
publication and earlier namespace/profile boundaries remain explicit.

Authority: pinned SAS9.4 Functions and CALL Routines Fifth Edition P11, MISSING,
N,NMISS,CMISS,COALESCE,COALESCEC and MEAN. Original fixtures retain every supplied
table, all columns and three logical PUT records; no PROC statistics implied.
