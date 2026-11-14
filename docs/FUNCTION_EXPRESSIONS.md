# Typed function expressions

Status: approved local composition-wave implementation for maintainer review.
The registrations below require matching source-stable full verification and
both unchanged 1k workload receipts. Independent original hand/base-R evidence,
not native SAS validation, external-program proof or publication authority.

The separate `function-expressions-v1` ordinary version 2 profile joins an
explicit cohort of 46 already registered functions. Existing accepted source
keeps its original plan and emitted bytes. The v1/v2 consumer modules and the
319-name scalar registry remain unchanged.

Character trees compose UPCASE, LOWCASE, TRIM, STRIP, TRIMN, COMPBL, PROPCASE,
DEQUOTE, CATS, CATX, TRANSTRN and SUBSTRN. Temporary bytes stay separate from
storage widths. Normalization, PROPCASE, DEQUOTE and SUBSTRN inherit their first
argument's width; CATS/CATX/TRANSTRN infer 200. Constructors and destinations
refuse overflow conservatively. Computed empty text remains distinct from a
stored blank. Empty source literals remain held. PROPCASE and CATX delimiters
stay literal printable ASCII of 1..64 bytes. SUBSTRN controls remain primitive
bounded integral values. TRANSTRN's nonempty target stays primitive with a
maximum 64-byte descriptor; computed replacement values have at most 64 bytes.

Numeric trees compose MIN, MAX, SUM, COALESCE, N, NMISS, LARGEST, SMALLEST,
ABS, SIGN, CEILZ, FLOORZ, INTZ, ROUNDZ and MODZ. Unary signs and addition or
subtraction require exact integer operands and checked intermediates within
+/-1,000,000. Validate both operands before missing propagation. Fractional
operator trees, multiplication, division and powers remain held. New-context
SUM ignores ordinary missing, returns missing for all-missing inputs and checks
every operand/result against the exact 2^-10 grid and magnitude bound. Other
calls retain their original measurement and zero-fuzz domains. Rank, unit and
divisor controls stay primitive; rank measurements remain integral. Summary
and measurement lists retain their original 32-value bounds.

Comparisons produce numeric 0/1 values and admit compatible expressions on
both sides. Ordinary numeric missing orders below finite numbers. Character
comparison pads the shorter temporary with blanks. Numeric zero and ordinary
missing are false; other admitted numeric values are true. Computed character
bridges and validators are qualified: MISSING, CMISS, LENGTH, LENGTHN, VERIFY
and the 12 registered ASCII position functions. VERIFY sets and position starts
retain their original primitive roles. No implicit type conversion is added.
The new grammar admits =, ^=, ~=, <, <=, >, >= and EQ/NE/LT/LE/GT/GE. Chained,
prefix and IN comparisons, tagged missing and WHERE-only operators stay held.
The new profile holds <>; older bounded consumer aliases remain unchanged and
retain their separate semantic-review question.

AND, OR and NOT also admit &, |, ^ and ~ in their qualified contexts.
An unquoted ampersand immediately followed by a name remains a held macro
reference; write a spaced `a & b` for the qualified Boolean alias.
SAS Group-I NOT binds before comparisons: `not a=2` means `(not a)=2`;
`not(a=2)` explicitly changes the tree. AND binds before OR. Every pure operand
of a reached compound predicate must be domain-valid, including a function
that a Boolean optimization could omit. This conservative admission policy is
not a universal native SAS evaluation claim. Statement IF and unvisited ELSE IF
predicates remain dynamically reached-only. ELSE associates with the nearest
unmatched IF. Static literals, types and descriptors validate on every path.

An earlier unmarked parse treats bare `not -2` as an undeclared numeric variable
named NOT followed by subtraction. Its source/plan compatibility remains a
separate legacy semantic-review boundary, like the older <> alias. The new
marked profile qualifies NOT over signed operands when the source requires
this expression profile; it does not promote that legacy parse as SAS evidence.

IFN and IFC accept numeric expression or predicate conditions and correctly
typed computed choices, including an optional distinct missing choice. Every
argument of a reached selector is evaluated and validated before selection.
IFC infers200bytes; each reached choice must fit 200 actual bytes. Qualified
empty temporary choices are admitted. Primitive character descriptors retain
the original 200-byte choice limit. Selectors may nest inside other qualified
trees within the same type, call-depth and buffer budgets.

One top-level subsetting IF is qualified in a single-input step with implicit
output. It runs at its statement position. A false predicate stops later work
for that row; earlier assignments and logical PUT records retain their timing.
Descriptors still form for skipped later assignments and empty results.

One WHERE is qualified on the original driving input descriptor, before body
execution. Computed-only variables and automatic state are refused. Whole input
catalog validation precedes filtering. WHERE and a later subsetting IF retain
their distinct times, with one predicate of each kind allowed. Explicit OUTPUT,
multiple inputs, additional WHERE statements and multiple subsets remain held.

Every marked step has one exact leading profile marker justified by a new
admitted expression or context. Source and portable validation check exact
program, step, operation and node fields, argument roles, declarations and read
order before recursive legacy walkers. Caps are 16 steps, 256 operations/step,
128 calls/step, four call levels, expression depth 16, conditional action depth 16,
structural depth 64, 16,384 containers/step and 4,096 provenance rows. Cycles, invalid
scalar types, unknown fields and missing/moved/duplicate/unnecessary markers
refuse. Declaration operations, lengths and display names must agree.

LENGTH preserves other input descriptor attributes, including labels and formats.
New assigned copies inherit their type and width without inheriting formats.
PUT requires unformatted variables and source whitespace after a literal before
a variable; special controls retain their separate output profiles.

Numeric consumption keeps the 1,000,000 magnitude bound; position controls keep
their separate integral domain. Input metadata and column order are preserved.
Logical PUT reuses its existing helpers, including integer numeric output,
blank-character refusal and 64-column limits. A late fault publishes no partial
result or emitted stdout. Caller inputs and plans remain unchanged.

Stateful calls, queues, CALL routines, arrays, loops, BY/MERGE, RETAIN, sum
statements, macros, FCMP, SQL, C++ and specialized binary64 joins remain held.
Separately qualified older profiles retain their own execution boundaries.

Each original below has complete ordered hand/R/runtime/emitted/actualCLI
comparisons, 30 generated complete R catalogs including empty input, and six real
CLI mismatch controls for values, types, metadata, row order, column order and
logical output. The 46 contextual kernel pins also compare independent hand/R
values. Source suites exercise static skipped/empty checks, malformed portable
plans, resource boundaries, deterministic emission, profile coexistence,
nonmutation and working-prefix/late-fault atomicity.

| Stage or finish program | Original complete program | Registered gate |
| --- | --- | --- |
| 1. character-expressions | [expression_characters](../examples/expression_characters_capture.sas) | [verify](../examples/verify_expression_characters.py) |
| 2. numeric-expressions | [expression_numerics](../examples/expression_numerics_capture.sas) | [verify](../examples/verify_expression_numerics.py) |
| 3. comparisons-and-truth | [expression_comparisons](../examples/expression_comparisons_capture.sas) | [verify](../examples/verify_expression_comparisons.py) |
| 4. boolean-conditions | [expression_booleans](../examples/expression_booleans_capture.sas) | [verify](../examples/verify_expression_booleans.py) |
| 5. selector-expressions | [expression_selectors](../examples/expression_selectors_capture.sas) | [verify](../examples/verify_expression_selectors.py) |
| 6. subsetting-if | [expression_subset](../examples/expression_subset_capture.sas) | [verify](../examples/verify_expression_subset.py) |
| 7. where-composition | [expression_where](../examples/expression_where_capture.sas) | [verify](../examples/verify_expression_where.py) |
| 8. record-eligibility-and-normalization | [record_eligibility](../examples/record_eligibility_capture.sas) | [verify](../examples/verify_record_eligibility.py) |
| 9. measurement-exception-triage | [measurement_triage](../examples/measurement_triage_capture.sas) | [verify](../examples/verify_measurement_triage.py) |

The [approved wave plan](NEXT_DATA_STEP_WAVE_4.md) records scope, documentary
authority and the unchanged-source preservation requirements.
