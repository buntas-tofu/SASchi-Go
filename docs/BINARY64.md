# Bounded rounded scalar arithmetic

Status: repository/base-R evidence for principal and maintainer review. This
profile covers bounded scalar values, ordered DATA observations and declared
logical numeric PUT records. It does not establish live-SAS equivalence,
cross-platform transcendental bit identity, diagnostic recovery or physical SAS
log fidelity. Those claims require additional evidence.

## Primary characterization

The [SAS arithmetic tutorial](https://support.sas.com/documentation/cdl/en/basess/58133/HTML/default/a001334675.htm)
places exponentiation before multiplication/division and addition/subtraction.
Equal-precedence operations proceed left to right except exponentiation, which
proceeds right to left. The [SAS operator table](https://support.sas.com/documentation/cdl/en/lrcon/65287/HTML/default/p00iah2thp63bmn1lt20esag14lh.htm)
also places prefix signs and exponentiation in the first group, evaluated right
to left. Consequently,2**3**2 is512,-2**2 is-4 and(-2)**2 is4.

The [SAS binary floating-point usage note](https://support.sas.com/kb/31/437.html)
identifies IEEE double precision on Windows, UNIX, Linux and AIX. The [numeric
precision reference](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a000695157.htm)
describes finite floating-point precision. These sources support binary64
representation on that platform family. They do not promise that every host
mathematical library produces identical last bits for transcendental functions.

The [CONSTANT reference](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p0l7s11dwvzfq5n1wnw997dye8fx.htm)
defines CONSTANT('PI') as Pi. The [sum-statement reference](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n1dfiqj146yi2cn1maeju9wo7ijs.htm)
defines a retained accumulator initialized to zero, adds the evaluated expression
and treats a missing expression as zero. This differs from ordinary assignment
with a missing addend. The source comment in the sibling series program is only
applicable to its nonmissing values, not to every possible sum statement.

[SIN](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000245945.htm)
and [COS](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000245875.htm)
take radians. Their references also describe missing results when very large
arguments cannot be reduced accurately. [ATAN](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000245864.htm)
returns the principal inverse tangent in radians and returns missing for a missing
argument. The [Functions and CALL Routines reference](https://documentation.sas.com/api/docsets/lefunctionsref/9.4/content/lefunctionsref.pdf)
defines ARSIN and ARCOS on[-1,1], with results in radians. The [SAS mathematical
function summary](https://support.sas.com/documentation/cdl/en/etsug/68148/HTML/default/etsug_model_sect241.htm)
also identifies radians for TAN and excludes odd multiples of Pi/2.

The [BEST reference](https://support.sas.com/documentation/cdl/en/leforinforref/64790/HTML/default/p1fum54c93f8r0n1wrs5mrb05nzi.htm)
sets default width12, omits decimal points on integers and omits trailing zeros.
It permits scientific notation to fit values or improve precision. It does not
specify a complete algorithm for choosing fixed versus scientific output or all
decimal midpoint cases. The [DECIMALCONV reference, printed pages139-140](https://go.documentation.sas.com/api/collections/pgmsascdc/9.4_3.4/docsets/lesysoptsref/content/lesysoptsref.pdf?locale=en)
documents COMPATIBLE as the shipped default and STDIEEE as an alternative that can
change BEST formatting. The [list PUT reference](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/p0jcwhe1ofmb49n1xf1q2kc44b0v.htm)
defines ordinary missing as a period and one following blank for each numeric
variable. Sources consulted2026-10-29. No SAS output was captured for this work.

## Implementation policy

Design inference: introduce the explicit binary64-v1 numeric profile only for
catalog-free scalar DATA steps containing exponentiation or one of the newly
supported functions. Earlier serialized plans and exact multiplication/division
policies retain their behavior. A new source construct does not silently rewrite
an older plan. The profile admits scalar assignments, counted DO bodies, IF,
retained sum statements, OUTPUT and numeric-list PUT. Arrays, SET, INPUT,
WHILE/UNTIL, procedures, macros and the C++ backend remain outside this increment.

DS-052/053 provide a separately gated extension through binary64-rows-v1 for
projection and one numeric SET per step. The original binary64-v1 marker retains
the catalog-free admission described here. New row/projection plans must satisfy
their own composition trigger and eager selected-input validation; see
[numeric row composition](NUMERIC_ROWS.md). Numeric domains, text policies and
all earlier accepted serialized plan shapes remain unchanged.

Every arithmetic operand and reached intermediate is ordinary numeric missing,
zero or a finite normal binary64 value with magnitude at most2147483647. Both
operands validate before missing propagation. Boolean, character, tagged missing,
nonfinite, subnormal and wider values refuse. Addition, subtraction,
multiplication and nonzero division may round to binary64. Overflow, a nonzero
operation underflowing to zero, and a subnormal result refuse. Cancellation to
zero is allowed, and signed zero normalizes to zero.

Exponentiation accepts integer exponents0 through32. It refuses0**0, wider,
fractional or negative exponents and the same result error states. This bounded
domain is a tool choice, not a SAS exponentiation limit. CONSTANT accepts the
literal Pi name only. SIN/COS arguments stay in[-Pi,Pi], TAN in[-Pi/4,Pi/4],
ARSIN/ARCOS in[-1,1], and ATAN uses the general numeric bound. The trigonometric
range limits avoid large-argument reduction and tangent poles. They are profile
limits, not the full SAS domains. Invalid operations refuse atomically; the tool
does not synthesize SAS notes or recovery results.

## Logical numeric text

Design inference: retain the earlier integer and missing renderer. Integers have
magnitude at most99999999999, ordinary missing is a period, and every field adds
one following blank. The complete logical record stays within64 columns.

For a noninteger, require1e-4<=abs(value)<1e9. Include the sign, at least one digit
before the decimal point, and the decimal point in the12-character budget. Use
the remaining positions for decimal places, round to the nearest decimal grid,
then remove trailing zeros and a trailing decimal point. A rounding carry that
exceeds12 positions before trimming refuses. Scientific notation and smaller
fractional magnitudes remain deferred.

An exact rational distance check rejects a value within16 binary64 ULPs of a
decimal midpoint. This avoids selecting a tie-breaking rule from incomplete SAS
characterization and gives the accepted examples room for small host-library
differences. This guard is a declared tool policy. It is not a SAS rounding rule,
and it does not imply that all possible upstream computations have a16ULP error
bound. The R witness independently uses native fixed decimal rendering and
requires unchanged tokens for value plus and minus17ULP, a conservative witness
for the selected cases. The R witness never calls the Python renderer.

The resulting strings are logical records under this declared profile. They are
not labeled as exact SAS BEST12 output. Live characterization must record the SAS
release, platform, numeric representation, DECIMALCONV and relevant output
settings before upgrading that claim.

## Independent evidence and complete programs

The binary64 gate has24 hand numeric pins,1200 generated arithmetic/function
cases,59 shared domain/type/range refusals,13 hand logical-format pins,
400 generated decimal records,11 format refusals and five naive controls.
It compares independently executed base R with the primitive,
source/runtime and sampled emitted Python. Ordered schema, missing masks,
observation multiplicity and logical records are checked separately from numeric
tolerance. It also checks right association and unary-sign precedence.

Numerical comparison uses abs(a-b)/(epsilon*max(1,abs(a),abs(b))), with
epsilon=2**-52. The budget is32 for the direct function cases and trigonometric
program, and2048 for the1000-step series. The larger series budget accounts for
sequential accumulation. These are acceptance tolerances, not measured SAS error
bounds. R and Python can share a host mathematical library. Independence here
means separately implemented source interpretation and control schedules, not an
independent implementation of every transcendental algorithm.

The original binary64_capture.sas consumes21 statements across two DATA steps,
three loop trips and three snapshots. It checks rounded reciprocal accumulation,
IF selection, missing sum addends, missing output, snapshot timing and fresh step
state. The source, runtime, emitted Python, actual CLI and independent R witness
agree under the declared comparison rules.

The entire unchanged sibling sum_of_a_series.sas consumes8 statements and1000
loop trips. Base R accumulates one term at a time, rather than using a vector SUM
that could change accumulation. Its final s is approximately1.6439345666815615,
its loop counter is1001, and its e is approximately-0.00099950016666494612.
Its logical record is `1.6439345667 -0.0009995 `, followed by a newline in emitted
stdout. The program creates no dataset.

The entire unchanged sibling trigonometric_functions.sas consumes25 statements,
has no loops, and emits six ordered two-field records. The records cover sine,
cosine, tangent and the three inverse functions, including radians-to-degrees
conversion. It creates no dataset. Separate in-memory observation variants expose
the final numeric state for tolerance checks; those variants are distinct from
the unchanged-source proofs. Appended-code and truncation controls require the R
interpreter to consume every executable statement. Corpus source remains in the
sibling data repository.

| Program | Source SHA-256 |
| --- | --- |
| binary64_capture.sas |073e624986a2bb979567e8fff507dd111ff15b68061bf0c9f5024b60f49de526 |
| sum_of_a_series.sas |0fd04c9914fcd4d1a517e20aef2fc271602b3c545f6a277f04065c3b745f7c68 |
| trigonometric_functions.sas |d99125f923ad821c5d97754acf14c444841f088a9cfa6da617cd89c6edbf7b5a |
