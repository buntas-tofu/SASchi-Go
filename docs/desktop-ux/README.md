# Desktop UX design proposals

Status: design proposals for the principal's review and backup. These screens
are not shipped desktop features, implementation commitments, usability results,
or native SAS validation. All file selections, datasets, run outcomes and
comparison evidence are synthetic. The principal may use them to direct further
design and implementation.

## Confirmed direction

The intended audience is an experienced SAS analyst who is new to SASchi-Go.
The requested experience uses clean, legible typography, comfortable text sizes
and layouts that adapt to smaller windows. Analysts should be able to open SAS
code, connect SAS data, review conversion targets, and inspect code and results
differences with understandable evidence.

Direct `.sas7bdat` input belongs in the first analyst-facing version. Analysts
should not have to prepare JSON files to use it. This is a product requirement,
not a claim that the importer or the illustrated workflow is implemented.

The confirmed main targets are Python, R and SQL; C++ belongs in advanced
options. Parquet is the planned shared data format, with DuckDB as the local
query layer. The optional comparison action is named **Compare with SAS
results**. These choices define the intended release direction, not completed
integration or target coverage for an arbitrary program.

## Agent proposals

The screens propose the detailed wording, layout, controls, progressive setup,
input connections, recovery states and evidence presentation. Per-program target
readiness, import and data-layer integration, persistent setup, comparison-only
retry, detailed difference views and export mechanics remain implementation
work wherever the mockups identify it. A successful simulation does not establish
engine support or agreement with an actual SAS run.

## Screen inventory

| Screen | Review focus |
| --- | --- |
| [First open](mockups/saschi-first-open.html) | Open a program, connect inputs, and optionally supply SAS results before reviewing conversion options. |
| [Main screen](mockups/saschi-main-screen.html) | Comfortable text, adaptable panels, source and converted code, output data and one illustrative difference. |
| [Conversion options](mockups/saschi-conversion-options.html) | Target readiness, unresolved requirements, input connections and the distinction between analysis and execution. |
| [Post-run review](mockups/saschi-post-run.html) | Execution status, comparison scope, output inspection and evidence states. |
| [Recovery](mockups/saschi-recovery.html) | Preserve setup, explain a stopped run or unavailable comparison file, and review a separate retry. |
| [Review a difference](mockups/saschi-review-difference.html) | Inspect a differing value, its calculation, comparison rules and supplied evidence. |
| [Save and export](mockups/saschi-save-export.html) | Review destinations, export contents and evidence status before saving a separate copy. |

These seven screens are separate prototypes, not one connected application.

## Viewing and preservation

The files in `mockups/` are the exact HTML fragments reviewed in the design
conversation. Open an individual file in a modern browser to inspect its local
sample interactions. Optional host-provided icons, tuning controls and widget
state persistence may be absent outside the original preview host. The fragments
do not import datasets, execute SAS or translated programs, or save real jobs.

The main screen uses an early `adjust_sales` example. Later screens use the
`net_sales` example. These are independent synthetic scenarios, not successive
receipts from a real conversion. Private archive content, private dataset values and
conversation transcripts are not part of this backup.

Keep these source fragments intact when adding a viewing wrapper. Implementation
and human usability checks should be recorded separately from design review.
