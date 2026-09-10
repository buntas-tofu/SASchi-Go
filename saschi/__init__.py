"""saschi: the SASchi program-level translator package.

Track A of the SASchi frontier: a CLI that takes a SAS program and emits a
translated target (python or r) plus a signed verification report, driven
by the rulebook (docs/sasconversionrulebook.yaml).

v1 scope: data-step translation only. Constructs without a direct
equivalent and every not-yet-gated family (stat procs, survey, macro)
emit a human-review ticket rather than code.
"""

__version__ = "0.1.0"
