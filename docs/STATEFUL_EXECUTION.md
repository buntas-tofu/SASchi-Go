# Stateful execution and typed comparison, 0.4.0

Status: executable development contracts, original pins, and Python/base-R
witnesses. No live SAS capture. Maintainers may use these results to review the
bounded operations below; they do not establish equivalence for arbitrary jobs.

## Run the event example

```sh
saschi inspect examples/events/job.sas
saschi run examples/events/job.sas --inputs examples/events/inputs.json --expect examples/events/expected.json --output telemetry/events-review
```

The example reads a configuration row once, filters the driving input before BY
groups form, resets a retained total at each group boundary, and writes five
snapshots from three selected input rows. The scratch variable is missing after
the first iteration. The second configuration row is never consumed. Fixed
expected values and an independent base-R implementation gate the result.

## Plan version 2

Quoted-literal `PUT` statements emit one logical log record each. For example,
`put 'left' 'right';` emits `leftright`, while `put 'left ' 'right';` emits
`left right`. Syntax whitespace is not output. Blanks inside literals remain
significant. Doubled delimiters decode once, and the PUT-specific bare quote
pair emits one delimiter. No Python backslash escaping is applied.

DS-023 gates printable ASCII records of at most 64 columns, which fit the
documented minimum SAS LINESIZE. Double-quoted ampersands and percent signs
require macro review. FILE destinations, pointer controls, line holds, repeats,
formatted items, conditional PUT, and longer
records remain tickets. Named-list `put x=;` remains supported separately.
Python execution and the independent base-R witness are checked by
`examples/verify_put.py` and `saschi.test_put`; C++ refuses literal PUT. These
are logical records, not physical log captures with SAS notes and source echoes.

DS-024 adds ordinary unformatted character-variable list PUT, optionally mixed
with quoted literals. With `c='  A  '`, `put '[' c ']';` records `[A ]`:
variable edge blanks are removed and one blank follows the value, while
literals keep their own spaces and add none. A final variable separator is
retained in the logical record as a pointer-spacing contract, without a claim
about physical SAS log trailing blanks. The complete record, including every
separator, must fit 64 printable ASCII columns. Zero-length and all-blank
values are refused pending a missing-field contract; this is a support policy,
not a claim that SAS refuses them. Numeric and tagged-missing values, attached
formats, special PUT controls, and implicit conversions require review.

Original token spans distinguish `put '41'x;` from `put '41' x;`. A literal
followed by a variable requires whitespace immediately after its closing
delimiter. Comment-only separation such as `'41'/*c*/x` is conservatively
refused; `'41' /*c*/x` is accepted. The guard applies to suffix prefixes as well
as exact suffix names. Descriptors are validated even on empty or filtered
inputs, and LENGTH preserves inherited formats. Assigning `copy=source;`
creates an unformatted copy with the source type and width. Literal-only and
named-list PUT keep their existing paths. A program using DS-024 conservatively
refuses double-quoted source tokens containing `&` or `%` anywhere, including
unused expressions, later assignments, and earlier DATA steps. This prevents
unexpanded source macros from becoming apparently valid character output.
Single-quoted source and external catalog values still treat these characters
as data. `examples/verify_put_list.py` and
`saschi.test_put_list` gate Python and independent base-R logical records;
C++ refuses this operation. No live SAS was used.

DS-025 adds bare `PUT _ALL_;` in scalar DATA steps. It writes the complete PDV
in compilation order, preserving the first source spelling of each variable,
then `_ERROR_=0` and `_N_=1`. References to uninitialized variables create
numeric PDV slots; declarations after PUT still belong to the complete PDV.
Automatic variables do not enter the output dataset. Each named field has one
following blank, including the final `_N_` field. This is a logical output
buffer contract, not a physical SAS log transcript.

The numeric output slice is ordinary missing (`.`) or integer-valued numbers
with magnitude at most 99999999999. This conservative subset fits signed
BEST12 without exponent notation. Nonblank printable ASCII character values
lose edge blanks. Names, equal signs, separators, and automatic variables all
count toward the 64-column limit. Fractions, special-missing output, blank
character fields, attached formats, and wider records refuse explicitly.

The source slice allows declarations, assignments, bare PUT _ALL_, and OUTPUT,
without inputs, BY, retention, or conditions.
Explicit OUTPUT in this slice requires a named DATA destination; DATA _NULL_
OUTPUT is deferred.
Assignments may use literals, variable copies, the LENGTH family, and in-range
character SUBSTR. Arithmetic, other functions, and invalid SUBSTR bounds refuse
pending error-flag modeling.
Empty character source literals also refuse pending their source-blank contract.
The implementation never fabricates a zero `_ERROR_` after those operations.
As with DS-024, program-wide double-quoted macro triggers refuse. DS-025 also
refuses non-ASCII/control source strings, including intermediate expressions.
C++ remains blocked. The older literal, character-list, and named-list paths
retain their own contracts.

Typed numeric LENGTH, LENGTHN, and LENGTHC arguments return 12, including
uninitialized and tagged-missing numeric values: SAS converts them to a
right-justified BEST12 character representation. Character missing remains a
blank-padded string in the typed executor and follows the original character
length rules. `examples/verify_funcs.py` and `examples/funcs.R` gate this
conversion separately from the PUT field renderer. Conversion and uninitialized
variable notes are diagnostic log content, not user PUT records.

`examples/verify_put_all.py` checks original pins and constructed cases against
an independent base-R renderer. `saschi.test_put_all` also reads the unmodified
Roku `string_length.sas` and `substring.sas` programs in place. It pins source,
emitted stdout, and complete result hashes, executes the emitted Python and job
paths, and requires a separately parsed base-R program witness to agree. It
stores hashes rather than third-party source or derived text. These two tests
skip only when the optional sibling corpus is absent; CI uses its pinned
revision. Their passing result establishes the recorded logical output under
these contracts, with no live SAS execution or physical log equivalence.

A single simple DATA destination is supported. `OUTPUT;` and `OUTPUT name;`
snapshot the current PDV immediately. Any explicit OUTPUT in the step disables
implicit end-of-iteration output, including an OUTPUT in a false IF branch.
A snapshot already written survives a later failed subsetting IF.

The driving `SET name;` precedes computations. One optional
`IF _N_=1 THEN SET lookup;` can precede that SET. The lookup reads its first row
once; an empty lookup ends the step without output. Input variables retain their
values between iterations until a SET or assignment overwrites them. Ordinary
assignment variables reset to missing. `RETAIN name number;` and
`RETAIN name .;` initialize a numeric variable once; a repeated initializer uses
the last declaration. Uninitialized RETAIN lists are not implemented.

`WHERE predicate;` selects driving input rows before group formation. It can
reference only columns in that input. Subsetting `IF predicate;` runs in source
order after the input read and group flags. An ascending BY list after SET
provides `_N_`, `FIRST.key`, and `LAST.key`; flags propagate when a preceding
BY key changes. Automatic variables are excluded from output schema and rows.
`_N_` is also available without BY. Inputs must be sorted after WHERE selection.

Predicates accept a numeric truth value or one comparison (`=`, `^=`, `~=`, `<>`,
`<`, `>`, `<=`, `>=`, and EQ/NE/LT/GT/LE/GE). IF THEN accepts one assignment or
OUTPUT. Expressions accept atoms, two-argument ROUND, and `variable + atom` or
`variable - atom`. Implicit character/numeric conversions are refused except
for the explicitly gated numeric LENGTH-family conversion above.

Declarations and input descriptors establish column order and types before row
execution, including empty outputs and assignments inside skipped branches.
Version 1 serialized plans remain executable. The C++ pilot retains its scalar
numeric scope and blocks the new event, metadata, and expression operations.

## Typed catalog and metadata

Existing `"column": "number"` schemas remain supported. Descriptors can declare
`type`, `length`, `label`, and `format`:

```json
{
  "a": {
    "encoding": "utf-8",
    "schema": {
      "id": {"type": "character", "length": 3, "label": "Identifier", "format": "$3."},
      "day": {"type": "number", "length": 8, "format": "DATE9."},
      "reading": "number"
    },
    "rows": [{"id": "007", "day": 0, "reading": {"missing": "A"}}]
  }
}
```

SET, SORT, and OUTPUT preserve column descriptors. This transport contract also
carries the source table's optional label and encoding. Copying a variable by
assignment copies type and width, not its label or format. A format descriptor
is retained as metadata; the executor does not render SAS formats or infer a
date from one. Named-list PUT uses raw numeric values and trimmed character text.
The base-R metadata witness checks descriptors, byte counts, and value identity;
it is not a SAS-file reader or a metadata interchange library comparison.

Character lengths are bytes. `LENGTH name $ width;` must precede SET and
computations; otherwise the first literal assignment establishes width. Values
are blank-padded and subsequent assignments truncate to that width. A truncation
that splits a multibyte code point raises an error. Imported values exceeding
the declared width also fail instead of losing data. Supported encodings are
UTF-8, ASCII, and Latin-1; mixing input encodings requires explicit transcoding.
Character comparison pads the shorter operand with blanks. Sorting uses the
ordinal character order for these encodings, without linguistic collation.

Numbers are binary64. Ordinary missing is JSON null. Special missings use
`{"missing":"_"}` or uppercase A through Z, and literals `._`, `.A` through `.Z`.
Identity survives transport, assignment, and output; numeric order is underscore,
ordinary missing, A through Z, then finite numbers. Arithmetic with any numeric
missing yields ordinary missing. Boolean, text, non-finite, malformed, or
out-of-range numeric inputs fail validation.

## Comparison policy

CLI expected-output checks compare numeric values exactly, preserve type
boundaries, require row cardinality/order and schema column order, and compare
all descriptors and table metadata. JSON object property order within individual
rows is irrelevant. Integer 1 and binary64 1.0 are the same numeric value;
boolean true and string "1.0" are different. Comparisons do not round a large
integer to a float before checking it.

Synthesis remains an explicitly numeric CSV bridge. Its six families require
ordered rows and columns; CSV NaN and null represent the same ordinary missing.
Only rounding uses absolute tolerance 1e-10; the other five families use exact
numeric comparison. Every family prints its policy into the verification receipt.
CSV inference is not evidence of character, label, format, or tagged-missing
preservation; those use the typed catalog witnesses.

## Remaining boundaries

Multiple DATA destinations, general conditional SET, nested/grouped DO, sum
statements, LAG translation, macro execution, raw INPUT, format rendering, and
linguistic sort orders still require review. Character BY key width changes are
refused. MERGE retains its ordinary numeric, sorted, at-most-one-repeating-side
scope; tagged/character inputs, filters, explicit retention, and assignments to
MERGE input variables are refused. Modeling writes to MERGE input variables
requires a separate merge read-event implementation.

Garage research IDs SL003, SL004, SL005, SL006, and SL020 motivated these original
witnesses. They are not held-out SAS outputs, and the five imported mirrors were
not modified. The operational code and gates belong to Go; KB work remains with
the separate session.

## Primary behavior references

- [SAS OUTPUT statement](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n1lltvbis7ye1an1eryo4leh2mck.htm)
- [SAS WHERE versus subsetting IF](https://support.sas.com/documentation/cdl/en/lrcon/65287/HTML/default/p04fy20d8il3nfn1ssywe4f25k27.htm)
- [SAS variable reset rules](https://support.sas.com/documentation/cdl/en/lrcon/65287/HTML/default/p1x98c58fc4rgzn1jb5viwl5faz2.htm)
- [SAS RETAIN statement](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/p0t2ac0tfzcgbjn112mu96hkgg9o.htm)
- [SAS missing-value order](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a000989180.htm)
- [SAS character-length discussion](https://support.sas.com/resources/papers/proceedings14/1468-2014.pdf)
- [SAS PUT and _ALL_](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n1spe7nmkmi7ywn175002rof97fv.htm)
- [SAS named PUT](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n177esg96c9hkgn10bforsq2886s.htm)
- [SAS numeric LENGTH conversion](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/n0f6jve4kdxnh1n1m7c82fhosgih.htm)

## Bounded counted DO

DS-026 admits a single-level `DO index=start TO stop [BY step];` group in a
DATA step. Controls are signed ASCII integer literals, with magnitude at most
2**31-1, and a nonzero step that defaults to one. The loop is rejected before
execution when its trip count exceeds 10000. These limits bound the runtime;
they do not state SAS language limits.

The plan emits an ordinary numeric declaration immediately before a
`do_counted` operation. Its arguments are `index`, `start`, `stop`, `by`, and a
serialized `body` operation list. Static schema discovery and OUTPUT detection
recurse into the body even when its trip count is zero. Normal completion
leaves the index at its first value past stop. A zero-trip loop leaves start.
The index is an ordinary output column, while `_N_` counts DATA iterations.

Direct assignments and existing direct PUT/OUTPUT operations compose inside
the body. DS-031 additionally admits bounded IF/ELSE simple actions there;
SET, WHERE and retention keep their existing outside-body paths.
SET may drive several DATA iterations; each counted loop reinitializes its
index for that DATA iteration. Explicit OUTPUT anywhere in the step suppresses
bottom-of-step output, including a skipped zero-trip body.

Deferred cases include nested/grouped DO, WHILE/UNTIL, LEAVE/CONTINUE, subsetting
IF, variable or computed controls, writes to the index inside the body,
declarations or input operations inside the body, MERGE with DO, explicit
OUTPUT in DATA _NULL_ counted-DO steps, PUT _ALL_ combinations, and C++. These
are translator boundaries, not a claim that SAS rejects those programs.

Evidence: `examples/verify_do_counted.py`, original `examples/do_counted.R`, and
`saschi.test_do_counted` pin controls, final index, PDV order, zero-trip schema,
OUTPUT suppression, `_N_`, and SET composition. This is repository and
cross-language evidence for maintainer review, without live SAS verification.
The documented control rules come from the primary
[Base SAS iterative DO statement](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000201276.htm),
[SAS OnlineTutor](https://www2.sas.com/onlinetutor/linklib/doloop.htm), and
[Base SAS DATA-step execution](https://support.sas.com/documentation/cdl/en/lrcon/65287/HTML/default/n0fjj14wij8q3jn1qpsq5770xhs2.htm).
Inference: the zero-trip and final-index pins follow from initializing the
index to start and checking the control after each increment. The R witness
models that control explicitly rather than relying on R for-loop final state.

## Numeric-variable list output

Status: DS-027 repository evidence for maintainer review, not a live SAS log
capture or a general BEST12 implementation.

Simple `PUT n m;` uses `put_numeric_list` with normalized variable names when
preceding declarations or assignments establish every item as numeric. The
operation reads current PDV values. Ordinary missing prints as a period, and
finite integer-valued numbers with magnitude at most 99999999999 print decimal
digits without fractional places. Negative zero prints zero. Each field
advances one following blank, including the final field. Complete logical
records are at most 64 columns.

Source-order type knowledge is a conservative compiler boundary. Descriptor-only
numeric SET variables, unknown variables, automatic variables, mixed numeric and
literal/character items, numeric literals, formats, FILE, pointer controls,
fractions, nonfinite/nonnumeric values, and special missing
output remain refused. Numeric declarations provide the shared interface for the
separately gated counted-DO index. Source-order discovery includes body operations.

Runtime descriptor validation precedes row execution, including empty and
WHERE-filtered SET input. Attached numeric formats are refused; a plain numeric
copy does not inherit a format. Programs using this operation conservatively
refuse double-quoted source macro triggers and non-ASCII/control source literals
anywhere, including unused or prior-step values. Character-list, quoted-literal,
and named-list output retain their own paths. C++ refuses the new operation.

Original numeric pins, generated records, shared refusals, and an independent
base-R renderer live in `examples/verify_put_numeric.py` and
`examples/put_numeric.R`. `saschi.test_put_numeric` checks execution, descriptors,
source-order routing, final separators, whole-job failure, and target refusal.
The documentary sources are [Base SAS PUT List](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/p0jcwhe1ofmb49n1xf1q2kc44b0v.htm)
and [BESTw. Format](https://support.sas.com/documentation/cdl/en/leforinforref/63324/HTML/default/p1fum54c93f8r0n1wrs5mrb05nzi.htm).


## Counted DO and numeric PUT composition

Status: bounded repository and independent base-R evidence for maintainer review,
without live SAS verification. DS-026 and DS-027 compose through the ordinary
numeric loop-index declaration and source-order traversal of body operations.
Numeric PUT inside the body uses current PDV values. Static type discovery,
format validation, source guards, and OUTPUT detection also inspect zero-trip
bodies. Unsupported later output fails the complete job without publishing
earlier records or a partial result.

`saschi.test_do_put` and the independent `examples/do_put_program.R` witness
verify the unmodified external `loops_for_with_a_specified_step.sas` using source,
stdout, and complete-result hash pins. The witness reads that program in place;
no corpus source or derived output text is shipped. The two earlier complete
program proofs in `saschi.test_put_all` remain registered. Passing these three
programs does not establish equivalence for other corpus programs.


## Shared operation-tree analysis

The compiler and runtime validation use `saschi.operations.walk_operations` for
source-order preorder traversal of IF children and counted-DO bodies. Mixed
compiled objects and serialized nodes retain their original payloads. Static
schema/type discovery, OUTPUT target checks, descriptor validation and source
guards therefore share the control-container structure, including zero-trip
bodies. Conservative PUT guards also inspect structural containers of unknown
kinds; this does not admit those kinds for execution. Runtime IF/DO scheduling
and all operation allowlists remain separate from this read-only analysis.
`saschi.test_plan` pins traversal order, payload preservation, malformed-body
refusal, and skipped-body output-target diagnostics. Existing DO/PUT suites and
whole-program witnesses retain the execution contract.


## Character LENGTH lists and REVERSE

Status: DS-028 bounded repository and independent base-R evidence for maintainer
review, not live SAS. A single character LENGTH name group emits ordinary
`declare` operations in source order. Names must be unique ordinary ASCII
identifiers, width 1..32767, before SET and computations. Multiple width groups,
numeric lengths, variable ranges and declarations inside DO remain deferred.

`REVERSE` reverses all bytes of a nonempty printable ASCII value, including
leading and trailing blanks. Its new destination has the argument descriptor
width; an earlier destination keeps its own fixed width and assignment rules.
WHERE calls use the driving input descriptor before DATA-step LENGTH overrides
and PDV coercion. Static discovery uses `character_width(expr, schema=None)` and
`assign_spec(expr, schema=None)`, retaining existing one-argument call support.
Literal, copied and input character descriptors and supported REVERSE/PUT calls
provide widths before row execution. Recursive REVERSE-call validation also
runs for already-sized targets, nested numeric expressions, empty/filtered
input and zero-trip bodies. Numeric/unresolved widths and unsupported source
or value encodings fail atomically. Existing PUT refusals and C++ bounds stay
in place.

Original pins, generated cases and the raw-byte R witness are in
`examples/verify_length_reverse.py` and `examples/length_reverse.R`.
`saschi.test_length_reverse` reads the unmodified external reversal program in
place and checks source, stdout and complete-result hashes, the shared job path
and an independently parsed R program. No corpus source or derived output text
is included. The primary references are the [Base SAS LENGTH statement](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/p1hgqgmxm3dpqcn1d4w5za5qbz0d.htm)
and [REVERSE function](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/n0r87nwd0lt2rzn1h348larywe0r.htm).


DS-030 repairs SUBSTR destination descriptors and replaces the earlier global
quarantine with local consumer checks. Multi-name LENGTH and REVERSE over stored
SUBSTR variables are accepted. The temporary expression REVERSE(SUBSTR(...))
still requires storing the substring first; its temporary width is unclaimed.
The `length-list` matched marker records declaration grammar provenance without
adding a program-wide SUBSTR restriction. Local checks also apply to handwritten
plans and partial execution.

## Bounded character concatenation and CATX

Status: DS-029 repository and independent base-R evidence for maintainer review,
without live SAS equivalence. Operator chains use `{kind: concat, args: [...]}`
and preserve every character operand blank. The result descriptor is the sum
of source widths. Earlier target descriptors retain truncation and padding.
There are2..32 operands, nonempty printable ASCII, at most32767 bytes each and
in total. Arithmetic mixed into a chain is deferred rather than given guessed
precedence. Quoted operator text and operators inside function arguments remain
lexically separate from top-level chains.

CATX uses the existing call form with1..32 literal/variable character items or
direct checked SUBSTR items, and a literal/variable character delimiter. It trims ASCII spaces from item edges, skips blank items,
and preserves the delimiter. A new target is200 bytes. This slice admits direct
assignment RHS calls, including IF THEN assignments, with at most200 result
bytes. Actual target overflow is refused before assignment, preserving atomic
job failure rather than approximating SAS blanking, warnings and error flags.
Nested CATX, concatenation operands, function arguments, predicates and WHERE
remain refused because temporary-buffer behavior depends on context.

Source-order schema inference validates operand types even on empty or filtered
SET inputs and zero-trip loop bodies. New constructs impose source-wide macro
and ASCII guards even without PUT. Existing PUT blank-field/64-column rules,
PUT _ALL_ new-expression refusal and C++ refusal stay intact. All-blank CATX is
a padded blank target, not a successful nonblank PUT field.

Evidence: `examples/verify_concat_catx.py`, original `examples/concat_catx.R` and
`saschi.test_concat_catx`. The external `string_concatenation.sas` program is read
in place and checked by source/stdout/complete-result hashes, shared job results
and an independent original R parser. No external source or derived output text
is shipped. Primary documentary sources: [SAS operators](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a000780367.htm)
and [CATX](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/n0p7wxtk0hvn83n1pveisbcp2ae9.htm).


## Checked SUBSTR destinations and sources

Status: DS-030 repository/base-R evidence for maintainer review, no live SAS.
Three-argument SUBSTR accepts a nonempty printable ASCII character literal,
known character variable, or fixed-width REVERSE/concatenation source expression.
A new target inherits the first argument descriptor width. An existing target
keeps its own width and ordinary assignment truncation/padding. For example,
`x=substr('ABCDE',2,3)` stores `BCD` followed by two spaces in a five-byte target.
Raw extraction and destination storage are distinct contracts.

Position and length are finite positive integral numeric values, within the
source width and the implementation bound32767. Literal invalid bounds and
wrong expression types are refused even on empty/filtered input and skipped
bodies; dynamic bounds are checked when evaluated. WHERE validates against the
driving input descriptors before output PDV overrides. Invalid/error-state
behavior, implicit coercion, two-argument calls, Unicode/control values and
unproven temporary sources remain refused. The raw `sas_substr` helper and its
old fixture pins are extraction-only evidence, without destination/error-state
coverage; executable translation uses `sas_substr_checked`.

Evidence: `examples/verify_substr.py`, `examples/substr.R` and
`saschi.test_substr`. The semantics source and plain-text mirror stay identical.
The existing unmodified substring program retains source/stdout/complete-result
hashes, shared-job execution and its independent R program witness. Primary
reference: [Base SAS SUBSTR](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/n0n08xougp40i5n1xw7njpcy0a2b.htm).

## String-feature composition

Status: repository and independent R evidence for maintainer review, no live SAS.
The earlier program-wide SUBSTR quarantine is removed. Stored SUBSTR variables
compose with grouped LENGTH, REVERSE, concatenation and CATX, including copied
variables, input descriptors and cross-step SET. SUBSTR can extract from the
fixed-width REVERSE/concatenation source expressions described above.

CATX accepts direct checked SUBSTR items because trimming either a raw extraction
or its source-width-padded model gives the same item. This is a bounded
padding-insensitive inference, checked independently in R, not a claim about
SUBSTR temporary storage width. CATX retains direct-assignment syntax,
literal/variable delimiters and all result/destination-capacity limits.

Width-sensitive temporary consumers remain local refusals: REVERSE(SUBSTR),
SUBSTR concatenation operands or CATX delimiters, nested SUBSTR sources and
LENGTHC(SUBSTR). Store the substring in a variable before those consumers.
Existing padding-insensitive LENGTH/LENGTHN, direct comparisons and COUNT with
a constant nonempty space-free needle retain their bounded contracts. Source
macro/ASCII guards, C++ limits and atomic error-state refusals remain in force.
No ticket-metadata removal or partial-plan mode bypasses the local checks.

Evidence: `examples/verify_substr_compositions.py`, its original base-R twin
`examples/substr_compositions.R`, and `saschi.test_substr_compositions`, alongside
`saschi.test_string_composition`. The tests cover exact stored widths/values,
CATX raw/padded agreement, input-side WHERE, empty/filtered input, skipped bodies,
local refusals and late failures that publish no earlier records. All five
unmodified external whole-program proofs remain registered, without copying
external source or derived output text into this repository.

## Bounded conditional actions

Status: DS-031 repository/base-R evidence for maintainer review, no live SAS.
IF THEN can dispatch a simple assignment, existing PUT or OUTPUT. An immediately
following ELSE or ELSE IF becomes an optional `otherwise` child on the existing
`if` operation. The first true branch executes; later conditions/actions are not
evaluated. Chains are bounded to32 conditions. Existing numeric truth treats
zero/missing as false. Conditional ROUND operations remain deferred.

These actions are also permitted inside the existing literal counted DO. Both
branches are traversed statically in source order for schema, source guards and
OUTPUT suppression, including zero-trip or empty-input cases. Counted-body
validation recursively refuses index writes even in unreachable branches.
Nested/grouped DO, subsetting IF, input/declarations, PUT_ALL and unsupported
actions remain review cases, and the C++ pilot refuses this new surface.

`examples/verify_do_if.py`, its original base-R twin and `saschi.test_do_if`
verify scheduling, branch descriptors, source guards, atomic failure and the
unmodified external FizzBuzz program through source/stdout/complete-result
hashes, shared-job execution and independent R parsing. No external source or
derived output text is shipped.
