# Bounded function consumers

Status: DS-108 typed consumer implementation with independently frozen original
hand/base-R and supplemental kernel oracles. Maintainer acceptance requires
matching complete verification and workload receipts. No native SAS comparison
is claimed.

The new `function-consumers-v1` profile qualifies ordinary version2 DATA steps
containing at least one of the following forms:

- A final assignment whose RHS is a unary chain of two or three calls from
  UPCASE, LOWCASE, TRIM, STRIP, TRIMN and COMPBL, over one primitive character
  leaf. New stored width inherits the leaf's descriptor.
- A root CATS assignment with 1 through 32 items, including at least one call.
  Each item is primitive character or one primitive-argument call from UPCASE,
  LOWCASE, TRIM, STRIP, LEFT, RIGHT, COMPBL, TRIMN and SUBSTRN. New width is200;
  the actual result and destination buffer bounds are checked.
- An IF comparison whose left side is one primitive-argument MISSING, VERIFY,
  ANYALPHA, ANYDIGIT, ANYALNUM, ANYSPACE or NOTDIGIT call, and whose right side
  is a finite integral literal from0through32767. Existing numeric comparison
  aliases remain available.

The compiler inserts an explicit `function_profile` operation with exactly
`{"profile":"function-consumers-v1"}` before existing profile validation.
Portable execution independently requires one exact marker at the beginning
of the operation list and a genuine qualified consumer. Missing, duplicate,
moved, malformed or unnecessary markers refuse. The marker has no SAS data
or output side effect. Direct-call profiles and their validators remain strict
outside this profile.

These finite character grammars qualify the relevant temporary behavior.
Normalization operations alter case or edge/run blanks; final inherited-width
storage makes unobserved edge padding irrelevant. CATS strips every item's
edges, so its admitted temporary items do not expose that padding. Empty
intermediates remain empty through case mapping, STRIP, TRIMN and COMPBL;
TRIM contributes one blank. Earlier general helper refusals on empty arguments
remain unchanged.

RIGHT/LEFT/REVERSE argument chains, nested raw CAT/CATT buffers, deeper CATS
items and numeric nesting remain held. IF bare function truth, swapped sides,
compound Boolean expressions, nonliteral comparison targets and WHERE remain
held. This new profile excludes loops, subsetting IF, arrays, BY, RETAIN,
multiple driving inputs, C++, SQL and specialized execution profiles. Existing
ordinary direct-call profiles retain their separately accepted loop behavior.

Literal and descriptor checks occur on empty and skipped paths. Dynamic values
and ELSE IF predicates evaluate only when reached. Scratch fields reset for
each input row; descriptor/column/row order and caller data remain stable.
A late fault publishes neither partial results nor partial logical output.

The independent twelve-statement original compares six records and all seven
stored fields, plus complete logical output. Thirty generated whole catalogs
exercise R/runtime/emitted execution, including empty input. Supplemental R
kernels, qualified before implementation, freeze1008normalization chain results,
154predicate/operator results and235identifier results, including19identifier
hand pins. Actual CLI gates include six receipt-verified wrong comparisons.
Source and portable tests cover profile isolation, exact marker shape,
short-circuit evaluation, buffer faults, metadata, deterministic emission and
late actual CLI failures.

Older source-refusal assertions overlapped the newly approved chains.
Their old-profile checks remain, while separate DS-108 positive evidence admits
the marked source forms. Replacement source cases retain held call-pair/depth
coverage. No older profile receives a blanket nested-call exception.

Source admission applies finite normalization and CATS-item grammars. The
older atomic TRIM/STRIP parser extends only to bounded normalization chains.
Other existing call parsers retain their parenthesized primitive arguments;
the new profile independently checks every admitted call pair and depth.
