# Typed expressions with state and snapshots

Status: principal-approved local composition work for maintainer review. Current
registrations require a matching source-stable full receipt and both unchanged
1k workload reports. Complete independent hand/base-R originals, not native SAS
validation or publication authority. UI changes are deferred.

The separate ordinary version 2 `stateful-expressions-v1` profile qualifies
selected joins between existing typed expressions and DATA-step scheduling.
Source compilation preserves accepted older plans first. New marked steps have
one driving SET and one fresh named output. Portable validation independently
checks exact fields, declarations, read order, types and resource bounds before
legacy walkers. Inputs and plans remain unchanged; late failures publish no
accepted partial result or emitted stdout.

The contextual cohort is ten existing functions: UPCASE, COMPBL, STRIP, DEQUOTE,
NOTALNUM, LENGTHN, N, ABS, MAX and IFC. Their type, missing, width, temporary-byte
and argument-role policies remain those of the [typed expression contract](FUNCTION_EXPRESSIONS.md).
No scalar registry name is added. Other functions retain their own profiles.

## Decision groups and explicit snapshots

DS-123 registers typed IF/THEN/ELSE decisions, nested simple DO/END groups,
assignments, existing bounded logical PUT and explicit OUTPUT. Grouping adds no
iteration. ELSE binds to its nearest unmatched IF. Every reached pure predicate
operand is domain-checked; selectors retain eager choices. Static literal/type/
width errors validate on skipped and empty paths. Dynamic faults in unreached
statement bodies remain unreached.

OUTPUT snapshots the full current row. Later assignments cannot change prior
observations. Explicit OUTPUT anywhere suppresses implicit output, including an
OUTPUT in a skipped branch. Unnamed OUTPUT and the single declared DATA target
are admitted. Skipped and later assignments still form their descriptors before
any snapshot. Input table metadata and column descriptors survive the new step;
character declarations retain their documented width override behavior.

The [original program](../examples/stateful_decisions_capture.sas) has seven hand
snapshots across six input observations and six logical records. It covers
independent reasons, two observations for one input, post-snapshot mutation,
missing inputs, blank/quoted identifiers and a later field that remains missing
in earlier snapshots. Complete ordered hand/R/runtime/emitted/CLI comparisons,
30 generated whole R catalogs and actual CLI mismatch controls are registered in
[the gate](../examples/verify_stateful_decisions.py). The
[source suite](../saschi/test_stateful_decisions.py) checks exact portable shape,
resource boundaries, empty/skipped paths, profile coexistence and late faults.

## Numeric retention

DS-124 adds top-level numeric RETAIN with one literal initializer per fresh name.
An initializer is an exact finite integer within +/-1,000,000 or ordinary missing.
Its value applies once before the first input observation, even when RETAIN
appears later in the source. Descriptor order follows the first declaration/use.
At most 16 explicit retained names are admitted. Character, absent, computed and
duplicate explicit initializers refuse; imported-state collisions refuse even
on empty input. A retained name remains numeric throughout the step.

Retained values carry to the next input observation. Ordinary row scratch resets
to missing. Reached retained assignments and known constant assignments obey the
same integer/missing bound. Skipped dynamic assignments remain unreached. State
resets independently for each step and each run. The [complete retention original](../examples/stateful_retention_capture.sas)
has eight snapshots, including missing scratch and carried peak/seen/pending
values. Its [hand/R gate](../examples/verify_stateful_retention.py) compares 30
whole catalogs; the [source suite](../saschi/test_stateful_retention.py) checks
later-position declarations, collisions, bounds, portable fields and atomic
failure. Stage 1 portable validation still refuses retention explicitly.

## Expression sum statements

DS-125 adds fresh numeric sum targets with an existing typed expression as the
contribution. Each sum target implicitly starts at zero and retains its value,
even when every contribution action is skipped. An explicit numeric RETAIN
initializer overrides that default, including a later lexical declaration.
Implicit and explicit state share the 16-name cap. Contributions and accumulated
results obey the same exact integer/ordinary-missing state bounds. Missing values
contribute zero in accumulation. Ordinary expression addition still propagates
missing. This is a separately pinned repository/base-R contract.

Sum actions are reached statements: skipped dynamic contributions remain
unreached, while static known type/domain faults refuse on empty/skipped paths.
A sum action consumes one scheduled action. Assignment resets and multiple
contributions preserve their source order and snapshot timing. The [complete sum original](../examples/stateful_sums_capture.sas)
compares implicit totals, explicit offset and ordinary addition through its
[hand/R gate](../examples/verify_stateful_sums.py) and
[source suite](../saschi/test_stateful_sums.py), including late atomic overflow.
Earlier stage validation continues to refuse sum operations.

## Ordered numeric BY groups

DS-126 adds one imported numeric BY key in ascending, missing-first order. Every
key is ordinary missing or a finite number within +/-1,000,000. Whole-input
ordering validates before any body action, including a disorder late in input.
Character, unknown, nonfinite, tagged, multiple, descending and NOTSORTED keys
refuse. Empty input still requires the numeric key descriptor. The runtime does
not sort; observations within each tie retain their original order.

FIRST.key and LAST.key are read-only temporary numeric expression leaves for
that key. A singleton sets both flags. Missing-key observations form the first
group. Flags and internal type/evaluation proxies never enter stored schemas or
snapshots; explicit ordinary assignments such as f=first.batch store f only.
Nested decisions, explicit reset actions, global accumulation and snapshots
retain their prior timing. The [complete grouped original](../examples/stateful_groups_capture.sas)
covers resets, singleton/missing cases and two snapshots for one input, with a
[hand/R gate](../examples/verify_stateful_groups.py) and
[source suite](../saschi/test_stateful_groups.py). Earlier stage validation
continues to refuse BY/automatic leaves. Numeric keys may be fractional; retained
numeric state keeps its stricter integer bound.

## Complete record-quality audit and review queue

The [unchanged complete audit program](../examples/record_quality_audit_capture.sas)
combines normalization, independent identifier/measurement reasons, reason-level
snapshots and a separately dispatched ordinary filtering step. All seven input
records and both complete output tables are pinned: nine audit observations and
six review observations. Records with two failures keep both reasons in source
order. ACCEPT rows remain in the audit. Padded keys are stripped before NOTALNUM
inspects their actual identifier bytes.

The [complete hand/base-R gate](../examples/verify_record_quality_audit.py) compares
every field, ordered descriptor, row and metadata attribute through runtime,
emitted Python and actual CLI, plus 30 whole generated catalogs and six actual
CLI mismatch controls. The [target source suite](../saschi/test_record_quality_audit.py)
checks complete row fates, empty input, all-missing measurements, profile
coexistence and a late computed-key overflow after valid output and an earlier
completed DATA step. Component acceptance alone does not accept this target;
its matching full receipt and both unchanged workloads remain required.

## Complete batch reconciliation and review list

The [unchanged complete reconciliation program](../examples/batch_reconciliation_capture.sas)
combines normalization, first-row resets, retained counts/totals, conditional
expression contributions, last-row snapshots and a separately dispatched
ordinary review filter. Its nine input observations form five complete batch
summaries and three review observations. The original last invalid observation
makes scratch delta missing while retained net/magnitude stay two. All inherited
last-row input fields and descriptors remain part of the expected output.

The [complete hand/base-R gate](../examples/verify_batch_reconciliation.py) checks
both whole outputs through runtime, emitted Python and actual CLI, plus 30 whole
generated catalogs and six actual CLI mismatch controls. The
[target source suite](../saschi/test_batch_reconciliation.py) checks complete
summary/review fates, missing-key singletons, exact limit boundaries, scratch
reset, unsorted input and accumulated overflow after an earlier completed group.
These late failures publish no partial accepted job or emitted stdout. This
second target requires its own matching full receipt and both unchanged
workloads after the first target is accepted.

All four components and both original targets are registered in order. Their
six complete hand/R expectations, R implementations and source bytes were frozen
before translator implementation. The gates retain those bytes and compare all
stored fields, descriptors and logical records. This wave adds four bounded
composition rules and no scalar registry name or runtime dependency. Existing
profiles, capability objects, old fixture order and workload assets retain their
prior contracts. These are repository/base-R results, not native SAS validation
or a new external-program execution claim.

## Resource and remaining boundaries

The marked-step limits are 256 expanded operations, 128 static call sites, four
nested calls, expression/action depth 16, structural depth 64 and 16,384 containers.
Programs have at most 16 ordinary DATA steps and 4,096 provenance rows. Marked
steps have at most 64 stored columns, 10,000 input/output observations, 10,000
logical records and 1,000,000 scheduled actions. Cycles and oversized structures
refuse before recursive validation. These are tool policies, not SAS limits.

Each reached executable action, IF/group and input read consumes one scheduled
action; an implicit snapshot consumes one additional action. Explicit snapshots
are counted through their OUTPUT action once. Declarations and markers consume
no runtime action. Static operations count every expanded descendant, even when
skipped. All dynamic counters reset per marked step.

Filtering inside the marked step, multiple inputs/destinations,
replacement, arrays, loops, queues, macros, callbacks, procedures, SQL/C++ and
broader arithmetic remain held. Older separately qualified source continues to
use its existing plan and gates. For example, an older counted-loop ABS source
stays valid in its original profile while the new profile refuses iterative DO.

The [approved wave contract](NEXT_DATA_STEP_WAVE_5.md) records the complete ordered
scope: four separately accepted components followed by BOTH original finish
programs. Their hand/R oracles were frozen and qualified before translator work.
An added registration alone does not claim completion of a later stage.
