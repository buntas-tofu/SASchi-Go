# Nested and computed counted-loop profile

Status: DS-041 repository/base-R evidence for principal/maintainer review.
This is the bounded A2 implementation, not live-SAS validation or a new complete
external-program proof. The local handoff binds exact commits and receipts.

## Source characterization and representation

The primary [Base SAS iterative DO reference](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000201276.htm)
and [SAS 9.3 Statements Reference, pages65-67](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/PDF/default/lestmtsref.pdf)
describe numeric expressions for start, stop and BY. They evaluate these controls
before execution, preserve captured stop/BY despite body changes, and warn that
index changes can affect termination. The index is an ordinary output variable.
The [vendor tutorial](https://www2.sas.com/onlinetutor/linklib/doloop.htm) also
describes the default increment and termination after passing the bound. Sources
consulted2026-10-28. These are DATA-step sources, not SCL or IML loop contracts.

Design inference: capture all three controls on every loop entry, then execute
with those values. Entering an inner loop again captures its controls again.
Own-index references in any control refuse, avoiding an unproved dependency on
evaluation order relative to index initialization. Ancestor indices are allowed.
Body writes to any active index, including skipped IF branches, refuse. Array
members remain excluded as indices, so aliases cannot bypass this restriction.

Existing single-level literal plans retain the exact DS-026 shape and helper.
New computed or nested loops add only `profile: bounded` to `do_counted` arguments.
Every loop in a nested tree carries this marker; nested index declarations occur
immediately before their loop. Legacy unmarked plans do not authorize nesting or
computed controls. Runtime validation checks this independently of compilation.

## Controls, scheduling and resource bounds

Syntax remains `DO index=start TO stop [BY increment]; ... END;`. Controls admit
signed ASCII integer literals, ordinary numeric variables, `_N_`, parentheses,
unary signs and exact integer addition/subtraction. Every control operand and
intermediate result must be a finite integer of magnitude at most2147483647.
BY must be nonzero. Decimal/exponent literal spellings, missing/tagged values,
character coercion, calls, array controls, multiplication and division refuse.
Compute a separately gated function or array result into a scalar first.

At most8 counted levels may be active, with distinct indices. Each DATA row has
a shared10000-iteration budget across A2 loops, counting outer and inner trips.
Each invocation reserves its own trip count before executing its body; zero-trip
invocations reserve none. Existing independent literal-only roots retain their
DS-026 per-loop limit. Limits are tool policy, not SAS language limits.

Control parsing has a4096-character/128-token limit per control and32 expression
levels. Plans admit128 control-expression nodes per DATA step and256 operations
per bounded loop body, including descendants. Malformed trees and excessive
depth refuse before recursive execution. Internal counters never become columns,
and reset for each row, DATA step and run.

Normal completion leaves the index at the first value past stop, even when that
final value exceeds the control bound. A reached zero-trip loop leaves start.
An inner loop never reached does not initialize its index at runtime. Schema
discovery still visits its declarations, control references and body. `_N_`
counts DATA rows. Scratch values reset and supplied input descriptors survive.

Existing assignments, indexed array reads/writes, direct ROUND, retained sum
statements and bounded IF/ELSE actions compose in counted bodies. PUT keeps its
existing scalar formats. Explicit OUTPUT snapshots each execution and suppresses
implicit output for the entire step, even when skipped. Future/skipped columns
appear in snapshots with their current missing/blank values. Empty and filtered
inputs still validate descriptors, literal errors and plan shape. Dynamic control
errors occur only when reached and identify the loop source line. Any failure
publishes no accepted partial result or previously buffered stdout.

## Evidence and remaining boundaries

[The semantic gate](../examples/verify_counted_nested.py) compares4 hand control
pins,212 independent R control/budget cases and303 complete runtime/R schedules.
The [original full program](../examples/counted_capture.sas) has six hand-pinned
row snapshots, complete source/result/stdout hashes and an independent
[base-R witness](../examples/counted_nested.R). It combines mutable captured
controls, inner recapture, numeric aliases, output scheduling and final indices.
[The source suite](../saschi/test_counted_nested.py) checks source, emitted and
actual CLI execution, wrong-value/order/multiplicity/schema controls, resets,
empty inputs, boundary budgets, malformed plans and atomic late failures.
The isolated installed wheel also executes nested computed loops with only the
standard library. Existing gates retain their order and assertions; exact former
refusal sources promoted by A2 now have execution or dynamic-failure assertions.

Conditional/grouped loops, WHILE/UNTIL/OVER nesting, active-index mutation,
LAG/DIF in A2 bodies, declarations other than generated nested index declarations,
body input operations, MERGE, DATA _NULL_ explicit OUTPUT, PUT _ALL_ and C++ remain
deferred. DO OVER stays single-level. Existing numeric-array limits and all output
and receipt contracts remain in place.

The unchanged100_doors.sas now compiles, but runtime refuses its mixed
literal/numeric PUT before any accepted output. It is not an eleventh corpus
proof. A3 must separately characterize and prove that output profile. The full
loops_for.sas still needs TRIM/STRIP. No corpus source was copied into this tree.
