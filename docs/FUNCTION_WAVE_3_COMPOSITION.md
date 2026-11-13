# Third DATA step function wave

Status: bounded implementation evidence for principal and maintainer review.
Acceptance requires a matching source-stable golden receipt and both unchanged
1k workloads for the final source. Independent hand/base-R witnesses support
these contracts. Native SAS comparison and new external-program proof remain
outside this evidence.

This wave adds 31 selected function names across six families, a separately
marked finite consumer profile and two complete composition programs. Nine
original program gates cover the six families, the consumer phase and both
compositions. This selected matrix does not enumerate the SAS functions/CALL
universe.

| Family | Selected names | Rule and contract | Source gate |
| --- | --- | --- | --- |
| Text and quoting | PROPCASE, QUOTE, DEQUOTE, COUNTC, TRANSTRN | [DS-109](TEXT_QUOTING.md) | [text/quoting](../examples/verify_text_quoting.py) |
| ASCII positions | ANYLOWER, ANYUPPER, ANYPUNCT, ANYXDIGIT, NOTALPHA, NOTALNUM, NOTSPACE | [DS-110](ASCII_POSITIONS.md) | [positions](../examples/verify_ascii_positions.py) |
| Selection and lookup | IFN, IFC, CHOOSEN, CHOOSEC, WHICHN, WHICHC | [DS-111](SELECTION_LOOKUP.md) | [selection](../examples/verify_selection_lookup.py) |
| Rank and sums of squares | LARGEST, SMALLEST, CSS, USS | [DS-112](RANK_SQUARES.md) | [rank/squares](../examples/verify_rank_squares.py) |
| Numeric functions without fuzz | CEILZ, FLOORZ, INTZ, ROUNDZ, MODZ | [DS-113](ZERO_FUZZ_NUMERIC.md) | [zero-fuzz numeric](../examples/verify_zero_fuzz_numeric.py) |
| Calendar constructors | HMS, YYQ, DATEJUL, JULDATE7 | [DS-114](CALENDAR_CONSTRUCTORS.md) | [calendar](../examples/verify_calendar_constructors.py) |

All 31 names have canonical reference helpers and bounded direct ordinary
version 2 DATA source/portable assignments. Earlier fixture registrations and
rule objects retain their order. Prior oracle files, the original canonical
reference prefix, dependency locks and capability manifests remain unchanged.
The earlier `function-consumers-v1` module and its standalone grammar remain
unchanged.

## Contract distinctions

Character functions use printable ASCII and stored descriptor widths. PROPCASE
requires explicit delimiters. QUOTE preserves trailing blanks, doubles the
chosen quote and refuses buffer exhaustion; a known literal result also checks
a predeclared destination on skipped or empty execution. DEQUOTE has explicit
termination, doubled-quote and unclosed-quote cases. COUNTC admits literal I/V/T
modifiers. A single stored blank replacement differs from the zero-length
TRIMN temporary qualified for TRANSTRN deletion.

Position functions return one-based positions, with signed starts and zero for
no match. ANYPUNCT with a missing start remains held because the pinned
reference section contains conflicting missing-start statements. The other six
new class functions qualify a missing start as one.

Selectors validate every admitted argument of a reached call, including an
unselected choice. A missing IFN/IFC condition selects the optional missing
choice when supplied, otherwise the false choice. CHOOSE admits nonzero signed
integral indexes within the candidate count, counting negative indexes from
the end. WHICH returns the first match; WHICHC ignores trailing storage blanks
for equality, and a blank search returns ordinary missing.

Rank and squares measurements are integral, within +/-1000000, with up to 32
values and ordinary missing. A valid rank beyond the nonmissing count returns
missing; an invalid rank refuses. CSS uses an exact integer centered numerator
and one binary64 division. Independent R uses squared pairwise differences.
The high-offset CSS(999999,1000000,1000000) target is exactly 2/3 before binary64
conversion. USS uses an exact integer sum. The VAR/STD tolerance does not
transfer to these new gates.

Zero-fuzz inputs have magnitude at most 1000000, and nonzero magnitude at least
2^-40. ROUNDZ uses exact half-even ties and positive power-of-two units from
2^-10 through 2^10. MODZ independently admits signed nonzero dyadic divisors in
the same range, retaining the dividend sign for nonzero remainders. All 1071
supplemental targets are independently derived with exact rational arithmetic
and checked against base R. Canonical validation uses binary decomposition;
the R oracle uses exact unit membership. Adjacent floats are distinct from an
admitted unit or tie. New results normalize numeric zero to +0 as an explicit
transport policy, without a native SAS IEEE sign claim. New-profile source
rejects nonzero numeric text lost to binary64 zero; true zero text remains
valid. General decimal units, smaller nonzero inputs and underflow stay held.

HMS uses integral hours 0..23 and minutes/seconds 0..59. YYQ requires explicit
four-digit years 1753..3999. DATEJUL requires a valid seven-digit year/ordinal
value, including leap-year checks. JULDATE7 returns the numeric seven-digit
ordinal for an integral epoch date in that civil range. YEARCUTOFF, JULDATE,
system clocks, timezones and component normalization remain held.

## Separate finite consumers

[DS-115](SELECTION_CONSUMERS.md) uses an exact leading
`function-consumers-v2` marker in each consumer step. Its assignment grammar is:

| Root | Qualified arguments |
| --- | --- |
| IFC | NOTALNUM over primitive arguments compared to literal zero with = or EQ, followed by two primitive character choices |
| IFN | Primitive flag and fallback, followed by LARGEST over a primitive rank and primitive measurements |
| CATS | Primitive character items or one primitive-argument PROPCASE/DEQUOTE item, with at least one such new call |
| TRANSTRN | Primitive source and target, then TRIMN over exactly one literal blank |

Selected validator/MISSING calls may appear on the left of an IF comparison
with an integral right literal 0..32767 and the existing numeric comparison
spellings. Reached calls evaluate their arguments eagerly. Statement IF and
ELSE IF evaluate only reached predicates and branches. Literal and descriptor
checks still run for skipped paths and empty input. New IFC/CATS/TRANSTRN
destinations infer 200 bytes; buffer failures remain explicit.

The resource caps are engineering bounds: 16 ordinary DATA steps per program,
256 operations and 128 calls per step, 16384 containers per step, structural depth 64,
two call levels, one driving input and 4096 matched provenance rows. Exact program, operation and marker
shapes are checked before recursive runtime walkers. Loops, arrays, queues,
WHERE, BY, RETAIN, multiple inputs, mixed profile versions, arbitrary nesting,
SQL and C++ remain held under this profile. Direct family calls retain their
own domains. The only additional legacy call here is strict PUT DATE9.

## Complete originals

The [consumer original](../examples/selection_consumers_capture.sas) has 13
statements, six hand records and 15 completely compared columns. Its
[gate](../examples/verify_selection_consumers.py) precedes both compositions.

The [quoted-record original](../examples/quoted_record_classification_capture.sas)
has 26 statements, six hand records and 26 checked columns. It combines quoting,
proper case, byte classification, stored blanks, duplicate/negative selections,
identifier construction and eager ranked choices. Its
[gate](../examples/verify_quoted_record_classification.py) compares the whole
program and another 30 complete input catalogs.

The [quarterly original](../examples/quarterly_reconciliation_capture.sas) has
34 statements, eight hand records and 42 checked columns. It combines calendar
construction and recovery, ordinal round trips, supplied pre-epoch timestamps,
missing counts, rank/squares, zero-fuzz rounding and the nested IFN choice.
Its [gate](../examples/verify_quarterly_reconciliation.py) compares the whole
program and another 30 complete catalogs, including empty input. Fractional
CSS/rounding/remainder values remain exact dataset comparisons; numeric PUT
retains its earlier integer-only contract.

Each original compares every value, type, descriptor, metadata field, table,
column, row and logical record in runtime, emitted Python and the actual CLI.
Wrong value/type/order/metadata/column-order and log expectations require their
intended CLI comparison-failure receipts. Late faults require a successful
prefix control and publish no result artifact or partial emitted stdout.

The functions/CALL universe remains null. Compile-clean inventories do not
supply a coverage percentage or complete external-program execution proof.
Raw oracle versions, failed attempts, source snapshots and per-phase acceptance
receipts stay in ignored telemetry. The final source also requires the invariant
linter, strict sanitization, manifest schema and source-preservation review.
