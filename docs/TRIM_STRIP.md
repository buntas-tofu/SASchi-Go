# Bounded TRIM and STRIP

Status: DS-043 repository/base-R evidence for principal/maintainer review.
This profile proves bounded character values and logical output records.
Live-SAS validation and physical SAS log fidelity remain outstanding. Wider
syntax, values or changed source bytes require new evidence before acceptance.

## Characterization and representation

The primary [SAS TRIM reference](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000212226.htm)
defines trailing-blank removal and a one-blank result for an all-blank argument.
The [SAS STRIP reference](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/n0xk6tl87f4b4qn1sp1ywen1ntan.htm)
defines leading/trailing-blank removal and a zero-length result for all blanks.
Both references distinguish a shortened return value from the receiving variable:
a new target inherits the argument's length, and assignment pads the destination.
The printable ASCII profile is a bounded subset of the documented SBCS behavior.

Design inference: retain fixed character descriptors and mark direct TRIM/STRIP
call operands during concatenation. Those operands contribute their shortened
bytes; other operands contribute their existing fixed-width values. Assignment
then truncates or pads to the receiving width. The result descriptor of a
concatenation sums declared operand widths, not observed byte counts. No general
temporary-expression representation or output operation is introduced.

For `length a $4; a=' X ';`, `trim(a)` supplies the bytes ` X`, while `strip(a)`
supplies `X`. Assigned separately, both targets have width4 and regain trailing
blanks. In `'['||strip(a)||']'`, the raw value is `[X]`, assigned into width6.
For all-blank a, the corresponding TRIM concatenation starts `[ ]`; STRIP starts
`[]`. Two empty STRIP temporaries can concatenate to zero bytes, then become
blank-filled fixed storage on assignment. The older concatenation helper still
refuses empty ordinary operands.

## Accepted scope and boundaries

Arguments are printable ASCII character literals or ordinary variables with a
preceding character descriptor, width1..32767. Calls are direct assignment RHS
values or direct operands in a concatenation RHS. Other concatenation operands
are character literals or ordinary variables. The existing2..32 operand limit
and total declared width limit32767 remain in force. These are implementation
policies, not SAS language limits.

Top-level DATA, simple IF/ELSE and existing counted bodies, including bounded
nested loops, are covered. A call reads the actual current row variable;
self-assignment remains valid. Static types, argument/call shapes and widths
validate on empty, filtered, skipped and zero-trip paths. Dynamic character
content validates when reached. A late failure publishes neither an accepted
result nor buffered stdout. OUTPUT snapshots, suppression of implicit output,
input metadata and row/run/step reset retain their existing behavior. No internal
iteration or temporary state enters dataset schemas.

Numeric conversion, nested call arguments, array arguments, automatic names,
LENGTH/REVERSE/SUBSTR/CATX temporary consumers, predicates, WHERE, PUT expressions,
PUT _ALL_, DO OVER/WHILE/UNTIL bodies, MERGE and C++ remain refused. Unresolved
double-quoted macros, non-ASCII text and control characters remain outside this
profile. Other string functions and array/counting limits are unchanged.

## Proofs

The semantic gate has12 hand pins,1600 constructive source/runtime/base-R
comparisons,20 shared refusals and4 naive controls. The30-test suite checks
fixed descriptors, temporary values, boundaries, skipped paths, snapshots,
resets, malformed serialized plans, atomic failure and complete-program proofs.
An isolated installed-wheel check executes the new functions without adding
runtime dependencies.

The original `examples/trim_strip_capture.sas` has26 statements and two DATA
steps. It captures three character snapshots plus three counted snapshots.
Independent base R uses raw-byte blank scanning and its own complete-program
interpreter. It accounts for every statement and returns rows, schemas, logs,
final state and loop-trip counts. Dataset comparator controls reject wrong
values, row order, multiplicity and schema order. The public comparator still
excludes logs; separate exact log/stdout checks cover record order, separators
and multiplicity.

The first external target is the entire unchanged sibling `loops_for.sas`.
All17 executable statements and both DATA steps run. The first step resets a
for each n, then appends n-1 stars:5 outer plus10 inner trips, final n=6 and i=6.
The second step begins with fresh blank storage and appends one star on each of
5 trips, ending at n=6. Each step emits the ordered staircase from one through
five stars. Each logical record has one trailing blank; emitted stdout adds one
newline. The complete result has no datasets and exactly10 records. Hand
accounting, independent base R, source/runtime, emitted execution and the CLI
agree. This is the twelfth complete external-program proof. Corpus source stays
in the sibling repository and is never copied into this tree.

| Program | Pin | SHA-256 |
| --- | --- | --- |
|loops_for.sas|source|88ad65e242857efa846bf34618e7b99ec4fba3dec8b3357033a9458759f39f87|
|loops_for.sas|complete result|94e92f8365b10f40383ed27e1e28e0ea9788bebbf34b1c7d87b5a5c03eb6549a|
|loops_for.sas|stdout|fa3e879dbbcc99fb4765c74272d862e330c8de985cbaac87b75db36ceab10699|
|trim_strip_capture.sas|source|b68612c0a80b501e0785547336210dd94c461c6f8df0c9c0a4e0107c986e7b32|
|trim_strip_capture.sas|complete result|6d279b226da98becf45fc40fb528fa670ca7c937b8ca57a08c994a57fa8561e9|
|trim_strip_capture.sas|stdout|d01d92ad8ef03cb7196048523a2b7df966d6475bcf1ee69476f3b64495a0bdea|

Result pins hash sorted compact JSON. Stdout pins include all trailing blanks
and newlines. Exact commit, receipts, workload comparisons and ownership live
in ignored `telemetry/SESSION_HANDOFF.md`. New fixture/suite registrations append
to the prior lists; no existing gate order or assertion is weakened.
