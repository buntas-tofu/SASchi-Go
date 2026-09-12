# Macro surface census: licensed public SAS testbed

Status: measurement of a private clone set, not a claim about
upstream, not a license opinion. Counts macro feature tokens
in 1,755 .sas files across 22 public repositories. The estate
bench under testbed/local/ was compared privately and is not
reported here. Corrections land as new commits.

## Method

- Source: a checkout of the licensed public testbed, cloned 2026-09-08
  (snapshot; upstream may have moved since).
- Token census, not parsing: comments stripped (block, macro,
  single-line star), then feature regexes counted per file.
- Counts are data about code; no source lines are reproduced.
- per_1000_lines uses code lines after comment stripping.
- The broad %DO row includes the %DO %WHILE and %DO %UNTIL
  rows; the variant rows are shown separately below it.
- Features with zero occurrences across the whole testbed are
  omitted (WAITFOR: zero).
- Feature-to-rule mapping follows the rulebook: MC-001 %LET,
  MC-002 %MACRO, MC-003 %DO variants, MC-004 CALL EXECUTE and
  %SYSFUNC (dynamic code), MC-005 %INCLUDE, MC-006 SYSTASK and
  X commands, MC-007 ODS, MC-008 SYSERR/SYSCC, MC-009 PROC
  DATASETS. INFO rows (macro conditionals, &var references)
  inform Track A routing and are not rule families.

## Scope

| Repo | .sas files | License in clone |
|------|-----------:|------------------|
| friendly_SAS-macros | 463 | no license file in clone |
| sasjs_core | 408 | LICENSE |
| phuse-org_phuse-scripts | 164 | LICENSE, LICENSE.md, LICENSE.txt |
| sascommunities_sas-global-forum-2019 | 152 | LICENSE |
| sascommunities_sas-prog-for-r-users | 83 | LICENSE |
| Boemska_macrocore | 76 | LICENSE |
| HHS-AHRQ_MEPS | 58 | no license file in clone |
| sassoftware_sas-code-examples | 51 | LICENSE |
| sasutils_macros | 49 | LICENSE |
| yabwon_SAS_PACKAGES | 48 | LICENSE, license.sas |
| sassoftware_sas-iml-packages | 42 | LICENSE |
| atorus-research_atorus-sas-macros | 31 | LICENSE |
| cdisc-org_COSMoS | 31 | LICENSE |
| sassoftware_enlighten-apply | 23 | LICENSE, LICENSE.txt |
| wyp1125_SAS-Clinical-Trials-Toolkit | 22 | LICENSE |
| RhoInc_sas-statistical-data-checks | 14 | LICENSE |
| CausalInference_GFORMULA-SAS | 11 | LICENSE |
| PaulSchmidtGit_Heritability | 11 | no license file in clone |
| sascommunities_sas-cert-prep-data | 8 | LICENSE |
| danielegiardiello_Prediction_performance_survival | 6 | LICENSE |
| sascommunities_learning-sas-by-example-2nd | 3 | LICENSE |
| eleanormurray_CausalSurvivalAnalysisWorkshop | 1 | no license file in clone |

## Aggregate frequency (all repos)

| Rule | Feature | Occurrences | Files using | per 1k code lines |
|------|---------|------------:|------------:|------------------:|
| INFO | macro variable refs (&var) | 101267 | 1420 | 219.4 |
| INFO | %IF/%THEN macro conditionals | 16804 | 982 | 36.4 |
| MC-001 | %LET statements | 16418 | 1125 | 35.6 |
| MC-003 | %DO loops (all variants) | 15505 | 954 | 33.6 |
| MC-004 | %SYSFUNC calls | 4462 | 579 | 9.7 |
| MC-002 | %MACRO definitions | 2576 | 1170 | 5.6 |
| MC-007 | ODS statements | 1180 | 237 | 2.6 |
| MC-008 | SYSCC references | 639 | 117 | 1.4 |
| MC-004 | CALL EXECUTE | 558 | 68 | 1.2 |
| MC-008 | SYSERR references | 497 | 71 | 1.1 |
| MC-009 | PROC DATASETS statements | 470 | 237 | 1.0 |
| MC-005 | %INCLUDE statements | 383 | 148 | 0.8 |
| MC-003 | %DO %WHILE loops | 284 | 145 | 0.6 |
| MC-003 | %DO %UNTIL loops | 31 | 22 | 0.1 |
| MC-006 | SYSTASK statements | 14 | 2 | 0.0 |
| MC-006 | X command lines | 4 | 1 | 0.0 |

## Files touching the macro layer

- friendly_SAS-macros: 462 of 463 files (100 percent)
- sasjs_core: 368 of 408 files (90 percent)
- phuse-org_phuse-scripts: 148 of 164 files (90 percent)
- sascommunities_sas-global-forum-2019: 87 of 152 files (57 percent)
- Boemska_macrocore: 76 of 76 files (100 percent)
- sasutils_macros: 49 of 49 files (100 percent)
- yabwon_SAS_PACKAGES: 35 of 48 files (73 percent)
- HHS-AHRQ_MEPS: 32 of 58 files (55 percent)
- atorus-research_atorus-sas-macros: 31 of 31 files (100 percent)
- cdisc-org_COSMoS: 31 of 31 files (100 percent)
- sascommunities_sas-prog-for-r-users: 27 of 83 files (33 percent)
- sassoftware_sas-iml-packages: 23 of 42 files (55 percent)
- sassoftware_enlighten-apply: 22 of 23 files (96 percent)
- wyp1125_SAS-Clinical-Trials-Toolkit: 21 of 22 files (95 percent)
- RhoInc_sas-statistical-data-checks: 14 of 14 files (100 percent)
- sassoftware_sas-code-examples: 12 of 51 files (24 percent)
- CausalInference_GFORMULA-SAS: 11 of 11 files (100 percent)
- PaulSchmidtGit_Heritability: 11 of 11 files (100 percent)
- danielegiardiello_Prediction_performance_survival: 6 of 6 files (100 percent)
- sascommunities_sas-cert-prep-data: 6 of 8 files (75 percent)
- sascommunities_learning-sas-by-example-2nd: 2 of 3 files (67 percent)
- eleanormurray_CausalSurvivalAnalysisWorkshop: 1 of 1 files (100 percent)

## NOTICE

Counts are derived from public repositories cloned for
testing; each repo's own LICENSE file governs its content,
and this table cites only token frequencies, not code.
Four clones carry no license file at any depth and their
upstream license must be verified before any reuse beyond
token counting: eleanormurray_CausalSurvivalAnalysisWorkshop,
friendly_SAS-macros, HHS-AHRQ_MEPS, PaulSchmidtGit_Heritability.
The estate bench is private and stays out of this report.
