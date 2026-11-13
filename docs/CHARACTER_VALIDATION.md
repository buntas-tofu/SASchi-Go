# Character validation and class positions

Status: DS-104 bounded implementation with an independently qualified original
hand/base-R oracle. Maintainer acceptance requires the matching full verification
and workload receipts. No native SAS comparison is claimed.

VERIFY takes a source and 1 through 31 character excerpts. It returns the
one-based position of the first source byte absent from every excerpt, or zero.
ANYALPHA, ANYDIGIT, ANYALNUM, ANYSPACE and NOTDIGIT return the first matching
position for their character class, or zero. Results are positions, not Boolean
flags. Stored padding participates: NOTDIGIT on a padded digit field can find
the first trailing blank.

The admitted domain is printable ASCII. Letters are A through Z and a through z;
digits are 0 through 9; ANYSPACE sees ASCII blanks within this domain. Helpers
accept character lengths 0 through 32767. Source calls initially require
primitive nonempty character literals or ordinary descriptor-backed variables
of width 1 through 32767.

The five class searches accept an optional primitive numeric start. Omitted or
ordinary missing starts at 1. Otherwise the start must be finite, integral and
within magnitude 2147483647. Positive starts search right, negative starts
search left, with an excessive negative magnitude beginning at the end. Zero
or a positive start beyond the field returns zero. Every argument validates
before searching, including later VERIFY excerpts.

Implicit conversion, Unicode/control bytes, tagged starts, fractional/nonfinite
starts and malformed portable forms refuse. Literal and descriptor checks
include empty/skipped paths; dynamic values validate when reached. Existing
WHERE, bare function truth conditions, BY, RETAIN, array and C++ boundaries
remain. The approved IF comparison phase adds its own separate contract.

The original fourteen-statement program checks all six supplied records,
including a blank record, every numeric position and the complete descriptors.
A nonblank guard retains the existing character PUT policy. Twenty-eight hand
pins, 605 generated source/runtime/R cases and 65 shared refusals qualify
classes, excerpt unions, reverse starts and ordinary missing starts. Runtime,
emitted Python and actual CLI compare complete results; six negative CLI
comparisons require their intended failure receipts. Source tests additionally
exercise six late actual CLI failures, lazy dynamic values, empty descriptors,
caller immutability and existing array names.

Before implementation, independent qualification exposed an empty single-column
CSV record omitted by R's default transport. The failed attempt was retained;
explicit blank-record preservation corrected the transport without changing
hand values, source or character-class semantics. Reporting guards were
independently qualified before source admission.

Behavioral reference: SAS 9.4 Functions and CALL Routines, Fifth Edition P11,
VERIFY, ANYALPHA, ANYDIGIT, ANYALNUM, ANYSPACE and NOTDIGIT.
