# PROC SORT input KEEP

Status: DS-075 bounded repository/base-R contract for maintainer use, conditional
on current source-bound full verification. No live SAS, native SAS/ODS layout,
maintenance-wide or whole-language equivalence is claimed.

The separate sort-input-keep-v1 profile admits PROC SORT DATA=name(KEEP=names)
OUT=fresh, one ascending BY list and optional NODUPKEY. It requires genuine
preceding character DATA, an empty initial catalog and complete source ownership.
Comments, strings, opaque records and numeric-only producers cannot select it.
Existing directed, all-column, numeric and DATA-step projection profiles retain
their previous shapes and refusal contexts.

The [SAS9.4 KEEP= reference](https://support.sas.com/documentation/cdl/en/ledsoptsref/69751/HTML/default/p0vw9lyyxk1cxkn0zzfemrsr3t9a.htm)
describes input selection as restricting variables available for processing and
admits the option in PROC steps. This profile requires all BY columns to survive.
It validates the complete original schema and every cell before KEEP, so excluded
columns cannot hide invalid data. These are explicit repository refusal policies.

KEEP has1..32 unique literal ordinary names; BY has1..8 distinct ascending names.
All names must exist. Selection retains original descriptor order, types, lengths,
padding and cells, regardless of KEEP-list spelling order. At least one character
descriptor must remain. This ordered-schema mapping is witnessed independently,
not a captured native SAS descriptor golden. Stable sorting and optional
first-survivor NODUPKEY retain existing ASCII and ordinary-missing policies.

The exact version2 projected_sort Step has one same-kind header-line operation
with profile,keep,by,nodupkey,source_lines. Legacy by/nodupkey fields stay empty
and false. No existing Step gains fields. Every SORT destination inside this new
family is fresh, including plain legacy SORT joins; standalone old profiles keep
their previous in-place behavior. Preflight propagates selected descriptors and
validated values without sorting. Runtime sorts once, and trace ordinals refer
to original source rows. Source tables and earlier reports remain unchanged.

Retain64steps,1000rows,32columns,character widths1..64,two PRINTs and32TITLEs.
Exact numeric INPUT fractions remain sortable; logical PRINT retains its separate
integer-only domain. Failed jobs publish no accepted partial artifacts.

An original complete fixture has independent hand/base-R datasets, both reports
and full trace, qualified before runtime implementation. Unequal tied payloads,
nonalphabetical schema, reversed KEEP lists, missing/padding, generated boundaries,
invalid excluded values, portable refusals, actual CLI wrong comparisons and late
failures challenge the contract without deriving expectations from the runtime.

The whole official witness is unchanged SORT4 at sassoftware/sas-code-examples
commit579e057f90cd699f744fd6a1c8acaf9243f7ff67,1824bytes,14inline rows and two
reports. Its separate full-source hand/R expectations freeze complete datasets,
schema,reports and events before runtime comparison. The vendor manifest is a
registration; only its passing gate and full receipt accept the proof. Vendor
bodies, LICENSE text and complete derived results remain outside Go.

DROP=, ranges, special lists, directed/ALL composition, output options, DUPOUT,
new in-place forms, extra reports, general informats and input recovery remain
refused. No dependency or capability-manifest assessment is added.
