# Directed stable SORT and descriptor-order BY _ALL_

Status: bounded repository/base-R contracts for maintainer use, conditional on
source-bound full verification. No live SAS, physical output, all-runtime or
whole-language equivalence. Logical report text retains its existing named policy.

DS-073 adds per-key DESCENDING in directed-sort-v1. DS-074 adds sole BY _ALL_
with NODUPKEY in descriptor-sort-all-v1. Existing ascending SORT and NODUPKEY
remain separate preserved contracts. These new forms require a complete program
with a genuinely parsed character_data producer, empty initial catalog and
left-to-right lineage. Comments, quoted strings and opaque records do not select
the family. Numeric-only legacy DATA and supplied-catalog programs do not gain
DESCENDING through this profile.

Each new SORT has explicit DATA and a fresh OUT destination, exactly one BY and
explicit RUN. Directed BY has1..8 unique ordinary names, each optionally preceded
by DESCENDING, and at least one descending key. The modifier applies only to its
following key. Stable ties preserve input row identity. Optional NODUPKEY keeps
the first stable BY-key occurrence. Sole BY _ALL_ requires NODUPKEY, has no
direction modifier and expands1..32 columns in ordered descriptor order.

## Source evidence and repository mapping

The [SAS9.4 Language Reference: Concepts, Sixth Edition](https://documentation.sas.com/api/docsets/lrcon/9.4/content/lrcon.pdf),
printed62, describes variable-list order by compiler encounter, with a numbered
range exception. Printed69 identifies _ALL_ as the special list of defined
variables. Printed46 relates variable position to definition order. The cover
identifies April2023 and9.4-P10:lrcon. The [Base SAS9.4 Procedures Guide](https://documentation.sas.com/api/docsets/proc/9.4/content/proc.pdf?locale=en),
Seventh Edition, printed2409, Example7, corroborates NODUPKEY with BY _ALL_.
These are citation-only explanatory sources, not a live execution golden.

The repository maps INPUT definition order to ordered schema descriptors.
Resolution does not sort column names or inspect first-row key order. The
nonalphabetical original fixture distinguishes that policy even though the
official all-column target's descriptor order happens to be alphabetical.
CAS, arbitrary engines and maintenance-wide behavior are outside this mapping.

## Portable shape, values and limits

The exact version2 bounded_sort Step keeps existing Step field names and empty
legacy metadata. It has one bounded_sort header-line operation with exact args
profile,keys,nodupkey,source_lines. Explicit keys have exact name/descending
boolean fields; the all-column profile has an empty keys list and true nodupkey.
source_lines records BY and RUN positions. The legacy Step.by stays empty and
Step.nodupkey stays false. New markers cannot hide in earlier operations.

The complete family retains at most64 Steps,1000 rows per table,32 columns,
character widths1..64,2 PRINTs and32 TITLE statements. Directed lists have at
most8 keys; _ALL_ expands at most32 columns. All descriptors and cells validate
before empty-row shortcuts. Input is the existing strict printable-ASCII
character/numeric record contract. Numeric values retain its exact converter
domain, including representable fractions and ordinary missing. Sorting strips
only trailing character padding for comparison and preserves the stored cells.
Ordinary missing sorts first ascending and last descending. Report rendering
independently retains its existing integer-only numeric bounds.

Legacy ascending SORTs inside the family keep their old serialized shape and
stable survivor semantics. New SORT destinations must be fresh even for empty
tables. Source datasets remain unchanged, and earlier report snapshots remain
immutable across later SORTs. Runtime and emitted Python buffer all results;
late execution or comparison failure publishes no accepted partial artifact.

## Independent evidence and whole sources

The original directed and _ALL_ fixtures have separate Python gates, a base-R
twin and source/portable tests. They exercise mixed directions, ties with unequal
payloads, blank padding, ordinary missing, exact fractions, nonalphabetical
descriptors, empty inputs, invalid values, known-wrong comparisons and atomic
failures. The whole official witnesses have independent hand and full-source R
lexers, complete datasets/descriptors/reports, statement/event accounting,
runtime/emitted execution and actual CLI comparison controls.

Three additional identities in [the vendor manifest](vendor-benchmark-manifest.json)
pin unchanged programs from sassoftware/sas-code-examples commit
579e057f90cd699f744fd6a1c8acaf9243f7ff67:

- SORT2,1854 bytes: Subject ascending,Score descending,14 inline rows,two reports.
- SORT3,1856 bytes: NODUPKEY with BY _ALL_,14 inline rows,13 survivors,two reports.
- SORT6,1886 bytes: Name/descending Score then existing Name NODUPKEY,13 inline
  rows,6 survivors,no reports. Both intermediate and final datasets are checked.

These witnesses remain separate vendor proofs, conditional on passing full
gates; they do not add a Roku proof or change its56-program denominator.
Vendor bodies, LICENSE text and complete derived results stay outside Go.
Explicitly prepare the immutable external cache before offline verification:

```sh
python tools/prepare_vendor_sources.py
python verify_all.py
```

NOTSORTED, NOEQUALS, SORTSEQ/linguistic/non-ASCII collation, tagged missings,
NODUPRECS, DUPOUT, input projection, external engines, new in-place SORT forms,
additional report invocations, broader informats and missing-data recovery remain
refused in these profiles. Duplicate-output partitioning needs a later contract.

DS-075 separately admits bounded input KEEP with ascending BY under the
[input KEEP contract](SORT_INPUT_KEEP.md). The directed/ALL profiles above retain
their projection refusal; duplicate-output partitioning remains deferred.
