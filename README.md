# SASchi-Go

Reproducing SAS behavior in open languages (Python, R) with receipts.

The AE85 to SASchi-Roku's AE86: the quiet workhorse underneath the legend.
This repository holds the migration toolchain: reference implementations of
SAS semantics, gold-pair fixtures that prove cross-language agreement, and
the rulebook for translating SAS constructs. The corpus it is tested against
lives in the sibling repository, [SASchi-Roku](https://github.com/buntas-tofu/SASchi-Roku).

The core claim: a translated program is accepted because it ran and its
numbers matched, not because it looked right. The gates combine hand-pinned
truth, Python/R comparisons and typed execution checks under explicit comparison
policies. Receipts record what passed for the source and environment tested.

## Current verification

Status: version 0.4.0 development evidence for maintainer review, checked on
2026-10-30. With the pinned Roku corpus present, `python verify_all.py` passes
67 fixture gates, 51 suites and 1061 tests with zero skips. Synthesis adds 60/60
faithful passes and catches 60/60 naive variants. Receipts bind these results to
the recorded source and environment; live-SAS validation remains outstanding.

Nineteen unmodified external programs pass complete-program repository/base-R checks.
The two B5 programs use declared numerical tolerances and an inferred logical text
policy; exact SAS BEST12/DECIMALCONV remains unproved. Earlier programs include
FizzBuzz, the day-of-the-week calendar program and `loops_do_while.sas`, whose
body-first DO UNTIL composes with a retained sum statement. `loops_while.sas`
adds bounded division, safe INT and pre-test DO WHILE composition. The bitwise program remains
an explicit 67-column output refusal under the unchanged 64-column profile. See the
[stateful execution contract](docs/STATEFUL_EXECUTION.md) for the supported slices
and their remaining boundaries.

Bounded numeric ARRAY declarations, indexed reads/writes and SUM OF now execute
with original source pins and independent base-R evidence. Arrays alias row
variables, preserve descriptors and retain the existing output/receipt paths.
See the [numeric-array profile](docs/NUMERIC_ARRAYS.md). The separate
[DO OVER profile](docs/DO_OVER.md) adds single-level implicit numeric current-element
iteration and the complete unmodified `loops_foreach.sas` proof. DO OVER nesting,
shared implicit indices and broader array forms remain deferred. The separate
[A2 counted-loop profile](docs/COUNTED_LOOPS.md) adds bounded nested/computed
counted loops, captured controls and original complete-program/base-R proofs.
[A3 mixed PUT](docs/MIXED_PUT.md) composes literals with bounded numeric fields.
The entire unchanged `100_doors.sas` now passes source/result/stdout pins,
independent base R and the divisor-parity hand check: ten doors remain open.
[B1 TRIM/STRIP](docs/TRIM_STRIP.md) preserves fixed descriptors while shortening
concatenation operands. Both DATA steps of unchanged `loops_for.sas` now pass
complete source/result/stdout pins and independent base-R accounting.

Bounded numeric list INPUT with CARDS/DATALINES now drives scalar DATA steps,
including FLOWOVER, record release and incomplete-EOF handling. The complete
unchanged `integer_comparison.sas` agrees with its hand truth table and independent
base-R witness. See the [numeric inline-input profile](docs/INPUT_LIST.md).

[B3 numeric composition](docs/NUMERIC_COMPOSITION.md) adds bounded exact
multiplication and output-only numeric discovery. The entire unchanged
`sum_and_product_of_an_array.sas` computes the sum of100 squares and leaves its
unassigned c missing. The A0 companions prove the entire hello-world source and
explicit comment-only no-op without expanding the language profile. All three
have source/result/stdout pins, independent R accounting and actual CLI evidence.

[B4 projection](docs/PROJECTION.md) separates KEEP/DROP output selection from
DATA output options and SET input options. Working variables and descriptor order
follow the documented timing contract. Other declarations and options remain
separate profiles. [B5 bounded arithmetic](docs/BINARY64.md) adds an explicit
binary64 profile for rounded scalar operations, integer powers, Pi and six
trigonometric functions. The unchanged series and trigonometry programs pass
complete source, independent sequential R, emitted Python and CLI witnesses.
Their numerical tolerances and inferred logical decimal text policy are separate
contracts. Exact SAS BEST12/DECIMALCONV and live-SAS equivalence remain unproved.
Earlier exact arithmetic and integer-output plans keep their previous contracts.

[C1+C2 numeric rows](docs/NUMERIC_ROWS.md) combines rounded scalar calculations
with KEEP/DROP and one numeric SET per step. A distinct binary64-rows-v1 marker
preserves earlier profile admission and serialized shapes. Supplied and
prior-step produced tables have independent witnesses for input selection,
retention, scratch reset and output snapshots. Every selected input descriptor
and value validates before row execution. This adds composition evidence without
claiming another complete external-program proof.


[D4a SQL creation](docs/SQL_CREATE.md) adds descriptor-only empty tables from
one explicit CHAR-column declaration inside bare PROC SQL and QUIT. The complete
unchanged postal-address source now has independent R, ordered descriptor,
empty-result, emitted Python and CLI evidence. Every existing destination refuses.
Query creation, numeric columns, DML and general PROC SQL remain separate.

D1 now composes the bounded rounded profile with numeric inline INPUT, numeric arrays/current aliases/ordered SUM OF, and existing WHILE/UNTIL. Four separate gates include a complete measurement-stream witness; exact indices, converter/trip limits, older markers and inferred text policies remain. See [numeric pipelines](docs/NUMERIC_PIPELINES.md).

D2a separately gates inline comma DLM/FIRSTOBS and numeric INPUT name ranges. DLM collapses empty comma spans; this profile preserves exact input conversion and FLOWOVER, and defers DSD, quoted/general CSV and numerical-pipeline composition. See [bounded comma and range input](docs/INLINE_CSV.md).

## Operational workflow

The typed execution workflow and C++ scalar pilot use a shared, versioned
operation plan. See [Operations](docs/OPERATIONS.md) for installation, the CLI,
explicit scope, receipts, and peer synchronization. The composed example in
[examples/workflow/](examples/workflow/) runs rounding, sorting, and a one-to-many merge against a
pinned result and a base-R counterpart. Python executes bounded typed datasets;
C++ currently supports scalar DATA _NULL_ programs. Julia remains an extension
option. Algorithm redesign must preserve a stated behavior contract.

[Workload testing](examples/workloads/README.md) adds two original composed
programs with independent base-R witnesses: a numeric monthly ledger and
character-heavy events with many short groups. CI runs both at 1000 input rows,
including hand pins and refusal/comparator controls, and retains failure
diagnostics. Standalone runners support scale tests through 100000 rows. Exact
comparisons and receipt behavior decide acceptance; RSS/timing remain informational.
These synthetic workloads do not add external-program or live-SAS validation claims.


The [stateful execution contract](docs/STATEFUL_EXECUTION.md) adds typed expected
comparisons, explicit OUTPUT snapshots, WHERE/IF timing, retained variables, and
character/metadata preservation. [examples/events/](examples/events/) provides a runnable job with
fixed expected output and base-R evidence. Special missings retain their tags.

## Layout

- [sas_semantics.py](sas_semantics.py) : reference implementations of SAS-quirk functions
  (round half away from zero, INTCK/INTNX, missing-value ordering, character
  truncation, merge mechanics, formats, and the family). The verifier's law.
- [examples/](examples/) : gold pairs. Each SAS construct gets a faithful Python and R
  sibling plus a fixture verifier (`verify_*.py`). Run any verifier directly,
  or all of them through [verify_all.py](verify_all.py).
- [docs/sasconversionrulebook.json](docs/sasconversionrulebook.json) : the machine-consumable translation
  rulebook. 97 rules with equivalence classes (EXACT,
  EQUIVALENT-WITH-SETTINGS, APPROXIMATE, NO-DIRECT-EQUIVALENT), required
  settings, forbidden patterns, and validation tests.
- [docs/capability-manifest.json](docs/capability-manifest.json) : the coverage manifest. Enumerated entries of
  the SAS reference documents each carry one disposition (GATED, RULE,
  POLICY, HUMAN-REVIEW, DOCTRINE, OUT-OF-SCOPE, or UNASSESSED). GATED entries
  declare bounded reference-fixture or source-execution evidence; a guidance rule
  alone does not prove execution. Only two reference areas are enumerated, so
  the catalogue supplies no whole-SAS coverage percentage.
  [examples/verify_capability.py](examples/verify_capability.py) checks evidence
  scopes, registrations and rollups. [The coverage backlog](docs/COVERAGE_BACKLOG.md)
  reconciles the current gates and prioritizes the next composition proofs.
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) : the user guide: running the gates, reading the
  receipts, understanding the equivalence classes, and verifying a new
  construct family.
- [saschi/](saschi/) : the program-level translator package (Track A). [parser.py](saschi/parser.py)
  preserves statement fences, [rules.py](saschi/rules.py) loads the rulebook and
  routes constructs, and the shared plan drives Python typed dataset execution
  and a C++ scalar backend. Tests: [saschi/test_parser.py](saschi/test_parser.py),
  [saschi/test_rules.py](saschi/test_rules.py), [saschi/test_emit_py.py](saschi/test_emit_py.py).
- [saschi/job.py](saschi/job.py) : the shared job path (compile, translate, run, compare,
  receipt) that the run command, the web workbench, and the showcase all
  render from, so what is shown is what ran.
- [saschi/catalog.py](saschi/catalog.py) : the DuckDB analysis layer. Every job records its pass
  (statements with the construct and rule they routed to, the functions
  recognized in code rather than inside string literals, the plan's tickets,
  and the run summary) into a catalog, and the receipt carries the resulting
  accounting under `completeness`. Completeness is a query, not a print
  statement. duckdb ships in the verify extra, so a base install still runs
  jobs and the receipt says `status: unavailable` with the reason.
- [saschi/web.py](saschi/web.py) + [saschi/web/static/](saschi/web/static/) : the web workbench. `saschi serve`
  runs a standard-library HTTP server (no new runtime dependency) with a JSON
  API over the job path, a program shelf, a paste-and-run box, and an
  assistant pane that is environment-configured and off by default.
- [saschi/showcase.py](saschi/showcase.py) : the showcase generator. `saschi showcase` renders a
  job as a self-contained single-file HTML document with the checksummed
  receipt embedded.
- [kb01/sas_semantics_reference.txt](kb01/sas_semantics_reference.txt) : the semantics reference as plain
  text, for humans and for diffs.
- [manifest.py](manifest.py) : pin a SAS corpus with content hashes and provenance.
- [synth.py](synth.py) : program-level synthesis across characterized construct
  families, seeded and deterministic. Runs cross-language and reference
  gates; the live-SAS capture stage is optional and license-gated.
- [verify_all.py](verify_all.py) : runs every fixture gate, emits a checksummed receipt JSON.
  One command, the whole proof.
- [tools/macro_census.py](tools/macro_census.py) : token census of the macro surface across the
  licensed public testbed, deterministic, pure stdlib. Outputs the
  frequency table in [docs/macro_surface_census.md](docs/macro_surface_census.md) plus a CSV.
- [docs/macro_surface_census.md](docs/macro_surface_census.md) : the macro-surface frequency table with
  method and NOTICE (which public repos were counted, under which
  licenses). Data about code, never code itself.
- [AGENTS.md](AGENTS.md) : the agent contract under the Inertia-Drift-Framework, the
  buntas-tofu principal GLOBAL plus this project's LOCAL layer.
- [agent-manifest.json](agent-manifest.json) : machine-readable project descriptor, validated
  against the bundled schema in CI.
- [scripts/inertia-drift-lint](scripts/inertia-drift-lint) : the DMF invariant linter (fences, pointers,
  manifest shape, status lines, style floor). Runs in CI on every push.

## Running the gates

Requires Python 3.11+ and R (for the R halves of the gold pairs).
The complete verification profile, including the compiler and wheel-build
tools, is described in [Operations](docs/OPERATIONS.md). The unified command
also builds and executes the installed wheel away from the source checkout.

```sh
python verify_all.py
```

Each verifier also runs standalone, e.g. `python examples/verify_merge.py`.
The R interpreter is found via `ROSETTA_RSCRIPT`, then `Rscript` on PATH.
[verify_all.py](verify_all.py) writes its receipts under `telemetry/` (gitignored).

## Known landmines (why the gate exists)

- MDY/WEEKDAY use the SAS day epoch and Sunday-one weekday numbering. DS-033
  gates valid dates from 1753 through 3999 with integral numeric arguments,
  independent base-R comparisons and the unmodified external day-of-the-week
  program. Two-digit years, invalid/missing inputs, fractional days and wider
  calendars require review ([calendar gate](examples/verify_calendar.py),
  [source execution suite](saschi/test_calendar.py)).

- PUT _ALL_ writes the complete ordered PDV, including uninitialized numeric
  references and the automatic variables. DS-025 gates a bounded scalar slice
  with original pins, independent base-R records, and execution of two
  hash-pinned external Roku programs. Numeric LENGTH-family arguments return
  12 through SAS's right-justified BEST12 conversion. Source and result hashes
  are checked without copying corpus code. See the [stateful contract](docs/STATEFUL_EXECUTION.md)
  for the 64-column, numeric-format, expression, and diagnostic-log boundaries
  ([examples/verify_put_all.py](examples/verify_put_all.py), [saschi.test_put_all](saschi/test_put_all.py)).

- MOD takes its nonzero result's sign from the dividend. Python `%` and R `%%`
  take the divisor's sign instead. DS-013 now gates exact integer MOD within
  binary64 magnitudes of 2**53; missing, nonfinite, fractional, oversized, and
  zero-divisor inputs require review. Fractional SAS fuzzing and log diagnostics
  remain unmodeled, and INT remains unwired ([examples/verify_mod.py](examples/verify_mod.py)).
- Quoted-literal PUT inserts no separating blank. Spaces inside literals remain
  significant; doubled quotes decode once, and a bare quote pair writes one
  quote. Each statement produces one logical log record. The gated slice is
  printable ASCII up to 64 columns, without FILE, pointer controls, or
  double-quoted macro triggers. Python execution and a base-R
  witness are covered, not a live-SAS log capture ([examples/verify_put.py](examples/verify_put.py),
  [saschi.test_put](saschi/test_put.py), DS-023).
- Character-variable list PUT removes both leading and trailing blanks, then
  advances one blank after each value. Literals add no separator: with
  `c='  A  '`, `put '[' c ']';` records `[A ]`. DS-024 gates ordinary
  unformatted, nonblank ASCII character values and mixed literals, up to 64
  logical columns including the final separator. Blank values, numeric output,
  attached formats, special PUT controls, and literal-to-variable adjacency
  require review. Comment-only separation after a literal is conservatively
  refused; source whitespace is required. Programs using DS-024 also refuse
  double-quoted source macro triggers anywhere, including earlier DATA steps.
  These are logical-record contracts,
  not physical SAS log equivalence ([examples/verify_put_list.py](examples/verify_put_list.py),
  [saschi.test_put_list](saschi/test_put_list.py)).
- The earlier DS-027 numeric-variable list PUT profile uses preceding numeric
  declarations or statically numeric assignments to enable simple lists such as
  `n=7; m=.; put n m;`, with logical record `7 . `. Ordinary missing and finite
  integers with magnitude at most 99999999999 are gated. Each field retains
  one following separator, including the final field, within 64 columns.
  Fractions, special missing output, mixed numeric/literal/character lists,
  attached formats, and descriptor-only numeric SET variables require review in
  that earlier profile. DS-053 separately admits selected numeric SET variables
  through binary64-rows-v1; see [numeric row composition](docs/NUMERIC_ROWS.md).
  Descriptor checks also run on empty or filtered inputs. These are bounded
  repository and independent base-R records, without a live SAS log capture
  ([examples/verify_put_numeric.py](examples/verify_put_numeric.py), [saschi.test_put_numeric](saschi/test_put_numeric.py)). The composed
  counted-DO program also passes source/stdout/complete-result hash pins and an
  independent R program witness ([saschi.test_do_put](saschi/test_do_put.py)).
- COUNT preserves trailing blanks by default. I ignores case, T trims both
  arguments, and overlapping matches are undefined in SAS. The bounded ASCII
  Python/R slice rejects overlap, empty needles, zero-length input strings,
  non-ASCII/NUL text, implicit conversions, and modifiers outside I/T rather
  than inheriting Python's defaults ([examples/verify_count.py](examples/verify_count.py), DS-022).
- Ordinary equality can accept true as 1, and string conversion can accept text
  "1.0" as numeric 1.0. Typed comparisons reject both; row/schema order and metadata
  matter too ([saschi/test_compare.py](saschi/test_compare.py)).
- Explicit OUTPUT disables automatic output even when its branch is skipped.
  WHERE runs before BY groups form; subsetting IF runs afterward. Input/retained
  variables survive iterations while scratch variables reset ([verify_events.py](examples/verify_events.py)).
- Character byte widths affect assignments. Losing leading zeros, missing tags,
  labels, or format descriptors changes the typed result ([verify_metadata.py](examples/verify_metadata.py)).
- LAG and DIF are queues, never column shifts. Each occurrence carries its own
  queue of depth n, and the queue advances where the CALL RUNS rather than
  where the row exists, so a conditional call returns the value at the previous
  EXECUTION. On values 10, 20, 30, 40 invoked only on rows two and four, SAS
  returns missing then 20 where the shift model returns 10 and 30. A missing
  argument is still an execution, which makes a skipped call and a call with a
  missing argument different histories ([verify_lag.py](examples/verify_lag.py)).

- SAS `round(x, unit)` rounds half away from zero; Python and R round half
  to even by default. A naive translation disagrees with SAS at every
  half-unit boundary.
- R `ifelse` evaluates both branches whole-vector; the SAS ladder short
  circuits. Naive translations diverge on out-of-range branches.
- SAS missing values sort first and compare low; NaN and NA do neither
  consistently.
- Significant digits are a rounding problem, not a format problem: SAS has
  no %g, so sig figs mean ROUND to an explicit power-of-ten unit (half away
  from zero). R signif() and Python %g round half to even, so 0.125 at two
  digits is 0.13 in SAS and 0.12 in both open languages.
- PROC IMPORT guesses CSV types from a 20-row window; pandas and R infer
  from the whole file. A column that looks numeric early but carries a
  string at row 500 reads NUMERIC in SAS (string becomes missing) and
  character in pandas/R. Pin the divergence per file; never trust either
  default. Leading-zero identifiers strip in all three engines: read them
  as character explicitly.
- PROC FREQ percents are three separate denominators (cell, row, column),
  one decimal, missing levels excluded. R factors materialize zero-count
  levels as NaN rows that SAS never lists; pandas 3 omits them. And
  crosstab margins combined with normalize sums normalized values, never
  SAS totals. Compute margins from counts.
- Laplace noise is a distribution problem, not a generator problem. SAS
  PDF('LAPLACE', x) with the default location 0 and scale 1 is a density
  value, a constant; the 2018 origin guide's workaround added that
  constant as its noise. Draw streams are incomparable across engines, so
  the gate proves the deterministic surface (PDF, CDF, QUANTILE, and the
  inverse-CDF sampling construction) and never compares draws.
- Matrix operators lie across languages. IML's `*` is matrix
  multiplication and `#` is elementwise; R and numpy read `*` as
  elementwise (`%*%` / `@` are the products). IML fills matrices
  row-wise; base R fills column-wise. A singular inverse fails
  differently in each engine. The matrix gate pins the 2018 worked
  examples (product `[[50,21],[24,10],[101,42]]`, inverse
  `[[3,-2],[-7,5]]`) and never emits a bare star for a SAS product.

## Bounded source execution

DS-026 preserves the original single-level literal profile: `do i=1 to 5 by 2;`
with signed integer literal controls, each magnitude at most 2**31-1, nonzero
step, and at most 10000 iterations. These are implementation bounds. Direct
assignments, existing PUT, OUTPUT and DS-031 bounded conditional actions may
occur in the body; schema and OUTPUT
suppression still apply at zero trips. The final index passes the stop, and
`_N_` counts DATA iterations. DS-041 separately adds nested/computed counted
loops under the [A2 profile](docs/COUNTED_LOOPS.md). Conditional loops,
active-index writes, general declarations or input operations inside the body, MERGE,
DATA _NULL_ explicit OUTPUT, PUT _ALL_ combinations, and C++ are deferred.
[examples/verify_do_counted.py](examples/verify_do_counted.py) and [saschi.test_do_counted](saschi/test_do_counted.py) provide original
repository pins and an independent base-R witness, with no live SAS claim.


Bounded character LENGTH name groups and REVERSE are gated under DS-028.
REVERSE preserves fixed-width blanks and inherits its character argument width;
nonempty printable ASCII up to 32767 bytes is the supported slice. Numeric
coercion, zero-length source literals, Unicode and control characters remain
review cases. DS-030 composition evidence permits multi-name LENGTH and REVERSE
over stored SUBSTR values, with local checks on temporary consumers. The external reversal program passes source/stdout/complete-result
hash pins, shared-job execution and an independent base-R program witness
([examples/verify_length_reverse.py](examples/verify_length_reverse.py), [saschi.test_length_reverse](saschi/test_length_reverse.py)). Repository
and cross-language evidence, no live SAS verification.

DS-029 adds bounded printable-ASCII character `!!`/`||` concatenation and direct
CATX assignment. Operator widths sum, blanks remain intact, and existing target
widths retain assignment truncation. CATX trims item edge blanks, omits blank
items, preserves delimiters and defaults a new target to200 bytes. Its result
is bounded to200 bytes; destination overflow and temporary contexts are refused.
The original R gate and translator suite pin these implementation bounds and
an unmodified external whole-program hash proof ([examples/verify_concat_catx.py](examples/verify_concat_catx.py),
[saschi.test_concat_catx](saschi/test_concat_catx.py)). Repository/R evidence, no live SAS claim.


DS-030 composition gates replace the program-wide SUBSTR quarantine. Stored
SUBSTR variables compose with LENGTH groups, REVERSE, concatenation and CATX.
SUBSTR can also extract from fixed-width REVERSE/concatenation source expressions.
CATX accepts checked SUBSTR items under a padding-insensitive inference, tested
against raw and padded R models, with its existing 200-byte/capacity limits.
Width-sensitive temporaries such as REVERSE(SUBSTR), SUBSTR concatenation operands
and SUBSTR delimiters still require assigning the substring to a variable first.
No SUBSTR temporary width or SAS error-state behavior is claimed.
[examples/verify_substr_compositions.py](examples/verify_substr_compositions.py) and [saschi.test_substr_compositions](saschi/test_substr_compositions.py)
provide complete runtime/R agreement, local refusal and atomic failure checks.
Repository/base-R evidence for maintainer review, no live SAS claim.

DS-030 repairs three-argument SUBSTR assignment widths: a new destination gets
the first argument width; an earlier target keeps its own width. Checked execution
accepts nonempty printable ASCII literals or known character variables, with
positive integral numeric bounds inside the source. Invalid bounds, coercion,
error-state behavior and unproven temporary consumers are refused. Static checks
also cover empty input and skipped bodies. LENGTH/LENGTHN, direct comparisons
and COUNT with a constant space-free needle are bounded padding-insensitive
consumer inferences tested with raw and padded R models; temporary widths remain
unclaimed. The original raw SUBSTR fixture remains extraction-only evidence.
[examples/verify_substr.py](examples/verify_substr.py) and [saschi.test_substr](saschi/test_substr.py) cover destination descriptors,
independent R cases, WHERE input widths, atomic refusals and local temporary-consumer checks.
Repository/base-R evidence for maintainer review, no live SAS claim.

DS-031 gates first-true IF THEN / ELSE IF / ELSE dispatch, at most32 conditions,
with simple assignment,
existing PUT and OUTPUT leaves, including bounded counted-DO bodies. Both branches
participate in static schema discovery, source guards and explicit OUTPUT
suppression; only the selected branch executes. Unreachable index writes,
subsetting IF, conditional/grouped DO, input/declarations and PUT_ALL in counted bodies
and conditional ROUND remain refused. [examples/verify_do_if.py](examples/verify_do_if.py) and [saschi.test_do_if](saschi/test_do_if.py) provide original
base-R branch evidence and an unmodified external FizzBuzz source/stdout/complete-
result hash proof. Repository/base-R evidence for maintainer review, no live SAS.

DS-032 gates unsigned32 BAND, BOR, BXOR, BNOT, BLSHIFT and BRSHIFT with finite
integral operands0..4294967295 and shift counts0..31. Invalid/missing/coercion
cases are refused atomically, including static checks on skipped or empty input.
The independent R gate uses32-element bit vectors. The existing64-column PUT_ALL
profile remains intact: the unmodified bitwise corpus reaches its67-column output
refusal after its scalar PDV agrees with independent R. That refusal is evidence
of the current boundary, not a successful whole-program execution proof.
[examples/verify_bitwise.py](examples/verify_bitwise.py) and [saschi.test_bitwise](saschi/test_bitwise.py) provide repository/base-R
evidence for maintainer review, without live SAS or C++ bitwise claims.

DS-007 source execution now supports canonical LAG/DIF and depths1..100 as numeric
direct assignment RHS calls, including selected IF/ELSE and counted-DO leaves.
Each structural source occurrence has its own queue, advancing only on invocation
and persisting across DATA rows/loop iterations. Ordinary missing advances it;
BY boundaries and OUTPUT do not reset or call it. State resets for each step/run.
Static type/context checks also cover skipped/empty input; invalid dynamic values
and DIF overflow fail atomically. Unproven argument expressions, temporary/WHERE
consumers, character/tagged values, PUT_ALL and C++ remain refused. The original
raw gate is unchanged; [examples/verify_lag_execution.py](examples/verify_lag_execution.py) and
[saschi.test_lag_execution](saschi/test_lag_execution.py) add independent base-R prior-invocation evidence for
maintainer review, no live SAS claim.

## Origins

This project is the open-source realization of a concept that predates it
by eight years: the Rosetta Wiki, an internal wiki of side-by-side
SAS, R, and Python examples built to move statisticians off SAS. The
concept and its worked-example pattern are documented in:

> [Rosetta Wiki 1.0 User Guide: Companion to Rosetta Wiki](https://www.census.gov/library/working-papers/2018/adrm/rosetta-wiki.html). Nelson Chung,
> Steve Clark, Philip Leclerc, Aref Dajani, Phyllis Singer. Research
> Report Series (Disclosure Avoidance #2018-02), Center for Disclosure
> Avoidance Research, U.S. Census Bureau. September 2018.

The lineage is conceptual only. Nothing in this repository is copied from
that work; every implementation here is original, and the difference is
the doctrine: the 2018 wiki compared examples against hand-pinned
desired results by eye, while this repository demands executable
gates with explicit comparison policies and receipts. One continuity check: the 2018 Fisher
worked example pinned a two-sided p-value of 0.1238 on its 2x2 fixture,
and every engine pinned in this repository reproduces it exactly.

A task-level coverage map of that census, cross-referenced to the rules
and gates here, lives at
[`docs/rosetta_wiki_coverage.md`](docs/rosetta_wiki_coverage.md).

## Provenance

The verification method: published SAS outputs and documented behavior
first, cross-language agreement second, and capture against a live
licensed SAS runtime as the last mile where available.
Nothing in this repository is a verified claim until it has passed the
fixture gate; the receipts are the current evidence.

## Governance

This repository is governed under the
[Inertia-Drift-Framework](https://github.com/buntas-tofu/Inertia-Drift-Framework)
(DMF 2.0), file-based governance for projects worked on by humans and agents
together. The contract is [`AGENTS.md`](AGENTS.md); the machine-readable
descriptor is [`agent-manifest.json`](agent-manifest.json), validated against
[`agent-manifest.schema.json`](agent-manifest.schema.json) in CI; and the
invariants are checked by
[`scripts/inertia-drift-lint`](scripts/inertia-drift-lint) on every push:
fences, pointers, manifest shape, status lines, and the style floor of no em
dashes and no ellipses in artifacts.

## License

MIT. See [LICENSE](LICENSE).

## Bounded grouped control

The [grouped-control contract](docs/GROUPED_CONTROL.md) adds a separate integer
DATA profile for simple DO/END groups and nearest-loop LEAVE/CONTINUE. It keeps
counted indices, WHILE/UNTIL test timing, static OUTPUT discovery and atomic
failure explicit. Earlier profile contracts remain intact. Independent base-R
state/event schedules, exact original-program pins and real CLI comparison
controls provide evidence for the stated slice. INPUT/CSV, arrays, rounded
profiles and broader control language remain separate compositions.
