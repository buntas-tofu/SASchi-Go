# SORT input DROP and directed projection

Status: bounded repository and independent hand/base-R engineering evidence for
principal/maintainer use. Acceptance requires the current source-bound full
receipt. No live SAS, native diagnostic/schema golden or physical report claim.

DS-078 adds literal input DROP. DS-079 combines literal input KEEP or DROP with
per-key DESCENDING and optional stable NODUPKEY. The separate version2
`composed_sort` Step uses `sort-projection-composition-v1`. Older profiles retain
exact fields, defaults and limits; ascending KEEP alone still uses DS-075.

```sas
proc sort data=raw(drop=temporary) out=ordered nodupkey;
  by label descending score;
run;
```

A complete admitted program starts from character DATA and an empty catalog.
Each SORT has explicit DATA and fresh OUT names. Input selection has one literal
list of1..32 unique ordinary names. BY has1..8 unique names, each optionally
preceded by DESCENDING. All selected names must exist and all BY names must
survive. A selected schema must retain at least one character column.

The full original tables, descriptors and cells are validated eagerly, including
excluded columns and unused or empty paths. Projection preserves original
schema order, independent of the written KEEP/DROP list order. Eager validation
and exact descriptor order are explicit repository policies. They are not claims
about native SAS error timing or exact native descriptors.

The runtime reuses the existing projection and sorting engines after separate
admission. Numeric values follow the accepted exact INPUT converter, including
its admitted fractions. Ordinary missing, ASCII case and padded character values
use the existing comparator. DESCENDING reverses a key comparison without
reversing tied rows. NODUPKEY keeps the first input identity in each BY group,
including ties with equal or different payloads. Original source tables and
previous report snapshots remain intact.

Preflight propagates selected schemas and unsorted values without sorting or
deduplicating. Actual execution performs each SORT once. A new trace event
records input selection, ordered key directions, sorted source ordinals and kept
ordinals. It preserves original1-based input identity through projection.
Whole-job publication remains atomic on a later error or failed comparison.

Programs may join character DATA, fresh plain/directed SORT, older ascending
KEEP SORT, local TITLE and the existing default mixed PRINT. Limits stay64Steps,
1000rows/table,32columns,character widths1..64,2PRINTs and32TITLE statements.
PRINT retains its integer-only numeric renderer even though sorting accepts
admitted fractions. Projected DUPOUT, replacement, BY _ALL_, output selection,
numeric-only selected schemas and wider report caps remain deferred.

`examples/sort_composition_capture.sas` is an original complete source with
nonalphabetical descriptors, padded and blank characters, missing and negative
numbers, stable equal/unequal payload ties, seven SORTs and two snapshots.
Separately authored hand expectations and two base-R witnesses were qualified
and frozen before the runtime implementation. Two fixture gates compare the
complete dataset/schema/report result and59-event trace, generated and boundary
cases, portable/emitted execution, actual CLI comparisons and late failure.
The source suite independently exercises source/portable admission and limits.
These checks add no vendor or Roku proof. Seven existing vendor proofs and the
pinned Roku corpus retain their separate evidence.
