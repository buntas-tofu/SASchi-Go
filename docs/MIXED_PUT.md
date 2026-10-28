# Bounded mixed literal and numeric PUT

Status: DS-042 repository/base-R evidence for principal/maintainer review.
This profile proves logical output records, not physical SAS log equivalence.
Live-SAS validation remains outstanding. Wider values, syntax or changed source
bytes require new evidence before acceptance.

## Characterization and representation

The primary [SAS list PUT reference](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/p0jcwhe1ofmb49n1xf1q2kc44b0v.htm)
defines a following blank for list variables. Literal text adds no separator;
its own blanks matter. Ordinary numeric missing is a period. The
[general PUT reference](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000161869.htm)
separates list output, literal text and pointer/line controls. The
[FORMAT reference](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000178212.htm)
establishes that attached formats affect output.

Design inference: compose the existing literal decoder and conservative BEST12
integer renderer in a separate version2 `put_mixed_numeric` operation. Its
ordered `items` contain exact literal tokens or normalized ordinary variable
names. Earlier literal, character, numeric-name-list, named and PUT_ALL plans
keep their behavior. The type-neutral statement router retains its previous
route; the typed compiler selects DS-042 after source-order type discovery.

## Accepted profile and boundaries

Require at least one quoted literal and one numeric variable known before PUT
in source order. Numeric assignments, array members and counted indices supply
that evidence, including discovery on skipped assignment paths. An input
descriptor alone does not widen compilation. For example, a skipped `n=.;`
after SET establishes numeric source evidence without overwriting input rows.

Numeric fields accept ordinary missing or finite integers with magnitude at
most99999999999. Missing renders as a period, negative zero as zero, and each
numeric field adds one blank. Literals preserve spaces and decode doubled
quotes. The established empty-quote behavior produces one quote character.
`put '[' n ']';` with n=7 produces the logical record `[7 ]`.

Printable ASCII,2..64 items and at most64 logical columns including separators
are implementation policies, not SAS language limits. The logical buffer retains
its terminal separator; emitted Python prints one newline after each record.

Top-level DATA, bounded simple IF/ELSE and counted-loop bodies are accepted.
PUT reads actual row variables, including scalar array members. It does not
emit dataset rows, introduce columns or change explicit OUTPUT suppression.
Row/run resets and loop scheduling retain their existing contracts. Static
item shape, minimum width, source-order types and attached formats validate
even for empty, filtered or skipped paths. Dynamic values validate only when
reached. A late failure publishes no accepted result or buffered stdout.

Refusals remain for character/numeric variable mixtures, unknown or descriptor-
only variables, direct expressions/array references, automatic names, fractions,
special missing tags, attached formats, FILE, pointers and line holds, unresolved
double-quoted macros, non-ASCII text, overwide records, MERGE and C++.
Mixed-output bodies in DO OVER, DO WHILE and DO UNTIL remain deferred. The
bitwise corpus program retains its67-column PUT_ALL refusal. Array and counted-
loop limits are unchanged.

## Evidence

`examples/verify_put_mixed_numeric.py` checks9 hand pins,2400 constructive
source/runtime/base-R cases,18 shared refusals and5 spacing/format controls.
`saschi.test_put_mixed_numeric` covers descriptors, skipped paths, malformed
plans, atomic failures, resets, source/emitted/CLI execution and comparator
controls. The installed wheel also executes a composed mixed-output program
with only the standard library.

The original `examples/mixed_put_capture.sas` captures three ordered snapshots
with aliased array values, ordinary missing and explicit OUTPUT. Independent
base R produces the rows and records. Dataset comparator controls reject wrong
values, row order, multiplicity and schema order. The public dataset comparator
continues to exclude logs; separate exact record/stdout checks reject incorrect
spacing, count and multiplicity.

The entire unchanged sibling `100_doors.sas` is the first whole-program target.
Its source remains external. Independent base R accounts for all13 statements,
simulates all100 final cells,482 inner iterations and the post-loop indices101
and200. The hand check uses divisor parity: only the ten perfect squares from1
through100 have an odd number of toggles. The logical record is
`Number of Open Doors:  10 `, with two blanks after the colon and one after10.
This is the eleventh complete external-program proof.

| Program | Pin | SHA-256 |
| --- | --- | --- |
|100_doors.sas|source|e708b988d5d9f852cef56150068abeb9eda8bb3ca3eb59d04457429e930d2aa1|
|100_doors.sas|complete result|de6deb664a12c7c59152d6b2a57baf70d80a6d14652135ef4bfe3e98bd600273|
|100_doors.sas|stdout|7fdf31c4f5a69dffc4113dc222c537f347029cfe0ea6f55b01f2c21b3fb9649e|
|mixed_put_capture.sas|source|a24331f7dc7ca0a41c06e72919d2aa072fb742db45d6f0b630089f92b2eeaa45|
|mixed_put_capture.sas|complete result|e54cb5fa6ec9cffc5147ec3fde8da0ea1c9a1f97163e3ffb5e3ffcc8a3dc94f6|
|mixed_put_capture.sas|stdout|9f973f0f7ac3a3b793518140675aa22132b13a4e35e447e98d82dc402c1a93b1|

Result pins hash sorted compact JSON; stdout pins include newlines and trailing
blanks. Current receipts, exact commit and ownership live in the ignored
`telemetry/SESSION_HANDOFF.md`. All existing gate registrations retain their
order; the former mixed-output refusals now have complete execution assertions.
