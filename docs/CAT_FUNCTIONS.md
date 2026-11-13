# CAT family character functions

Status: DS-103 bounded implementation with an independently qualified original
hand/base-R oracle. Maintainer acceptance requires the matching full verification
and workload receipts. No native SAS comparison is claimed.

CAT, CATS and CATT accept 1 through 32 printable ASCII character items. CAT
preserves every byte. CATS removes leading and trailing ASCII blanks from each
item; CATT removes trailing blanks only. A new destination has width 200,
distinct from the sum-of-widths rule for the concatenation operator.

Helpers admit item lengths 0 through 32767 and validate every argument before
assembly. The raw result must not exceed 200 bytes. Source calls initially use
primitive nonempty character literals or ordinary character variables with
preceding descriptors. Literal result bounds and statically excessive CAT raw
widths are checked eagerly, including empty/skipped paths. Other dynamic values
and destination fit are checked when reached. An existing destination shorter
than the actual result refuses; no truncation or blank-result/error-flag state
is simulated.

Numeric BEST conversion, OF lists, Unicode/control bytes, general temporary
buffers, WHERE, BY, RETAIN, arrays, C++ and specialized-profile joins remain held.
The later consumer phase has its own admission contract. Ordinary arrays named
CAT, CATS or CATT remain available independently.

The original nine-statement program retains all five supplied rows, both input
descriptors and all three 200-byte results. Explicit nonblank guards preserve
the existing character PUT boundary. Eighteen hand pins, 362 generated
source/runtime/R cases and 33 shared refusals qualify padding, trimming, empty
items, maximum arity and result bounds. Complete runtime/emitted/actual-CLI
comparisons include six receipt-verified wrong comparisons. Source tests cover
late CATS/CATT destination overflow after a valid row, actual atomic CLI errors,
metadata/order, caller immutability, empty/skipped checks and malformed plans.

Behavioral reference: SAS 9.4 Functions and CALL Routines, Fifth Edition P11,
CAT, CATS and CATT. See the [continuation plan](NEXT_DATA_STEP_WAVE.md).
