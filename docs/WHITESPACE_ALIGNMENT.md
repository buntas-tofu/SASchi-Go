# Whitespace and alignment functions

Status: DS-102 bounded implementation with an independently qualified hand/base-R
oracle. Maintainer acceptance requires the matching full source-bound receipt
and both workload suites. No native SAS comparison is claimed.

LEFT, RIGHT, COMPBL and TRIMN accept one printable ASCII character value.
LEFT moves leading blanks to the end and RIGHT moves trailing blanks to the
start; both preserve the argument length. COMPBL replaces each consecutive run
of ASCII blanks with one blank. TRIMN removes trailing blanks and returns a
zero-length value for an all-blank argument.

The reference helpers accept character values of length 0 through 32767,
including qualified empty temporaries. Source admission initially requires a
primitive nonempty character literal or an ordinary character variable with a
preceding descriptor of width 1 through 32767. Calls use direct ordinary
version2 DATA assignments. A new destination inherits the first argument's
width; an existing destination retains the established assignment padding and
truncation policy. TRIMN's temporary length is distinct from the receiving
variable's stored width.

Implicit conversion, Unicode/control bytes, numeric or tagged missing arguments,
malformed portable calls and out-of-range widths refuse. Literal and descriptor
checks include empty inputs and skipped branches; dynamic values validate when
reached. Late errors publish no partial result or emitted logical output.
WHERE, BY, RETAIN, array, C++ and unqualified temporary consumers remain held.
Pre-existing arrays with these names remain available independently.

The original ten-statement program retains all five supplied rows, every
descriptor and every stored value. Its two logical character PUT consumers
have explicit nonblank guards, preserving the existing blank-PUT refusal.
Twenty hand pins and an independent byte-array R implementation distinguish
alignment, compressed blanks and empty TRIMN values. The gate adds 408 generated
source/runtime/R cases, 28 shared refusals, actual emitted/CLI execution and six
receipt-verified negative CLI comparisons. The source suite additionally covers
metadata/order, empty and skipped paths, caller nonmutation, deterministic
emission and four actual late CLI failures after a valid first row.

An initial original witness attempted blank character PUT, which is outside
the existing output contract. Its failed focused run was retained. Before
reimplementation, the exact accepted baseline was restored, the guarded
original was independently requalified with the new helpers absent, and the
existing consumers were replayed on that baseline. Helper pins and all original
data expectations were unchanged. Earlier unguarded output expectations do not
establish a new PUT admission.

Behavioral reference: SAS 9.4 Functions and CALL Routines, Fifth Edition P11,
LEFT, RIGHT, COMPBL and TRIMN. See the
[approved continuation plan](NEXT_DATA_STEP_WAVE.md) for later consumers.
