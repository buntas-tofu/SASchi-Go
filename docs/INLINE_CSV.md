# Bounded comma input and numeric INPUT ranges

Status: bounded DS-058/059 repository/base-R evidence for principal and maintainer
use. The contract is an implementation inference from the authorized pair plan.
No live SAS, physical-log or general CSV equivalence is claimed.

## Characterization before implementation

The [SAS INFILE reference](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n1rill4udj0tfun1fvce3j401plo.htm)
defines FIRSTOBS as the physical record where reading starts, with default 1.
Its default FLOWOVER reads another physical record when INPUT still needs
values. A completed INPUT without a holding control releases the unread suffix
of its last record. An incomplete read at EOF terminates the DATA step.

The separate [SAS Usage Note 23206](https://support.sas.com/kb/23/206.html)
explains that DLM without DSD collapses consecutive delimiters. Thus comma spans
in `97,,92`, followed by `,1,1`, supply the values 97, 92, 1 to one three-variable
read. They do not supply an ordinary missing value between the commas. DSD is a
separate option with missing-field and quoted-field behavior. It is deferred.
Only an explicit period supplies ordinary missing in this profile.

The [SAS variable-list reference](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a000695105.htm)
describes numbered ranges as a common prefix followed by consecutive suffixes.
This differs from double-hyphen definition-order lists and name-prefix lists.
All primary sources were consulted on 2026-10-30. Their broader language limits
do not determine this implementation's conservative bounds.

## Admitted source and representation

One top-level numeric INPUT remains the first executable action, after existing
declarations and output projection. New comma source uses exactly
`infile datalines dlm=','` or its CARDS alias, with optional `firstobs=N`, where
N is an unpadded integer in 1..10001. Options can occur in either order, once
each. INFILE must precede INPUT and any executable action. No external file,
DSD, quoted field, alternate delimiter, retained cursor or other INFILE option
is admitted. The inline block and terminator retain the earlier scanner rules.

INPUT additionally admits canonical ordinary names or ascending numbered ranges,
such as `x1-x3`. Range endpoints have the same complete prefix and unpadded
suffixes in 1..64. A prefix ending in a digit is not inferred: the complete final
run of digits is the suffix. Expansion precedes duplicate and overlap checks,
and the expanded list remains 1..32 unique ordinary names. Reversed, padded,
double-hyphen, colon, special-name and mixed-prefix ranges refuse. Range expansion
is INPUT-only; PUT, SUM OF and other variable-list contexts remain separate.

Only actual new source creates an `input_numeric` operation. Its exact args are
`profile`, `terms`, `names`, `delimiter`, `firstobs`, `infile_line`, `records` and
`data_line`; profile is `numeric-inline-v1`. Terms are lowercase canonical source
names/ranges, names are their independently checked expansion, delimiter is comma
or space, and infile_line is absent only as the explicit value None for a
range-only ordinary list read. No default Step field or prefix operation is
added. Existing `input_list` plans retain their exact shape. The new operation
must have a comma source or at least one range trigger. New numeric_profile
compositions, arrays and loops remain deferred under this input profile.

All physical records, including skipped headers, retain the 10000-record,
80-byte printable-ASCII and no-semicolon bounds. FIRSTOBS skips records before
numeric conversion. Empty physical records supply no fields. Nonempty comma
fields may have surrounding ASCII blanks, which are removed before the unchanged
numeric converter. A consumed field consisting only of blanks is conservatively
refused because the consulted primary descriptions do not settle that case.
This is an implementation refusal, not a claim that SAS rejects it.

Adjacent and leading/trailing commas supply no fields. Once INPUT is satisfied,
extra fields on that physical record are discarded without conversion. Consumed
invalid values refuse eagerly, even before incomplete EOF; incomplete valid
observations are discarded. Numeric conversion keeps the existing exact
binary64, token, significand, exponent and magnitude limits. No helper or
semantic-reference body changes.

The validator checks the complete new shape and creates a private scalar-input
shadow for the earlier descriptor, operation and INPUT restrictions. Unknown
operations or args are not dropped. Static checks cover skipped and empty paths;
runtime retains ordinary row reset, retained-target overwrite, output suppression,
projection, snapshots and atomic failure. Earlier numeric profiles cannot admit
the new operation by forging or replacing its marker.

## Evidence

Separate DS-058 comma and DS-059 range gates preserve all older gate order.
They contain independently authored base-R parsing, hand pins, generated
complete-source cases, shared refusals and actual CLI comparator failures. An
original complete fixture binds source, ordered result, logical stdout and
statement/read/snapshot accounting. No complete sibling-program unlock is claimed.


The comma gate currently observes 8 hand pins, 240 generated complete-source
cases and 22 shared refusals. It also runs eight actual failed dataset CLI
comparisons and one separate exact logical-log damage control. The range gate
observes 5 hand pins, 180 generated complete-source cases, 21 shared refusals and
four actual failed dataset CLI comparisons for lexical ordering, lost endpoint,
reversed values and padding. Numeric values and descriptor/logical-record order
compare exactly; no numerical tolerance is introduced.

The original `examples/inline_csv_capture.sas` has 20 language statements and two
opaque inline-data scanner events, five complete reads and seven snapshots. Its
independently hand-accounted source, full ordered result and emitted logical
stdout are pinned by SHA-256 in the gate. R consumes the entire original source
and all generated cases. Its finite scalar witness grammar is not a claim of
universal equivalence for every inherited scalar function or character companion.
The 27-test source suite separately tests inherited character descriptors, static empty
paths, malformed portable metadata and atomic late arithmetic failure.

New-profile source is bounded before recursive expression parsing: at most 32
nested parentheses and 128 arithmetic/call markers per code statement. Opaque
physical records are excluded from code-marker and expression-depth checks. Portable structures
retain bounded cycle/container checks. These are conservative implementation
resource policies. Earlier source without either new input trigger is unchanged.

No exact earlier fixture or suite source-refusal case is promoted by D2a. The
manifest promotes one entry, INFILE Statement, from UNASSESSED to its explicitly
bounded inline subset. Four already-GATED INPUT/CARDS/DATALINES entries gain
additive evidence; document universes and all earlier evidence remain intact.

Original source SHA-256: e4ef1b6fc8ca978bb789acf834b2d61277a2646e1372809019aa8739c50527c2.
Ordered result SHA-256: f66eb9179e91325ba6512bc871a66543758a6d9f1cff7af25bf5c3d97e81f735.
Logical stdout SHA-256: 66b5baec970c71d09eda39dbd16da8501f5b173278c03d76b573ada7bdf69d31.
