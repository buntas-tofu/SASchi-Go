# Bounded scalar flow

Status: DS-064/065 repository and independent base-R evidence for maintainer
review. These are explicit source-execution profiles, not live SAS capture,
physical-log fidelity or whole-language equivalence. The approved pair authority
is recorded in `telemetry/cluster-d2b-d3b-20261031/authorization.json`.

## SAS characterization and implementation policy

Official SAS documentation defines statement labels as local DATA-step targets,
forbids duplicate labels in one step, and permits a labeled null statement.
A statement label differs from variable LABEL metadata. See the
[statement-label reference](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000204328.htm).
This profile keeps label and PDV namespaces separate, including a label and
variable both named `gcd`.

[GOTO](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/p04lue2yzjvc8xn1603l5kqlw62d.htm)
transfers to a label in the same step. An active LINK retains its caller through
a subsequent GOTO. [LINK](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n132s7tapddkc8n1my90ekgo4v0q.htm)
and RETURN resume at the statement immediately following LINK. SAS permits
nested LINK calls; admitting one active caller here is a conservative tool policy.

[RETURN](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000201969.htm)
without an active LINK restarts the DATA-step iteration and performs implicit
OUTPUT unless explicit OUTPUT elsewhere suppresses it. Every step has an implied
final RETURN. The implementation resumes an active caller at physical step end.
It refuses an explicit unlinked RETURN reachable without INPUT. This conservative
policy is recorded in the immutable pair decision
`DECISION-01-return-without-input.json`; it is not a SAS prohibition. Static
reachability follows both IF branches and conditional-loop possibilities, even
when a literal predicate is false. A routine tail after an unconditional main
STOP is allowed when its RETURN is reached with a caller active.

[STOP](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/p02jy612cym9oxn10i19cbewlrdf.htm)
ends the current DATA step successfully and continues to subsequent steps. It
omits the current implicit observation. Earlier explicit snapshots and logical
PUT records survive. Runtime failure has a different contract: it publishes no
accepted program result or buffered stdout.

## Portable profiles and admission

A new exact version-2 `flow_data` step retains the existing Step field set.
Its first operation is `flow_profile` at the DATA line, with exactly
`{"name":"scalar-jump-v1"}` or `{"name":"scalar-link-v1"}`. No profile field is
added to earlier plans. New `label`, `goto` and `link` operations have exactly
`{"name":"ordinary_lowercase_target"}` arguments. STOP and RETURN have empty
arguments. Existing scalar, IF, group, counted/WHILE/UNTIL, projection, retained,
PUT and OUTPUT operation shapes are reused under this separate validator.

`scalar-jump-v1` admits local labels, GOTO/GO TO and STOP first.
`scalar-link-v1` additionally identifies actual LINK/RETURN or numeric INPUT/MOD
composition with a real flow trigger. Strings, comments and opaque input records
do not select the profile. No-trigger sources use the earlier compiler unchanged.
Older profiles independently refuse hidden new operations, including empty and
skipped paths. The legacy detector adds no size limit to earlier accepted plans.

Labels are top-level, unique after ASCII case normalization, and resolved within
one step before execution. GOTO and LINK may be top-level or direct IF actions,
but cannot originate inside transparent groups or iterative bodies. No label
inside such a body can become a jump target. STOP and RETURN can propagate out of
IF, groups and loops; they bypass remaining bodies, counted increments and loop
tests. This distinction also admits the exact earlier STOP-in-group source only
under the new flow profile.

LINK permits one unique destination label. All call sites precede its label;
the target region contains no LINK, including dead code. A bounded static caller
analysis also rejects GOTO paths that would reach another LINK with a caller
active. Runtime enforces the same one-frame limit. A call changes the program
counter and stores a resume address, without creating a record or resetting PDV.

One first top-level numeric INPUT may use CARDS/DATALINES. Its operation retains
the existing names/records/data_line shape, with data_line naming the first
physical record line. INPUT and DATALINES may share a code line. Record decoding
uses the unchanged exact converter: 1..32 fields, at most 10000 printable-ASCII
physical records of 80 bytes, default FLOWOVER, release after a completed read,
and no incomplete EOF observation. Every consumed value must also satisfy this
integer profile, including a value in an incomplete observation. Unread tail
fields remain unread. Jumps to or before INPUT are refused. No ranges, CSV,
INFILE, external input, SET, array, Boolean or rounded-profile composition is added.

Numeric operands and reached results are ordinary missing or exact integers with
magnitude at most 2147483647. Existing plus/minus/multiply and the named integer
MOD helper are supported. MOD retains its existing refusal of missing arguments
and zero divisor. This does not expand any helper's domain or add a helper.
All 149 semantic helper definitions and reference bytes remain unchanged.

Static discovery includes retained/INPUT/assignment/control names and expression
operands, including dead source. Labels never create columns. PUT names must
resolve against the complete unformatted numeric PDV. Fresh output descriptors
are ordinary numeric descriptors, in PDV order. Bounded KEEP/DROP preserves that
order. Explicit OUTPUT anywhere suppresses implicit OUTPUT across the step.
Snapshots, supplied catalogs and serialized plans are not mutated.

## Independent limits

These are repository resource policies, not SAS language limits:

- 1..64 PDV columns, at most 64 local labels, 1024 expanded operations.
- 32 combined IF/group/loop containers, 32 expression levels, 128 arithmetic/call
  nodes, 20000 portable structure nodes and raw depth 256, with cycle refusal.
- At most 20000 static caller-analysis states and 100000 executed instructions
  per step. Each operation dispatch, loop test, counted increment and implicit
  caller return charges an instruction. The exact 100000 boundary has an
  independently computed positive and a next-dispatch refusal.
- Counted loops retain eight-level counted-only nesting, distinct active indices,
  no own-index controls, and full-trip reservation against 10000 trips per outer
  observation, including early LEAVE/STOP. WHILE/UNTIL retain 10000 bodies per
  invocation. GOTO cannot reset these budgets.
- At most 10000 snapshots and PUT records per step, 64 logical PUT columns and
  1000000 diagnostic events per step. All buffers remain private until success.

Static syntax, names, expressions, call ownership and label resolution are checked
before an empty INPUT or skipped path can hide an invalid operation.

## Evidence

`flow_control_capture.sas` is an original 31-language-statement, three-step witness:
five outer observations, four snapshots, four logical records and a hand-pinned
120-event schedule. It proves backward GOTO, STOP, caller resumption, retained sums,
scratch reset, input record advancement, projection/order and successful prior
publication. `flow_control.R` parses full source independently and computes its
own program-counter, input and caller schedule. Earlier first-party independent R
scalar/catalog/decimal routines are reused; Python plans are never read by R.

The complete unchanged sibling `flow_control_structures.sas` has 27 language
statements, two steps, four outer observations and 58 logical PUT records. The
first step produces 55 triangular records and ends at n=1,p=11 with STOP. The
second computes GCD(2,15)=1, GCD(533,221)=13 and GCD(8,44)=4 using 3/4/3 WHILE
bodies. All 698 events and the entire ordered result/log are hand/R/runtime/emitted
pins. Actual CLI execution and strict complete-source/result/stdout/trace digests
are checked by the scalar-link gate. The corpus remains in the sibling data
repository; no external source is copied into tracked files here.

Separate `scalar-jump` and `scalar-link` gates register semantic cases, generated
full-source schedules, shared refusals, six actual failing CLI dataset comparisons,
an exact logical-text damage and an exact caller-trace damage. Portable malformed,
static/skipped/empty, label/caller, numeric, resource and late atomic-failure checks
live in `saschi.test_flow_control`. Earlier gates keep their order and strength.
The exact old `data d;x=1;do;stop;end;run;` source gains new hand/R/runtime/emitted
acceptance while retaining its old compiler, bounded-control and R refusal.
Broader call graphs, jumps across structured bodies, no-INPUT unlinked RETURN,
zero-column DATA, arrays, rounded values, random streams and physical SAS log
formatting remain separate work.
