# SORT duplicate partition, owned replacement and three logical reports

Status: DS-076,DS-077 and ST-024 bounded repository/independent hand/base-R
contracts for maintainer use, conditional on a current source-bound full receipt.
No live SAS, native duplicate-stream ordering, physical SAS/ODS or maintenance-wide
applicability is established.

## Source and ownership

The distinct sort-dupout-v1 family requires a genuinely parsed preceding character
DATA producer and an empty initial catalog. One literal PROC SORT DATA=input
[OUT=fresh] DUPOUT=fresh NODUPKEY header, one1..8-name unique ascending BY list and
explicit RUN define the new partition. A fresh survivor OUT is DS-076. Omitted
OUT is DS-077 only when input is a prior SORT survivor destination in this job.
A producer or earlier DUPOUT side output does not confer replacement ownership.
Explicit OUT=input remains refused in this family. Duplicate destination must
be fresh and distinct from both input and survivor, including empty tables.

Partition stable BY-sorted input observation identities into the first survivor
of every group and all removed observations. Keep complete row multiplicity,
ordered descriptors, padding, ordinary missing and stored cells. Equal-valued
observations still have separate identities. Both destination tables are computed
before the local catalog is updated. Original datasets and previously rendered
report snapshots remain intact across a later controlled replacement.

The [Base SAS9.4 Procedures Guide, Seventh Edition](https://documentation.sas.com/api/docsets/proc/9.4/content/proc.pdf?locale=en),
printed2377, describes DUPOUT with NODUPKEY and EQUALS tie stability; printed2381
describes omitted OUT replacing the input after successful sorting. These sections
are explanatory citations, not an execution capture. Exact removed-stream ordering
across runtimes is not established here. This repository explicitly emits removed
observations in the stable sorted-stream order used to select survivors. An
independent original witness distinguishes this mapping from original encounter
order; matching the official target alone cannot establish native equivalence.

## Separate portable and report contracts

The exact version2 duplicate_sort Step retains existing field names and empty
legacy metadata, with one same-kind header-line operation. Its exact args are
profile,by,dupout,replace,source_lines; source_lines contains BY and RUN lines.
Step.name is fresh survivor OUT when replace=false and equals input otherwise.
NODUPKEY is mandatory in the profile; legacy Step.by remains empty and
Step.nodupkey remains false. Program admission proves owned replacement lineage.
The pure execute_partition helper returns two independent tables without mutating
its supplied catalog and is not a substitute for whole-program admission.

ST-024 uses duplicate_print/sort-dupout-print-v1, one same-kind operation with
profile/source_lines, name=input and one input, ordered RUN provenance and exact
empty defaults. The whole program must contain an admitted duplicate_sort.
At most three logical reports use print_01.txt,print_02.txt,print_03.txt with
existing default-column,ASCII/LF,mixed-integer text and local TITLE behavior.
Job receipts identify ascii-dupout-mixed-integer-v1. Its expected-report JSON
accepts1..3 safe entries and at most4MiB. Exact basename-set/UTF8-byte comparison
and staging are unchanged. Older report profiles retain their own limits.

Join only character DATA,fresh plain/directed SORT,TITLE and the new PRINT.
No KEEP/DROP projection,BY _ALL_,directed DUPOUT,NODUPRECS,NOEQUALS,arbitrary
replacement,external catalog/engine or additional procedure form is inferred.
Retain64Steps,1000rows/table,32columns,character widths1..64,32TITLEs and existing
per-report byte limits. Numeric INPUT retains its exact converter including
fractions; logical PRINT independently remains integer-only. No dependency or
capability-manifest assessment is added. Preflight validates original values and
propagates conservative tables without sorting. Actual SORTs execute once.

## Independent evidence and the whole official source

Three first-party semantic gates have R twins and a common independently frozen
complete-source fixture. Interleaved groups,nonalphabetical descriptors,ordinary
missing,padding,unequal tied payloads and equal-valued duplicates exercise identity,
multiplicity,replacement and immutable reports. Runtime,emitted Python and actual
CLI comparisons follow the pre-runtime hand/R freeze. Wrong-result/report/trace
controls,static/empty/resource and malformed-portable refusals,old-family positives
and actual late partition/replacement/third-report faults challenge acceptance.
Failed jobs publish no accepted partial catalog or report artifacts.

The separate whole-source vendor gate pins unchanged SORT5 at
sassoftware/sas-code-examples579e057f90cd699f744fd6a1c8acaf9243f7ff67:
2132bytes,14inline rows,two SORTs and three reports. Independent hand/R readers
bind the entire source,all3datasets/descriptors,12survivors/2removed rows,all
40semantic events and exact375/367/131-byte logical report artifacts. One removed
row ties the retained score exactly; the other has a lower score. A lower-score
filter would lose required duplicate multiplicity. The original input remains,
while the prior sorted survivor table is replaced as the source requests.

The manifest registers seven vendor candidates; whole passing gates and full
receipts establish proofs separately from Roku22complete/56pinned. Vendor bodies,
LICENSE and complete derived results remain external, including ignored paths.
Prepare the pinned external cache explicitly before offline verification:

```sh
python tools/prepare_vendor_sources.py
python verify_all.py
```
