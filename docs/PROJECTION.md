# Bounded KEEP/DROP projection

Status: DS-047/DS-048 repository/base-R evidence for principal/maintainer review.
The profile proves descriptor selection, DATA observations and supported logical
output records. Live-SAS validation and physical diagnostic fidelity remain
outstanding. These bounds do not characterize every SAS variable-list form.

## Characterization and representation

The primary SAS [KEEP statement reference](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000202978.htm)
and [DROP statement reference](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n1capr0s7tilbvn1lypdshkgpaip.htm)
describe declarative output selection. A declaration can appear anywhere in a
DATA step and applies to its output datasets. Variables excluded from output
remain available to calculations and PUT. These references advise against using
KEEP and DROP statements together in one step.

The [SAS variable-selection concepts](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a000695119.htm)
distinguish dataset-option timing. KEEP=/DROP= on an input selects variables
before they enter the PDV. On an output it selects variables as they are written.
The [KEEP= reference](https://support.sas.com/documentation/cdl/en/ledsoptsref/69751/HTML/default/p0vw9lyyxk1cxkn0zzfemrsr3t9a.htm)
describes this same input/output distinction. Sources consulted2026-10-29.

Design inference: store a declaration as a version2 `projection` operation with
exactly `mode`, `names` and `scope`. The scope is `statement`, `output` or `input`.
No default field is added to existing plans. An output option is the first
operation on the DATA header's source line. An input marker immediately precedes
its single driving SET read on that read's source line. Runtime validates marker
shape and placement independently of compiler admission.

## Accepted profiles

DS-047 admits one top-level KEEP or DROP statement. DS-048 separately admits one
KEEP=/DROP= option on the sole DATA destination and one on the single driving SET
source. The input choice can compose with one output choice. A statement and a
DATA output option in the same step are refused rather than silently combined.

Lists contain1..64 unique ordinary names, case-insensitive ASCII, with a maximum
name length of32. Ascending numbered ranges require a shared prefix, unpadded
positive suffixes1..64 and a total expanded list of at most64 names. For example,
`keep x1-x3 result;` selects four already discovered columns. List order never
reorders the descriptor. These bounds are implementation policies.

Output selection resolves after complete static PDV discovery, including future
assignments, uninitialized references and skipped branches. The projection list
itself creates no variable, type or width. Earlier explicit OUTPUT snapshots and
implicit output use the same final descriptor selection. All PDV variables stay
available for execution, retained state and supported PUT, including excluded
columns. Explicit OUTPUT retains its existing step-wide suppression of implicit
output even when its branch is skipped.

Input selection resolves against the normalized supplied descriptor. It selects
both values and descriptors before DATA discovery and row execution. An excluded
input name referenced later can be introduced afresh as an ordinary numeric
variable with a missing initial value; it does not inherit the input descriptor
or input retention. The supplied catalog remains intact. Full catalog validation
precedes projection, so an excluded column cannot hide invalid values, malformed
metadata or mismatched rows.

Selected columns retain descriptor order, type, byte length, label and format.
Dataset encoding and label survive. Empty input still produces the complete
selected schema and no observations. Unknown selection names and selections that
would leave zero columns refuse, including on empty or skipped paths. These
refusals are conservative profile policies rather than emulation of SAS warning
or recovery behavior. Late failures publish no accepted result or buffered stdout.

Output projection composes with the previously gated scalar, array, counted-loop,
inline INPUT, retained, BY and WHERE paths where their existing restrictions hold.
The input-option profile excludes MERGE, initial lookup, BY and WHERE. Broad input
timing and option-order composition require separate witnesses.

## Evidence and frontier

The projection gate checks six hand pins,300 constructive independent-R cases
across all three source timing forms,26 shared refusals and four competing
interpretations. The29-test suite covers portable-plan attacks, empty/skipped
paths, metadata, arrays, state reset, input normalization, atomic failure and
actual CLI execution. An independent R interpreter consumes every statement in
the original25-statement `examples/projection_capture.sas`, comparing three
complete datasets, eight observations and two logical log records with hand pins,
source/runtime, emitted Python and CLI execution.

Prefix lists, descriptor-order double-dash ranges, special lists, name literals,
duplicate selections, multiple statements/output choices, conditional or nested
declarations, zero-column results, general dataset options, multiple DATA
destinations, PROC options and C++ projection remain refused. PUT _ALL_ retains
its prior scalar-only profile. LABEL, FORMAT, INFORMAT, ATTRIB and numeric LENGTH
declarations are outside this slice; existing descriptor transport does not
authorize their source syntax. The separate B5 numeric profile requires its own
composition evidence before combining with projection.

Eight existing sibling corpus KEEP statements now route to bounded selection,
including numbered lists. The sole DATA DROP= form is recognized, but its full
source still requires other options and procedures. Four DROP occurrences belong
to the unsupported DS2 priority-queue program. No new complete sibling-program
proof is claimed. The Fibonacci file's first DATA step still does not prove the
FCMP recursion later in that file. No corpus source was changed or copied here.
