# Bounded grouped DATA control

Status: DS-060/DS-061 repository/base-R state and event evidence for principal
and maintainer review. Public branch acceptance remains separate. This document
does not claim live-SAS execution, physical-log fidelity or broader language
coverage. Design inferences were recorded before implementation.

## Primary characterization

The SAS DATA-step DO reference describes a simple DO/END group as a unit of
statements, commonly controlled by IF/THEN/ELSE. The iterative DO reference
separately describes index-controlled repetition, evaluation of start/stop/BY
before entry and iteration until the index passes stop. Its LEAVE example checks
that the current index is still10 immediately after leaving at10.

The DATA-step CONTINUE reference stops the current loop iteration and resumes
the next; it is restricted to a DO loop. LEAVE ends the current loop and resumes
after it. DO WHILE checks before a body and can have zero trips. DO UNTIL checks
after a body and therefore starts with one trip. Explicit OUTPUT writes an
immediate snapshot and suppresses implicit DATA-step output even when its action
is conditional. Sources were consulted2026-10-30:

- [Simple DO and other DATA-step statements](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/PDF/default/lestmtsref.pdf)
- [Iterative DO](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000201276.htm)
- [CONTINUE](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000289377.htm)
- [LEAVE](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000202782.htm)
- [DO WHILE](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000201927.htm)
- [DO UNTIL](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000201924.htm)
- [OUTPUT](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n1lltvbis7ye1an1eryo4leh2mck.htm)

Implementation inference: a simple group does not own an iteration. Transfers
propagate through groups and IF branches to the nearest iterative loop. LEAVE
bypasses its later body, index increment and condition tests. Counted CONTINUE
performs the normal increment; WHILE CONTINUE reaches its next top test; UNTIL
CONTINUE reaches the current bottom test. These interpretations receive separate
state/event witnesses. They are not represented as a captured physical SAS log.

## Separate portable contract

Design inference: a new `control_data` step retains exactly the existing Step
field set. Its first operation, at the DATA line, is `control_profile` with
`{"name":"bounded-control-v1"}`. Plans require exact integer version2.
There are no new default fields on older plans. New operations are `do_group`
with `body`, and `leave`/`continue` with empty arguments. IF and counted/WHILE/UNTIL
operations keep their existing structural payloads within this new step kind.
The marker requires an actual group or transfer. Older markers and step kinds
continue to refuse these operations.

The compiler selects this profile only for a plain group or transfer in an
actual DATA block. Parser tokens distinguish these statements from quoted text,
comments, variable names and opaque inline data. IF branches admit a simple group
or simple action, including a transfer. Conditional iterative-loop statements
remain deferred. Existing source without a new-control trigger retains the older
compiler path.

The first bounded surface is numeric scalar DATA, optionally reading one ordinary
numeric SET source, including a prior result table. Existing input/output
selection, literal RETAIN, sum statements, numeric list/named PUT, bounded literal PUT and OUTPUT are admitted
only after this profile validates their exact shapes. INPUT/CSV, arrays/DO OVER,
rounded numeric profiles, procedures and C++ composition are deferred. Labels,
GOTO, LINK, RETURN, STOP, Boolean grammar expansion and stochastic functions remain
outside this contract.

## Values, timing and resource policy

Design inference: operands, literals, selected imported values and reached
arithmetic results are integers with absolute magnitude at most2147483647, or
ordinary missing. Boolean, tagged missing, nonfinite, fractional and character
values refuse. Only existing addition, subtraction and multiplication syntax is
admitted. No new numeric function is added. Missing arithmetic and ordering follow
the existing scalar contract. Selected numeric descriptors and every selected
input value validate eagerly, including unused, skipped and empty paths. Ordinary
metadata keys and their order are preserved; nonempty formats refuse numeric PUT.

Only counted loops can nest within iterative loops, at most8 levels. Transparent
groups do not create loop ownership. WHILE/UNTIL remain single-level iterative
loops apart from groups and IF branches. Active counted indices cannot be written
in any descendant branch. Counted controls are captured on entry with the existing
bounded control evaluator. Control source keeps its integer literals, ordinary
names, _N_, parentheses and +/- grammar; decimal/scientific literal spellings
and multiplication in controls refuse. Each invocation reserves its full planned trip count
against a shared10000-counted-trip budget per DATA observation, even if LEAVE
later exits early. A constant10001-trip loop refuses even if its first action
would leave. WHILE/UNTIL retain10000 executed bodies per invocation. CONTINUE
consumes a body execution. A required10001st body refuses atomically.

The new profile additionally bounds mixed IF/group/loop nesting to32, expanded
operations to1024, structural containers to a finite acyclic tree before schema
walking. The raw portable tree additionally retains at most20000 expanded
container/value nodes and256 structural levels. Source has at most4096 ASCII
characters per statement and a2050-statement precheck before the exact1024-op
bound. Selected input observations are limited to10000, PDV columns to1..64, output observations
and logical records to10000 per step, and scheduled control/action events to
1000000 per step. These are tool policies, not SAS limits. Unmarked older plans
retain their previous limits; the cycle-safe new-operation detection scan adds
no global legacy-operation cap. Transfer ownership,
static expressions, descriptors and output discovery validate across all bodies,
including statements after unconditional transfers and skipped/empty/zero-trip
paths. Dynamic values remain lazy on skipped paths. LEAVE keeps the current
counted index; a natural final increment is checked only when actually performed.

A subset rejection is separate from LEAVE and CONTINUE. Group/IF propagation uses
distinct transfer signals. Explicit OUTPUT anywhere in the validated tree disables
implicit output, including unvisited groups. Snapshots deep-copy selected values.
Runtime catalog and portable plans are private; failed programs publish neither
accepted results nor buffered logical output.

## Independent evidence

The group gate has11 hand pins,160 generated complete-source/runtime/base-R
schedules and22 shared source refusals. The transfer gate has12 hand pins,
160 generated schedules and35 shared source refusals. These are per-gate units;
shared refusal sets can overlap. Each gate checks8 competing interpretations:
6 actual CLI dataset-comparison failures,1 exact logical-text damage and1 exact
event-trace damage. Failed comparisons retain observed artifacts and checksummed
receipts. The31-test source suite adds malformed portable, cyclic/deep/mixed
containers, exact resource boundaries, static/skipped/empty validation and old
profile controls. Earlier tests retain their exact source cases and order.

The independently authored base-R interpreter consumes source and raw typed
catalog transport, never Python plans. It schedules its own groups, retained
state, source reads, loop tests, transfers, snapshots and events. Comparisons are
exact for this integer domain, missing values, descriptor and observation order,
metadata, logical strings and traces. Unselected catalog values retain the old
generic normalization contract, including fractional numbers, tagged numeric
missing values, case normalization, duplicate-name refusals and encoding-aware
character widths. Generic numeric wire rendering uses17 round-trip digits;
integer control/event formatting is separate. Log limits apply per DATA step.

The original first-party `examples/grouped_control_capture.sas` consumes57
language statements across three DATA steps and five outer DATA observations.
It executes10 counted bodies and6 UNTIL bodies, takes9 snapshots, performs1 LEAVE
and6 CONTINUE transfers, writes4 logical records and yields172 ordered events.
The seed step writes3 observations. The measured step reads those3 observations
and writes5 snapshots; an imported missing sum target replaces its previous
value, scratch resets between rows and a retained accumulator carries. A fresh
step writes1 descending-loop result. The hand-authored state and event schedule,
independent R, source/runtime, emitted Python and actual CLI agree. Appended
procedure and truncated-source controls refuse; a late arithmetic failure after
earlier output/log actions publishes no accepted result or buffered stdout.

| Original artifact | SHA-256 |
| --- | --- |
| Source | a4355e2c445c3626d1b4c00dae698bfe6c896f54ccd47cc70aea58c48c2b08eb |
| Ordered canonical result | 7f456b0d33b1a0866fb112b1e5c13a5b6b923fd8c2a66817465f4f4c1a3745ba |
| Logical stdout | 3ff580a2f4bc01b60f96a822e39b8c0a4095d11c64d9a699411988da119e28e4 |
| Ordered canonical trace | 5a7240539b5a57cbb3ca3615b94b9d378d17accf8069c6df24ac99db9a5da971 |

JSON pins use insertion order and compact separators. Eleven exact earlier
source refusal cases now select the separate control profile. Their old DATA
kind and all three earlier numeric markers still refuse, and the older independent
R witness still refuses. Four no-variable transfer sources retain their source
refusal because zero-column DATA output is uncharacterized. Conditional iterative
statements and untriggered nested IF remain outside admission. No source was
replaced with another unsupported example. No complete external-program proof
or whole-SAS coverage percentage is attributed to this pair.
