# Numeric DO OVER execution profile

Status: DS-040 repository/base-R evidence for principal/maintainer review.
This is a bounded legacy DATA-step profile, not live-SAS validation or a claim
about CASL, SCL, or arbitrary implicit arrays. The session handoff binds exact
commits, receipts and checkout ownership.

## Source characterization and representation

The SAS 9.3 [ARRAY statement](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/p08do6szetrxe2n136ush727sbuo.htm)
documents explicit dimensions, including an asterisk that infers the extent.
The SAS 9.2 [array reference](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000203460.htm)
documents declaration-before-reference and the asterisk variable-list form used
by SUM OF. These manual pages do not establish the full legacy implicit syntax.

Primary vendor example evidence: the DATA step in the SAS/IML 15.1
[ALPHA2 sample](https://support.sas.com/documentation/onlinedoc/iml/ex_code/151/alpha2.html)
declares an array without dimensions and assigns through its bare name inside
DO OVER. This is evidence about its DATA step, not IML execution support here.
The SAS-hosted original paper [Sevick, 209-2010, pages1-3](https://support.sas.com/resources/papers/proceedings10/209-2010.pdf)
provides the legacy characterization: absent or variable-valued declaration
subscripts are implicit; the default index is automatic _I_; a bare reference
selects the current member; DO OVER visits the members and cannot control an
explicit array. The paper is original author evidence hosted by SAS, not a
current SAS9.4 statement-manual entry. Sources consulted2026-10-27.

Design inference from those sources: preserve the distinction only where new
execution needs it. A dimension-free declaration used by DO OVER gains
`mode: implicit` alongside its existing name/lower/names fields. Explicit
dimensions, including `[*]`, cannot supply this marker. Plans without DO OVER
retain the old declaration shape and behavior. Legacy unmarked plans cannot
authorize new DO OVER execution because their original declaration mode is lost.

`do_over` carries name/body only. `array_current` and `array_current_set` carry
explicit references to that loop's array. Runtime offsets live outside the row;
they never become schema columns or receipt fields. Each loop invocation starts
at the first declared member. The plan and caller's catalog are not mutated.

## Admitted behavior

The declaration is unconditional and precedes the loop. It lists ordinary numeric
variables or an ascending numbered range. The total declared-element limit stays
1024 per DATA step, including overlaps. Declaration order controls iteration.
Writes through the current element update the actual variable immediately, and
ordinary writes to that variable are visible through the current element.
Sequential loops over overlapping arrays share those row bindings.

One loop level and one active current-element name are admitted. Bodies support
ordinary assignments, current-element assignments, bounded IF/ELSE chains,
existing scalar PUT forms and named-dataset OUTPUT. Store a current value in a
scalar before PUT or a function. SUM OF continues to use declared member order
and its existing missing-value contract. Current expressions use DS-039's finite
numeric/ordinary-missing storage, magnitude2147483647 and exact +/- arithmetic.
The32-level/128-node limits remain, with deterministic parsing inside these bodies.

Scratch variables and scratch array members reset per DATA row; inputs keep their
existing behavior. Each DATA step and run owns fresh loop state. _N_ counts input
rows, not element visits. Implicit output occurs once after the row completes.
Explicit OUTPUT captures the current row each time it executes and suppresses
implicit output for the whole step, even when its branch is skipped. Schema
discovery includes skipped assignments, later assignments and empty/filtered
inputs. Inherited numeric descriptors are preserved.

Declarations, incompatible descriptors, literal precision errors and malformed
plans fail before row execution, including empty input. Dynamic errors retain
selected-path timing. A late failure publishes no accepted partial datasets or
previously buffered stdout. Existing comparison and receipt behavior is retained.

## Refusal boundaries

Explicitly dimensioned controls, named implicit indices, direct _I_ access,
another implicit array's bare name, nested/conditional loops, indexed reads or
writes inside the body, and indexed references to the marked implicit array
remain refused. Shared-index multi-array semantics need separate characterization.
Existing programs without DO OVER keep their prior indexed-array behavior.

Character, multidimensional, temporary, initialized/retained arrays, PDV-order
lists, macro extents, member RETAIN/sum/BY/index state and parenthetical element
references retain their existing boundaries. LAG/DIF, sum-statement and dedicated
ROUND operations inside DO OVER, direct current-element PUT, PUT _ALL_, DATA
_NULL_ explicit OUTPUT and C++ execution are deferred. Existing output width and
numeric formatting limits are unchanged. This profile does not emulate _ERROR_.

## Execution evidence

[The semantic gate](../examples/verify_do_over.py) compares two hand-pinned alias
snapshot sequences and201 generated complete-runtime cases with an
[independent base-R witness](../examples/do_over.R). The witness traverses a named
vector and compares every output cell, including missing values, shuffled member
order and1024 elements. Eight size controls and three known-wrong alias/order
controls supplement the snapshots.

[The source suite](../saschi/test_do_over.py) covers source and serialized-plan
admission, both alias directions, overlapping arrays, resets, descriptors,
OUTPUT scheduling, skipped-path validation, atomic failure, parser budgets and
comparator controls. The installed-wheel gate exercises the new profile using
only the standard library.

The first complete-program target is the entire unchanged sibling corpus file
`loops_foreach.sas`. It fills ten cells with1 through10, leaves n at11, computes55
and emits the existing numeric-list record `55 ` plus a newline. Source bytes,
complete result and stdout are SHA256-pinned. The R witness consumes every source
statement and checks variable identities before independently executing its
schedule. Source runtime, emitted Python, the shared job and actual CLI agree.
No corpus source is copied into this repository. This adds one repository/base-R
complete-program proof; live-SAS validation remains outstanding.
