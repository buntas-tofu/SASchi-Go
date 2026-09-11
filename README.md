# SASchi-Go

Reproducing SAS behavior in open languages (Python, R) with receipts.

The AE85 to SASchi-Roku's AE86: the quiet workhorse underneath the legend.
This repository holds the migration toolchain: reference implementations of
SAS semantics, gold-pair fixtures that prove cross-language agreement, and
the rulebook for translating SAS constructs. The corpus it is tested against
lives in the sibling repository, [SASchi-Roku](https://github.com/buntas-tofu/SASchi-Roku).

The core claim: a translated program is accepted because it ran and its
numbers matched, not because it looked right. Every fixture gate in this
repository demands byte-equal output between the Python and R translations,
checked against hand-pinned truth and the semantics reference.

## Layout

- `sas_semantics.py` : reference implementations of SAS-quirk functions
  (round half away from zero, INTCK/INTNX, missing-value ordering, character
  truncation, merge mechanics, formats, and the family). The verifier's law.
- `examples/` : gold pairs. Each SAS construct gets a faithful Python and R
  sibling plus a fixture verifier (`verify_*.py`). Run any verifier directly,
  or all of them through `verify_all.py`.
- `docs/sasconversionrulebook.yaml` : the machine-consumable translation
  rulebook. 56 rules with equivalence classes (EXACT,
  EQUIVALENT-WITH-SETTINGS, APPROXIMATE, NO-DIRECT-EQUIVALENT), required
  settings, forbidden patterns, and validation tests.
- `docs/USER_GUIDE.md` : the user guide: running the gates, reading the
  receipts, understanding the equivalence classes, and verifying a new
  construct family.
- `saschi/` : the program-level translator package (Track A). `rules.py`
  loads the rulebook and routes constructs; tests in `saschi/test_rules.py`
  run against the shipped YAML.
- `kb01/sas_semantics_reference.txt` : the semantics reference as plain
  text, for humans and for diffs.
- `manifest.py` : pin a SAS corpus with content hashes and provenance.
- `synth.py` : program-level synthesis across characterized construct
  families, seeded and deterministic. Runs cross-language and reference
  gates; the live-SAS capture stage is optional and license-gated.
- `verify_all.py` : runs every fixture gate, emits a signed receipt JSON.
  One command, the whole proof.
- `tools/macro_census.py` : token census of the macro surface across the
  licensed public testbed, deterministic, pure stdlib. Outputs the
  frequency table in `docs/macro_surface_census.md` plus a CSV.
- `docs/macro_surface_census.md` : the macro-surface frequency table with
  method and NOTICE (which public repos were counted, under which
  licenses). Data about code, never code itself.
- `AGENTS.md` : the agent contract under the Inertia-Drift-Framework, the
  buntas-tofu principal GLOBAL plus this project's LOCAL layer.
- `agent-manifest.json` : machine-readable project descriptor, validated
  against the bundled schema in CI.
- `scripts/inertia-drift-lint` : the DMF invariant linter (fences, pointers,
  manifest shape, status lines, style floor). Runs in CI on every push.

## Running the gates

Requires Python 3.11+ and R (for the R halves of the gold pairs).

```sh
python verify_all.py
```

Each verifier also runs standalone, e.g. `python examples/verify_merge.py`.
The R interpreter is found via `ROSETTA_RSCRIPT`, then `Rscript` on PATH.
`verify_all.py` writes its receipts under `telemetry/` (gitignored).

## Known landmines (why the gate exists)

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

## Origins

This project is the open-source realization of a concept that predates it
by eight years: the Rosetta Wiki, an internal wiki of side-by-side
SAS, R, and Python examples built to move statisticians off SAS. The
concept and its worked-example pattern are documented in:

> Rosetta Wiki 1.0 User Guide: Companion to Rosetta Wiki. Nelson Chung,
> Steve Clark, Philip Leclerc, Aref Dajani, Phyllis Singer. Research
> Report Series (Disclosure Avoidance #2018-02), Center for Disclosure
> Avoidance Research, U.S. Census Bureau. September 2018.

The lineage is conceptual only. Nothing in this repository is copied from
that work; every implementation here is original, and the difference is
the doctrine: the 2018 wiki compared examples against hand-pinned
desired results by eye, while this repository demands executable
byte-equal gates with receipts. One continuity check: the 2018 Fisher
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
