# Stateful execution and typed comparison, 0.3.0

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
`variable - atom`. Implicit character/numeric conversions are refused.

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

Multiple DATA destinations, general conditional SET, DO/ELSE loops, sum
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
