# The 2018 worked-example census: coverage map

The [README Origins section](../README.md) cites the 2018 report whose
concept this repository realizes. This page maps the worked-example
census in that report to the coverage each example has here today, so a
reader can trace any 2018 construct to its modern answer: a fixture gate
with receipts, a rulebook rule, a policy, or an explicit routing
decision. Rows follow the report's own appendix order and names.

Status vocabulary:

- **Gated**: a fixture family in `examples/` proves it under
  `verify_all.py`; the rulebook rule is named.
- **Rule**: a rulebook rule covers it; no dedicated fixture exists yet.
- **Policy**: a global policy in the rulebook covers it.
- **Human review**: routed to a reviewer, never auto-translated.
- **Doctrine**: covered by a stated verification rule rather than a
  fixture.

| 2018 worked example | Modern home | Status |
|---|---|---|
| B.1 to B.3 session mechanics and editor onboarding | none | Out of scope (tools, not constructs) |
| C.1 Set the working directory | DS-018 | Rule |
| C.2 Install and load an add-on package | GP-04 | Policy |
| C.3 Concatenate matrices (create, join horizontally, join vertically) | MX-001; matrix family | Gated |
| C.4 Matrix math (transpose, multiply, invert) | MX-001; matrix family | Gated |
| C.5 Merge datasets | DS-002, DS-003; merge family | Gated |
| C.6 Convert numeric to character | DS-015 | Rule |
| C.7 Concatenate character strings with a comma | DS-015 | Rule |
| C.8 Concatenate numbers with a space | DS-015 | Rule |
| C.9 Round numbers | DS-012; rounding_n family | Gated |
| C.10 Format numbers to four significant digits | DS-020; sigfig family | Gated |
| C.11 Create a function | funcs family | Gated (scalar function surface) |
| C.12 Impute missing values | DS-005; missarith family | Gated |
| D.1 to D.4 Frequencies and proportional frequencies (total, row, column) | ST-015; freq family | Gated |
| E.1 Fisher exact test | ST-014; fisher family | Gated |
| E.2 Add Laplace noise | ST-016; laplace family | Gated |
| E.3 Add Gaussian noise | rulebook meta (stochastic tolerance tier) | Doctrine (validate distributions, never draws) |

Notes:

- The matrix surface (concatenation, transpose, multiplication, and the
  2x2 inverse) is pinned and gated in MX-001; the rest of PROC IML
  (general inversions, subscripting, missing handling) still routes to
  human review under GP-09.
- Every Gated row names a family that runs under `verify_all.py`; the
  newest receipt under `telemetry/verify/` is the evidence, cited by
  timestamp.
- Where the 2018 material pinned a comparable expected result, this
  repository's gates reproduce it: the Fisher worked example's two-sided
  p-value of 0.1238 is pinned byte-for-byte in the fisher gate.
- The Laplace worked example predates random-draw support for the
  Laplace distribution; its material recorded a density value used as
  noise, which is a constant. The laplace gate pins that lesson as a
  landmine and never compares draws.
