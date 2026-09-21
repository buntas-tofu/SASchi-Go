"""saschi: the SASchi program-level translator package.

Track A of the SASchi frontier: an interface that takes a SAS program and
emits a translated target plus a completeness report, driven by the rulebook
(docs/sasconversionrulebook.yaml). The pipeline loads the program, splits it,
recognizes functions, routes every statement to a rule, emits, and records
the pass into a DuckDB catalog so completeness is a query.

v1 scope: data-step translation only, and only Python emits today (the R
target is declared in the rulebook, not yet emitted). Constructs without a
direct equivalent and every not-yet-gated family (stat procs, survey, macro)
emit a human-review ticket rather than code.
"""

__version__ = "0.2.0"
