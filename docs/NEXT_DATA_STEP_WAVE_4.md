# Fourth DATA step wave: expressions, conditions and filtering

Status: principal-approved local implementation scope for maintainer review,
prepared on 2026-11-13 from merged commit
`08bf3910e4179f0d70451736841a1fadac6991c3`. The principal selected connecting
existing functions through broader expressions and conditions, then explicitly
approved all seven stages and both finish programs in order, with full
verification and both workloads passing at each stage. The body retains the
engineering proposal; each stage still needs its frozen contract and evidence.
No new scalar function, external-program proof, native SAS validation or
publication is implied by approval.

Recommendation, an engineering inference: build one bounded typed expression
profile, then qualify its use in decisions and filtering. Reuse the functions
already proved rather than choosing another collection of names. Stage order
reflects semantic dependencies and oracle isolation, not measured source
frequency or projected corpus completions.

## Accepted foundation and observed boundary

[PR78](https://github.com/buntas-tofu/SASchi-Go/pull/78) merged the
[third function wave](FUNCTION_WAVE_3_COMPOSITION.md). Its accepted source passed
137 fixture gates, 101 suites and 2,032 tests with zero skips, synthesis and both
unchanged 1k workloads. The workloads retain 18 ledger and 21 text checks. Those
are recorded outcomes for that accepted source, not a fresh full run for this
planning document.

The [v1 consumer profile](FUNCTION_CONSUMERS.md) admits finite normalization
chains, selected CATS items and selected function-to-literal IF comparisons.
The [v2 consumer profile](SELECTION_CONSUMERS.md) adds particular IFC, IFN, CATS
and TRANSTRN trees. Neither is a general typed expression contract. Their
modules, markers, existing source cases and emitted programs must remain
independently valid.

Planning probes using unchanged accepted translator code confirmed 28 blocked
composition forms, four in
each proposed stage, alongside 10 compiling positive controls. These are
original compile-only probes, not runtime or complete-signature proofs. Three
focused runtime observations also confirmed existing simple WHERE behavior and
both outcomes of simple computed subsetting IF. Those observations are local
baseline controls, not independent R, emitted-code or CLI comparisons.

Simple subsetting IF and WHERE already exist. This proposal joins them to the
new expression contract; it does not claim to introduce either statement.
The broader function inventory screened before the principal selected this
direction remains unselected. No additional function family is part of this
proposal. The functions/CALL universe in the
[capability manifest](capability-manifest.json) remains null.

## Proposed execution envelope

Use a new ordinary version 2 DATA-step profile, provisionally named
`function-expressions-v1`. Give each participating step one exact leading
profile marker and independently validate portable plans. A real newly admitted
expression or context must justify the marker. Existing accepted forms keep
their original profile selection.

The new profile initially admits one driving SET input, or a bounded scalar
step without input, with declarations, assignments, IF/THEN/ELSE decisions and
existing qualified logical PUT operations. Later stages add the specified
filtering contexts. Supplied catalogs and prior-step datasets use the existing
typed input contract. The new subsetting-IF and WHERE joins require one driving
input and implicit output; explicit OUTPUT joins remain held in those steps.

Proposed engineering caps are 16 DATA steps per program, 256 operations and
128 calls per step, four nested call levels, expression depth 16, structural
depth 64 and 16,384 containers per step. Retain the v2 provenance cap of 4,096
matched rows. Freeze precise counting rules before implementation. Check source
budgets before recursive parsing and portable budgets before every legacy
recursive walker. Cycles, excessive fan-out, unknown fields and invalid scalar
types must refuse deterministically.

Stateful functions, LAG/DIF queues, CALL routines, arrays, loops, BY/MERGE,
RETAIN, sum statements, multiple inputs, macros, FCMP, SQL, C++, procedure joins
and specialized binary64 profiles remain outside this new profile. In
particular, existing SQRT/LOG evidence does not authorize moving those calls
into this profile. Older independently qualified execution remains available.

## Existing function cohort and argument roles

The proposed cohort contains 46 already registered names with existing gate
paths. This is an admission list for composition research, not 46 new
capabilities or a claim that every signature composes. Each implementation
stage must freeze the exact argument-role and temporary-value matrix first.

| Role | Existing names | Proposed composition boundary |
| --- | --- | --- |
| Character transformation | UPCASE, LOWCASE, TRIM, STRIP, TRIMN, COMPBL, PROPCASE, DEQUOTE | Typed character children; explicit literal PROPCASE delimiters; independently qualified empty and padded temporaries |
| Character construction and extraction | CATS, CATX, TRANSTRN, SUBSTRN | Character items and source may be trees; literal CATX delimiter; existing bounded SUBSTRN position/length controls; qualified TRANSTRN deletion |
| Numeric summaries and selection by rank | MIN, MAX, SUM, COALESCE, N, NMISS, LARGEST, SMALLEST | Numeric child trees within each existing domain; primitive bounded rank controls; at most 32 measurements or summary arguments |
| Numeric transformation | ABS, SIGN, CEILZ, FLOORZ, INTZ, ROUNDZ, MODZ | Existing finite and missing policies; qualified numeric children; existing dyadic unit/divisor restrictions retained |
| Character/numeric bridges and validation | MISSING, CMISS, LENGTH, LENGTHN, VERIFY, ANYALPHA, ANYDIGIT, ANYALNUM, ANYSPACE, NOTDIGIT, ANYLOWER, ANYUPPER, ANYPUNCT, ANYXDIGIT, NOTALPHA, NOTALNUM, NOTSPACE | Typed child expressions in value positions; primitive bounded search starts; qualified VERIFY sets; no implicit numeric/character conversion |
| Conditional selection | IFN, IFC | Numeric expression or predicate condition and correctly typed expression choices; all reached call arguments evaluated |

Option, modifier, delimiter, rank, position, unit and divisor arguments do not
gain arbitrary expressions by appearing in this table. Freeze which remain
literal and which retain primitive variables. Validate each computed argument
at the consuming function boundary. A type-correct result can still lie outside
that function's admitted domain.

The initial arithmetic join is unary signs and exact bounded integer addition
and subtraction, with ordinary missing propagation and checked intermediates.
Keep operands and nonmissing results within +/-1,000,000. Multiplication,
division, powers, general rounded arithmetic and arbitrary fractional operator
trees remain held. Existing function results retain their separately qualified
policies; a fractional result is not implicitly admitted to integer arithmetic.
Freeze summary precision and intermediate bounds independently before nesting
those calls.

## Seven acceptance stages

Each row needs an original full-program hand/base-R witness, its own registered
gate and source suite. Complete the source-stable full run and both unchanged
workloads before advancing to the next row.

Representative admission targets, currently blocked forms rather than runnable
examples:

```sas
canon = upcase(compbl(strip(dequote(code))));
score = sum(abs(a),abs(b),largest(k,c,d));
if largest(k,a,b)>=coalesce(limit,0) then hit=1;
status = ifc(notalnum(code)=0 and lengthn(strip(code))>=limit,'OK','REVIEW');
```

| Stage | New join | Contract and discriminating witness |
| --- | --- | --- |
| 1 | Recursive character expressions | Compose the selected transformations, builders and extraction by type and argument role, within depth four. Compare empty temporaries, stored blanks, multiple nested items, inferred and declared widths, buffer faults and exact metadata. |
| 2 | Recursive numeric expressions | Compose summaries, rank and numeric transforms, including integer arithmetic arguments. Distinguish SUM from missing-propagating addition; validate rank controls, missing inputs, intermediate limits and zero-fuzz domains at every call. |
| 3 | Comparisons as values and decisions | Admit compatible expressions on either side, numeric function truth and stored numeric 0/1 comparison results. Prove ordinary missing ordering, character blank padding, swapped operands, nonliteral thresholds and type refusals. |
| 4 | Compound Boolean expressions | Add AND, OR, NOT, grouping and qualified symbol aliases with SAS precedence. Use truth-table pins, mixed missing/zero/nonzero values, precedence counterexamples and the conservative function-domain policy below. |
| 5 | Selectors over expressions | Admit the frozen IFN/IFC argument matrix, computed choices, predicate conditions and selectors inside other qualified trees. Separate eager selector arguments from reached-only statement branches, including invalid unselected choices and character widths. |
| 6 | Composed subsetting IF | Join the new expressions and predicates to one top-level subsetting IF in a single-input step with implicit output. A false condition ends that iteration before later assignments or PUT operations; prior work and descriptor formation retain their timing. |
| 7 | Composed WHERE | Join typed expressions and predicates to one WHERE on the original input descriptor, before DATA-step execution. Reject computed-only variables and automatic state. Prove its timing separately from stage 6, including excluded rows with body-domain faults. |

These are seven incremental contracts, followed by the two original compositions
below: at least nine original program gates. Actual registration, rule and test
counts follow the implementation splits and passing receipts.

## Decisions to freeze before parser changes

**Temporary character values.** Track a temporary's bytes separately from its
maximum or declared width. Do not store and pad an intermediate merely because
Python finds that convenient. Freeze empty STRIP/TRIMN and one-blank TRIM,
TRANSTRN deletion, SUBSTRN boundaries, builder buffers and IFC destination
inference across runtime, emission and CLI. Existing helper refusals remain in
their old contexts; new contextual semantics need their own canonical reference
evidence. Exclude REVERSE, LEFT/RIGHT chains, CAT/CATT nesting, raw concatenation
and dynamic format conversion from the initial cohort.

**Truth, comparisons and syntax.** Ordinary numeric missing and zero are false;
other admitted numeric values are true. Numeric missing orders below nonmissing
numbers. Character comparison needs its own blank-padding policy, not Python
string equality. The [SAS operator reference](https://support.sas.com/documentation/cdl/en/lrcon/65287/HTML/default/p00iah2thp63bmn1lt20esag14lh.htm)
also places unary NOT differently from familiar SQL conventions. Freeze the
parse tree before evaluation. R's NA and Python's truth rules are not oracles
for these cases.

Initially qualify `=`, `^=`, `~=`, `<`, `<=`, `>`, `>=` and EQ/NE/LT/LE/GT/GE;
AND/OR/NOT and ASCII `&`, `|`, `^`, `~` in their proper contexts. Hold chained
comparisons, implied AND, IN lists, prefix comparisons and WHERE-only operators.
Hold `<>` in this new profile: the reference distinguishes the DATA-step MAX
operator from WHERE's NE spelling. Older consumer profiles already accept a
bounded `<>` comparison alias; preserve that compatibility boundary and record
its separate semantic-review question. Do not silently copy it into the new
grammar or rewrite old accepted plans. SAS also documents a
[DATA-step versus SQL NOT difference](https://support.sas.com/kb/51/054.html).

**Evaluation and conservative admission.** Every argument of a reached IFN/IFC
call is evaluated before selection. A statement IF or an unvisited ELSE IF does
not dynamically evaluate its skipped branch. Keep static literal, type and
descriptor validation on skipped paths and empty inputs. The distinction is
documented in [SAS's IFN evaluation guidance](https://blogs.sas.com/content/iml/2017/06/07/ifn-function-versus-if-thenelse-sas.html).

SAS's [short-circuit discussion](https://blogs.sas.com/content/iml/2019/08/14/short-circuit-evaluation-and-logical-ligatures-in-sas.html)
does not specify all function-containing cases. Proposed admission policy:
compound Boolean expressions require domain-valid pure function operands,
including operands a Boolean optimization might omit. Reject an invalid
potential function operand as a whole-job domain refusal. This is a conservative
repository boundary, not a native SAS evaluation or diagnostic claim. Nested
statement IF remains the way to guard a dynamic invalid call. Qualify this
policy independently; do not infer universal host-language short circuiting.
No stateful or external function enters these trees.

**Filtering time.** WHERE reads original input fields and runs before DATA-step
calculations; subsetting IF runs at its statement position and can read computed
fields. See [SAS's comparison of the two forms](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a001000521.htm).
Keep original catalog validation and descriptor checks even for excluded rows.
Do not push a subsetting predicate upstream, move a body call across WHERE or
erase observable earlier work. Explicit OUTPUT interactions, WHERE= data-set
options, multiple WHERE statements, indexes and filtered BY groups stay held.

**Profile isolation and transport.** Use one typed expression contract across
source, portable execution and emission. Exact node shapes, allowed operators,
arity, argument roles, resource limits and type checks must run independently
of source parsing. A malformed new node must not reach a legacy recursive
walker first. Preserve caller inputs and plans. Profile dispatch is per step;
any coexistence with old v1/v2 steps needs complete program validation and both
ordering controls. Multiple profile markers in one step remain refused.

## Two whole-program finish lines

1. **Record eligibility and normalization.** Read a supplied mixed catalog;
   compose normalization, extraction, validation and identifier construction;
   compute a decision from both numeric and character expressions; assign IFC
   statuses and apply a computed subsetting IF. A distinct input-filtered step
   demonstrates the WHERE contract. Include blanks, padded fields, mixed case,
   empty temporary values, nonliteral thresholds and rows rejected at different
   points. Compare all fields, widths, metadata, row order and logical output.
2. **Measurement exception triage.** Combine bounded differences, ABS, missing
   summaries, rank, zero-fuzz rounding, IFN and grouped conditions over supplied
   measurements. Contrast an input WHERE rank guard with a later subsetting IF;
   preserve reached-only statement guards and eager selector failures. Include
   all-missing and partial rows, tied ranks, zero/negative values, exact half
   ties, skipped branches and a late fault after a successful prefix.

Freeze both complete original hand tables and independently authored base-R
programs before translator changes. Include at least 30 generated complete
catalogs per finish program, including empty input. R witnesses need explicit
SAS truth, missing and character rules; native R logical operators alone are
insufficient. Generation supplements the original whole-program expectations.
Neither original is an external-program proof. Numeric PUT keeps its existing
qualified integer contract; fractional results remain dataset comparisons.

## Acceptance, preservation and next action

1. Record the principal's decision on this concrete scope before implementation.
   Planning direction alone does not approve the seven stages. Recheck main,
   the source and the project contract if the checkout has advanced.
2. Prepare the existing locked environment, doctor, pinned sibling corpus and
   explicit vendor/postal caches. Obtain an unchanged golden baseline and both
   unchanged 1k workloads on one stable entry source. Keep desktop checks and
   record actual outcomes, including failed attempts.
3. Freeze the role matrix, numerical and temporary policies, source sections,
   independent hand/R oracles, parser design and resource accounting before
   implementation. Resolve any source contradiction before admitting the
   affected shape. Narrowing or substituting an approved stage requires an
   explicit recorded scope decision.
4. For every stage and finish program, compare complete runtime, emitted Python
   and actual CLI results: values, types, descriptors, metadata, table/column/
   row order and separately qualified logical output. Prove empty/skipped
   paths, wrong portable plans, exact boundary refusals, deterministic emission,
   caller nonmutation and late atomic failure.
5. Give each wrong value/type/order/metadata/column-order/log comparison a fresh
   output directory and require its receipt to identify the intended mismatch.
   A nonzero exit alone is insufficient. Every late-fault case needs a working
   prefix control and no published partial result or partial emitted stdout.
6. Preserve the existing 137 fixture registrations and 101 suites in order,
   165 rule objects, 80 runtime-capability objects, prior canonical reference
   helpers, earlier oracle/gate files, dependency locks, capability-manifest
   bytes and pinned corpus. Audit old plans and emitted bytes, including both
   consumer versions. Reconcile overlapping source-refusal assertions with
   explicit old-profile refusals and distinct new-profile positive evidence.
7. Accept each stage, then each finish program separately, only after
   source-stable ALL VERIFIED and both unchanged workloads. Re-screen external
   inventories at the finish without promising a completion. Add a whole-file
   proof only with independent complete unchanged-source execution evidence.
   Make no publishable edits while a full run or its workload checks are active.

No new runtime dependency is proposed. Keep raw receipts, reference bodies,
environment details and planning probes outside the publication set. Validate
the plan with the invariant linter, strict sanitization, manifest schema and
local-link checks. This local implementation approval requests no commit, push,
PR, merge or release.
