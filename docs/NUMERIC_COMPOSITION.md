# Bounded numeric composition and output discovery

Status: DS-045/DS-046 repository/base-R evidence for principal/maintainer review.
This profile proves bounded values, DATA observations and logical PUT records.
Live-SAS validation, diagnostic recovery and physical SAS log fidelity remain
outstanding. The local handoff binds exact commits and passing receipts.

## Characterization and representation

The primary [Base SAS arithmetic tutorial](https://support.sas.com/documentation/cdl/en/basess/58133/HTML/default/a001334675.htm)
defines multiplication and division at equal precedence, evaluated left to right,
ahead of addition/subtraction. Parentheses control grouping. The [missing-value reference](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a000989183.htm)
describes propagation through arithmetic and separate diagnostic notes. This tool
refuses rounded/error-state cases in the bounded profile and emits supported PUT
records only. Those choices are implementation policy, not SAS language limits.

The [SAS variable-creation reference](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a000695113.htm)
distinguishes first use, default numeric missing and uninitialized-variable notes.
The vendor's [Test Your SAS Skills extract, printed page7](https://support.sas.com/publishing/pubcat/chaps/55625.pdf)
explicitly creates absent variables referenced by PUT as numeric variables in its
example and relates storage order to definition order. The [list PUT reference](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/p0jcwhe1ofmb49n1xf1q2kc44b0v.htm)
defines a period for ordinary numeric missing and one following blank per field.
Sources consulted2026-10-29. No physical SAS note fidelity is claimed.

Design inference: retain the existing arithmetic node with `op: '*'`. Add an
optional `discover` list only to new version2 `put_numeric_list` operations that
need output-only numeric discovery. Existing known-name plans acquire no fields
and retain their serialized shape. Restrict discovery to catalog-free DATA steps,
where type decisions do not depend on a supplied data-set descriptor.

## Exact multiplication

Operands are finite binary64 numeric values of magnitude at most2147483647, or
ordinary missing. Both operands validate before missing propagates. Character
coercion, bool, tagged missing, nonfinite values and wider magnitudes refuse.
Every nonmissing product must equal the exact rational product of the stored
binary64 operands and remain within2147483647. Rounded products and nonzero
underflow refuse; an exactly representable subnormal can pass. Zero normalizes.
Literal parsing keeps its existing binary64 meaning; this is not decimal-exact
source arithmetic. For example,1.25*2.5 passes;1.1*1.1 needs rounding and refuses.

Arithmetic subtrees containing multiplication use exact bounded addition and
subtraction, existing exact division and exact multiplication. Leaves and reached
intermediates validate before zero or missing can hide an invalid operand.
Unrelated legacy arithmetic keeps its earlier behavior. Existing numeric function
operand/consumer restrictions remain; a separately stored function result can be
used when direct composition is outside those restrictions. New scalar trees use
32 expression levels and the existing128 arithmetic/call nodes per DATA-step
budget. A256-container structural-depth guard also bounds forged wrappers before
recursive descriptor checks. Numeric arrays retain their separate existing
expression/node limits.

Scalar DATA assignments, supplied numeric input, IF/WHERE, retained sum statements
and previously permitted counted/WHILE/UNTIL bodies compose. Numeric arrays admit
multiplication in their existing indexed/current-element expression profile,
including permitted DO OVER and nested counted bodies. Array aliasing, integral
subscripts, aggregate limits and row/run/step state remain unchanged. Multiplication
in counted controls, exponentiation, broader array calls/division, wider loop
nesting and C++ remain refused. Earlier division and INT bounds are unchanged.

Literal/type/shape errors check on empty, filtered, skipped and zero-trip paths.
Dynamic values validate only when reached. Independent serialized-plan validation
rejects malformed literals/operators, excessive depth/budgets and cycles. Any
failure discards accepted results and previously buffered stdout.

## Output-only numeric discovery

Catalog-free version2 DATA numeric-list PUT can introduce normalized ordinary
numeric names, in first occurrence order. An unassigned name begins as ordinary
missing; no synthetic computation initializes it. Static schema discovery visits
skipped and zero-trip bodies and names first seen after OUTPUT. Earlier snapshots
therefore contain the column with its current value. Scratch resets on each input
row, step and run. Later assignments and existing output forms see that numeric
descriptor. The public dataset comparator still excludes logs.

The optional `discover` marker must be a nonempty unique ordered subset of `names`.
Its order follows first occurrence in the output list. Repeated output fields
remain repeated records fields without duplicate schema columns. Redundant marker
names already established as numeric are harmless, allowing condition/reference
schema discovery to precede a child PUT. Unmarked older plans retain the earlier
known-before-PUT check. All descriptors and minimum widths validate statically.

Existing numeric rendering stays bounded: ordinary missing is a period; supported
finite integers have magnitude at most99999999999; each field adds one following
blank; at most64 logical columns. Discovery does not add fractional output, unknown
mixed/named discovery, attached formats, special missing output, automatic names,
FILE, pointers, line controls, supplied SET/lookup-dependent discovery, MERGE/SORT
or C++. Existing output forms can consume a name after numeric discovery. No input
cursor, array object or internal loop/budget state becomes a schema column.

## Evidence and complete programs

The multiplication gate has20 hand pins,1200 constructive source/runtime/R cases,
61 shared refusals and4 naive controls. Python checks exact rational products;
independent base R decodes native hexadecimal doubles and multiplies significand
bit arrays, comparing exact bits/exponents to the native result. The discovery
gate has4 hand pins,400 independent R/source/runtime/emitted PDV schedules,
6 source refusals and4 naive controls. The integrated source suite adds malformed,
empty/skipped, state/reset, descriptor, comparator, atomic and actual CLI controls.
Gate and suite totals are reported descriptively in the current handoff inventory.

The original numeric_composition_capture.sas consumes28 statements across two
DATA steps,3 plus2 array trips and three ordered snapshots. Its stored products,
ordinary missing array member, SUM OF, discovered output-only column, schema order
and reset agree with hand accounting and an independent whole-source R interpreter.

The entire unchanged sibling sum_and_product_of_an_array.sas consumes8 statements
and100 loop trips. It assigns a1..a100 to the first100 squares, ends with i=101,
sets b=338350 and leaves c missing. Its only logical record is `338350 . `, followed
by a newline in emitted stdout; it creates no datasets. Despite its title, the
source never assigns a product to c. Hand accounting, independent base R,
source/runtime, emitted Python and actual CLI agree. Uninitialized-variable notes
are outside this logical log. Corpus source remains in the sibling data repository.

| Program | Pin | SHA-256 |
| --- | --- | --- |
|sum_and_product_of_an_array.sas|source|06eca942365b06dec7e0f99b077856b4b33391e8addee0b39a44c0170987ea1a|
|sum_and_product_of_an_array.sas|complete result|50083e57b54be2f314d78b7900011d114d447e2091b63eedcb71f4f66123ffcc|
|sum_and_product_of_an_array.sas|stdout|891d070ad83d719883b9b10e3e2ce42bf0aaa74fa560f55281ea6e0ad178e3ca|
|numeric_composition_capture.sas|source|c35ccb83772eea46cc5bc5a922e5537887dfd9cb18729227aef0e1542aa5658a|
|numeric_composition_capture.sas|complete result|d5205bb84b08a3e6de7dc3d936f3d3b5cb0f845e68dc4605d97dba42af2dcd64|
|numeric_composition_capture.sas|stdout|4ec6ca19bea3d45c44a40846f0aead89023664ac2ccd81610ec509563b27bfc6|

Result pins use sorted compact JSON; stdout pins include trailing blanks and every
newline. Separate log/stdout controls reject wrong values, order and multiplicity.

The A0 companion adds evidence for two existing behaviors, without a language
expansion: the entire hello_world_text.sas produces one exact `Hello world!` record,
and the entire comments.sas is an explicitly accepted no-op with no rows or logs.
A separate R scanner accounts for all bytes, both comment forms and all statements;
appended-code and truncation controls prevent a partial-source proof. Both have
source/result/stdout pins and actual CLI evidence in the separate corpus-basics
suite. These two proofs remain distinct from the B3 integration proof and from
fixture/suite counts. All56 sibling hashes remain pinned.
