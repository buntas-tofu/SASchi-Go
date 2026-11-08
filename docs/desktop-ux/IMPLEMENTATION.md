# Desktop UX implementation

Status: implementation authorized by the principal on 2026-11-08 after review
of the nine desktop UX prototypes. This records product direction and current
implementation scope, not human usability evidence or native SAS equivalence.
Maintainers may use it to implement and review the desktop app. The implemented
workflow and current limits are described in [the desktop guide](../DESKTOP.md).

## Approved scope

Implement the reviewed layout and workflow in the native desktop application:

- Comfortable text and code sizes, resizable panels and narrow-window layouts.
- Open a SAS program and connect .sas7bdat datasets without preparing JSON.
- Optional comparison labeled Compare with SAS results.
- Review conversion options and actionable issues before execution.
- Show Python, R and SQL as primary targets and C++ as an advanced option, with
  readiness based on actual engine support. Parquet is a data layer and DuckDB
  is a local query layer, not another target language.
- Separate execution completion from agreement with supplied SAS results.
- Review source and converted code, tabular results, matched values, differences
  and unchecked evidence without interpreting missing checks as success.
- Preserve setup and prior evidence through failures and comparison retries.
- Save, reopen and export runs while retaining comparison rules, differences,
  omissions and unchecked items. Reconnecting changed files creates a new run.
- Compare saved runs and disclose changed programs, input identities and SAS
  result versions. A value that now matches does not by itself resolve cause.

## Implementation decisions

The native Tk shell remains the desktop entry point. File import, run storage
and evidence presentation are separate from the existing bounded compiler and
runtime. Existing engine refusal gates remain intact. Unsupported R and SQL
emission must remain unavailable until their implementation has verification.
The current C++ scalar emitter stays an explicitly advanced capability.

The importer may use the already allowed pandas dependency; Parquet and local
query support may use DuckDB. Missing dependencies or unsupported source data
must have actionable errors and must not silently coerce SAS values. Original
files remain read only. Private archive content is excluded from repository
artifacts and test fixtures.

Validation must cover importer fidelity, comparison scope, immutable saved
records, reconnection checks, export omissions and recovery, then run the full
repository verification suite before a push. Automated validation does not
constitute a completed human usability session.

## Implementation record

The native interface now separates file setup, conversion review, run evidence
and saved-run history. The implementation uses `desktop_service.py` for reviewed
snapshots, `data_files.py` for imports and Parquet, and `workspace.py` for saved
evidence and export. The existing bounded compiler and execution engine retain
their refusal behavior. The browser workbench is unchanged.

Desktop regression coverage includes lookup dependencies, exact decoded-byte
identities, file changes, execution failure, comparison-only retries, immutable
original verdicts, missing originals and export omissions. Native window smoke
coverage exercises the actual Tk event loop, file connection controls, two runs,
reconnection, comparison and export recovery, plus narrow large-text navigation.
The package CI runs that smoke and native SAS import tests against the installed
package and distribution pandas. Full-repository acceptance remains tied to the
source-bound `verify_all.py` receipt and the unchanged ALL VERIFIED bar.

Parquet is an optional export choice when DuckDB is installed. Complete typed
results and the comparison report remain exportable without that dependency.
This is an explicit implementation choice for the architecture-independent Debian
package. A general DuckDB query workspace and general R/SQL emission remain
future engine and interface work, visibly unavailable in this implementation.
