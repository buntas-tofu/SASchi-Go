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
  rulebook. 50 rules with equivalence classes (EXACT,
  EQUIVALENT-WITH-SETTINGS, APPROXIMATE, NO-DIRECT-EQUIVALENT), required
  settings, forbidden patterns, and validation tests.
- `docs/rosetta_brief.md` : the project brief: the method, the oracle
  layers, and the verification doctrine.
- `kb01/sas_semantics_reference.txt` : the semantics reference as plain
  text, for humans and for diffs.
- `manifest.py` : pin a SAS corpus with content hashes and provenance.
- `synth.py` : program-level synthesis across characterized construct
  families, seeded and deterministic. Runs cross-language and reference
  gates; the live-SAS capture stage is optional and license-gated.
- `verify_all.py` : runs every fixture gate, emits a signed receipt JSON.
  One command, the whole proof.

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

## Provenance

The verification method is documented in the brief: published SAS outputs
and documented behavior first, cross-language agreement second, and capture
against a live licensed SAS runtime as the last mile where available.
Nothing in this repository is a verified claim until it has passed the
fixture gate; the receipts are the current evidence.

## License

MIT. See [LICENSE](LICENSE).
