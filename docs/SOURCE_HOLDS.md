# Pinned source-hold register

Status: retained source observations and unresolved admission questions for
principal/maintainer review, recorded 2026-11-03. Twelve observations are retained. H01 has a bounded repository policy; the
original numeric-picture target remains held at H12. These
are not live-SAS failure findings, source repairs or accepted parser/encoding
changes. Selecting a candidate order does not resolve a hold.

The exact repository, commit, paths, byte counts, SHA256/Git blob identities and
proposed resolution evidence live in [the staging register](format-candidate-staging.json).
It pins `sassoftware/sas-code-examples` commit
`579e057f90cd699f744fd6a1c8acaf9243f7ff67`. Only metadata and original assessment
notes are retained here; source and license bodies remain outside Go.

| Hold | Original path | Observed condition | Required next decision |
| --- | --- | --- | --- |
| H01 | `By Syntax/FORMAT Procedure/Using digit selectors in the PICTURE statement.sas` | UTF-8 BOM in the pinned bytes | Bounded repository envelope policy recorded below; H12 retains the original target hold |
| H02 | `By Syntax/FREQ Procedure/2_One-way frequency report statistics.sas` | Header closes at line 7 before explanatory prose | Resolve original-source boundary; retain any corrected revision as a distinct target |
| H03 | `By Syntax/FREQ Procedure/3_Create an output table with frequency statistics.sas` | Header closes at line 6 before explanatory prose | Resolve original-source boundary; retain any corrected revision as a distinct target |
| H04 | `By Syntax/FREQ Procedure/4_Control frequency report order.sas` | Header closes at line 8 before explanatory prose | Resolve original-source boundary; retain any corrected revision as a distinct target |
| H05 | `By Syntax/FREQ Procedure/5_Frequency plots.sas` | Header closes at line 7 before explanatory prose | Resolve original-source boundary; retain any corrected revision as a distinct target |
| H06 | `By Syntax/IMPORT Procedure/2_Specify Column Attributes with Generated DATA Step Code.sas` | Exactly zero source bytes | Keep visible; empty-source/no-op acceptance does not supply missing benchmark behavior |
| H07 | `By Syntax/Macro Language/1_Creating_Macro_Variables.sas` | UTF-8 BOM in the pinned bytes | Explicit bounded BOM admission and source accounting before target acceptance |
| H08 | `By Syntax/PRINT Procedure/3_Select rows to print and format displayed values.sas` | Go rejects an unterminated nested-looking header | Characterize native comment treatment and Go's accepted parser policy separately |
| H09 | `By Syntax/PRINT Procedure/4_Order rows in a report.sas` | Direction token is spelled `desending` at line 16 | Preserve the original and resolve source validity; a correction has a distinct identity |
| H10 | `By Topic/Utility Macros/Print first N rows from each table in a library.sas` | 1036 bytes, 567 NUL bytes, invalid UTF-8 | Identify actual asset format/provenance; do not guess an encoding or substitute another file |
| H11 | `By Syntax/FORMAT Procedure/Using Nested Formats.sas` | Original nests WEEKDATE50.; the SAS 9.4 HTML reference and current PDF specify widths 3 through 37 | Resolve native handling or an explicit new target identity; no silent width correction |
| H12 | `By Syntax/FORMAT Procedure/Using digit selectors in the PICTURE statement.sas` | Original delGy final template has selectors after message text without NOEDIT | Retain original hold pending native behavior evidence; valid first-party forms are separate |

H11 was discovered during stage 1 characterization and applies to FMT-01. H01
and H12 apply to FMT-04. The other nine remain retained for future work on the larger
source inventory. H11 does not establish that native SAS rejects, clamps or
successfully renders the requested width; that behavior is unresolved.
Absence of a source hold does not mean a candidate is implementation-ready: its
language contract, data policy and independent oracle may remain unresolved.

For H08, the current Go lexer counts nested block-comment depth. SAS 9.4 documents
block comments as non-nesting. That comparison motivates a characterization task;
it does not establish what this exact program did in a native runtime or justify
an unreviewed lexer change. [SAS 9.4 Global Statements: Comment Statement](https://documentation.sas.com/api/collections/pgmsascdc/9.4_3.5/docsets/lestmtsglobal/content/lestmtsglobal.pdf?locale=en).

Every resolution must retain the original observation, source identity, decision
and supporting evidence. A corrected or substituted source cannot inherit an
unchanged-original proof. Do not silently remove BOMs, comment out prose, repair
spelling, infer an unknown encoding or replace H10 with the differently pinned
PRINT-procedure macro of the same name.

H11 references: [WEEKDATE, SAS 9.4 HTML](https://support.sas.com/documentation/cdl/en/leforinforref/64790/HTML/default/p1rib2891qxd4yn18x1myfkmxeet.htm)
and [SAS 9.4 Formats and Informats, printed page 491](https://documentation.sas.com/api/docsets/leforinforref/9.4/content/leforinforref.pdf#page=505).

The complete larger screen accounted for 44 entries: 42 compiler attempts, all
blocked, one empty entry and one source-format deferral. This is a source-screen
observation, not execution or proof admission. The six-stage order is recorded
in [the candidate plan](FORMAT_CANDIDATE_PLAN.md).

H12, discovered during FMT-04 characterization: the original delGy final
picture has digit selectors after leading message characters without NOEDIT.
The primary PICTURE statement reference requires a digit selector first when
selectors are used. Native handling of this exact form remains unresolved.
Retain the unchanged3214-byte original; do not fabricate a complete expected
report or silently add NOEDIT. Valid09/99/NOEDIT work proceeds independently.
[PICTURE statement reference](https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a002473467.htm).

H01 repository-policy resolution: numeric-picture-fields-v1 admits exactly one
leading UTF8 BOM and an ASCII remainder, retains the raw byte digest, preserves
physical lines and records3prefix bytes separately from statements. Original
ASCII and BOM hand/base-R accounting and whole results agree through runtime,
generated Python and actual CLI. This resolves a scoped Go admission question,
not native SAS BOM behavior. H07 and all other families retain their prior rules.
H12 continues to prevent whole original FMT-04 admission.

Post-implementation compile-only rescreen of the same44-entry remainder:
42compiler attempts,4clean and38blocked, plus the same1empty entry and1encoding
deferral. The four clean targets are FMT-02,03,05,06 and have separate whole-source
gates. A clean compile alone is not proof. Original FMT-01/H11 and FMT-04/H12
remain blocked. The remaining40official entries include those holds and the
empty/encoding cases. No Roku denominator or native SAS result changes.
