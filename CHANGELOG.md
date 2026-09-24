# Changes for 0.3.0

Status: development changes with original pins and Python/base-R evidence; no
live SAS comparison. Branch synchronization is separate from a release.

- Require typed expected comparisons, ordered rows/columns, and preserved metadata;
  make synthesis numeric tolerance explicit per family.
- Add version 2 DATA events: OUTPUT snapshots, WHERE/IF timing, BY flags, numeric
  retention, and a bounded first-iteration lookup SET.
- Preserve character widths, encodings, labels, format descriptors, and special
  missing identity. Reject unsupported conversions and ambiguous state cases.
- Keep version 1 plans readable and make C++ reject new unsupported operations.
- Add original event and metadata witnesses, base-R twins, and an operator example;
  append the gates after all original fixture gates.
- Add the LAG/DIF invocation-queue gate: reference functions, a base-R twin, and
  original witnesses for queue depth, independent occurrence queues, conditional
  execution, and the missing-argument push. Extends DS-007 from a pattern test to
  a byte-equal Python/R gate.
- Ship the rulebook as JSON: `docs/sasconversionrulebook.json` replaces the YAML
  source and the loader becomes standard library only. The file banner and the
  runtime-capabilities note move into the document as data; the six section
  banners retire because the loader derives rule families from rule_id prefixes.
  The tool now declares no required third-party dependency.
- Add the gate-backed function slice: `saschi/functions.py` holds a registry of ten scalar
  functions (MAX, MIN, LENGTH, LENGTHN, LENGTHC, SUBSTR, SUM, ROUND, PUT with a numeric w.d or
  DATE9 format, and INPUT with a character read or the YYMMDD8 informat) in which every entry
  names the fixture gate that proves it. Call arguments nest and accept arithmetic operands,
  the parser refuses any function or format token that has no gate so the statement stays a
  human-review ticket, and `suite-functions` pins both halves. Measured over the variance
  corpus: tickets 205,577 to 205,318 of 244,678 statements.

# Changes for 0.2.0

Status: development changes with repository verification; no live SAS claim.

- Repair lexical fences and contextual routing; retain unsupported text as tickets.
- Add versioned operation plans, numeric Python dataset execution, and a C++17
  scalar backend with cross-backend tests.
- Add the operator CLI, installable packaging, dependency snapshot, and a composed
  rounding/sort/merge example with pinned and base-R output.
- Record source hashes, full diagnostics, and runtime versions in checksummed
  receipts; fail synthesis on incomplete execution and preserve binary64 CSV values.
- Keep the original fixture gates and extend unified verification and CI.

# Changelog

All notable changes to SASchi-Go are recorded here. Versioning is semver per
`agent-manifest.json`, and the current version is `0.3.0`.

The repository carries no release tags yet, so a version named in this file
describes a state of `main` rather than a published artifact. This file was added
on 2026-09-14, and the entries below were reconstructed from the commit history of
`main`, which was the only record before it existed. Short hashes are given so
every line can be traced to its commit.

## 0.1.0 - 2026-09-14

### Added

- The semantics reference, the gold-pair fixture gates, and the translation
  rulebook, as the first public-ready tree (`10effea`).
- Fixture families, one construct each: Fisher's exact test `ST-014` (`f680690`),
  four-significant-figure rounding `DS-020` (`1b5f6f7`), the PROC IMPORT
  guessing window `DS-021` (`49dc089`), descriptive listing `ST-015`
  (`099eb84`), the matrix family `MX-001` (`52ea855`), and the Laplace family
  `ST-016` (`49e03d0`).
- The macro-surface frequency table across the licensed public testbed
  (`1d70bb8`).
- The translator, in steps: rulebook loader and construct map (`826d4d1`), the
  fence-robust statement splitter (`3953394`), statement text keeping token
  boundaries (`fff7d73`), and `emit_py` translating the rounding program
  (`c24b2b2`).
- `saschi/test_rulebook.py`, the executable counterpart of the rulebook patterns,
  each test also asserting the pattern text so a rewording back to a wrong
  contract fails there (`7cb958d`).
- `duckdb` in the gate set, because an SQL target can only be proven in an engine
  (`7cb958d`).
- The user guide for running the gates, reading receipts, and verifying families
  (`66ccaa0`).
- The 2018 worked-example census coverage map (`3001832`).

### Changed

- Adopted the Inertia-Drift-Framework: `AGENTS.md` contract, `agent-manifest.json`
  and its schema, the vendored drift linter, and both CI workflows (`43eae99`).
- Re-vendored `scripts/inertia-drift-lint` at 2.1.0, whose floor covers all text
  artifact formats (`c6d45c7`).
- `verify_all.py` now runs 21 fixture gates and 4 translator suites, so ALL
  VERIFIED covers the translator and not only the fixture surface (`d4858e0`).
- `LICENSE` carries the operator's legal name, and local filesystem references
  were replaced in the docs, the tool defaults, and the corpus test path
  (`7fdb238`).
- The LOCAL contract now names `duckdb` in the gate set and the gate that covers
  translation (`e4ac22a`, `d4858e0`).

### Fixed

- The rulebook's four wrong targets: `DS-006` filled inside the aggregation,
  `DS-007` prescribed a full-column shift for a conditional LAG, `DS-009` required
  last-value aggregation where LET is the contract, and `SQL-001` claimed
  CALCULATED aliases work unchanged in DuckDB (`7cb958d`).
- `DS-007` now routes a conditional LAG call to review as well as modelling it
  (`bb5b6c7`).
- A ticket blocks the artifact instead of commenting on it, so a program whose
  control flow was dropped no longer emits a file that looks like a successful
  translation (`f0e0a89`).
- The emitter refuses a statement it cannot fully account for rather than reducing
  it (`b8ba85e`).
- The outside review P1 pair: zero-and-retained weights, and QTR SAME
  month-anchored (`5121aef`).
- Em dashes stripped from the shipped rulebook to meet the style floor (`e33d53b`).
- Agency provenance stripped from the brief, and DSEP naming dropped from the
  significant-figure surface (`b478cd5`).

### Removed

- The Rosetta brief left the public tree (`5534ab9`).
