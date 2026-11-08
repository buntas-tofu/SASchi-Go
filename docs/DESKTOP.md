# Ubuntu desktop

Status: implemented desktop workflow for maintainer and analyst review. Automated
checks exercise imports, execution, saved evidence and native window behavior.
No live SAS equivalence or completed human usability claim is made.

## Start the application

Install the locally built package with Ubuntu's package manager:

```sh
sudo apt install ./saschi-desktop_0.4.0+desktop2_all.deb
```

Launch SASchi-Go from Applications, or run `saschi-desktop`. The package uses
Ubuntu's Python, Tk and pandas. DuckDB is optional and is not bundled by this
architecture-independent Debian package. The export dialog states whether
Parquet is available in the running environment.

For a source checkout with the complete desktop dependencies:

```sh
sudo apt install python3-tk python3-venv
python3 -m venv --system-site-packages .venv-desktop
.venv-desktop/bin/python -m pip install -e '.[desktop]'
.venv-desktop/bin/python -m saschi.desktop
```

The application starts no HTTP listener or assistant service. Original selected
files stay read only. The default workspace is `~/Documents/SASchi-Go`; choose a
different folder in the header. Long-running file and execution work stays off
the Tk event loop. Wait for the current operation before closing.

## Files, review and execution

Open a `.sas` program, connect input datasets and assign the member names used
by the program. Direct `.sas7bdat` import requires no analyst JSON preparation.
Single-member `.xpt`, CSV and typed JSON catalogs are also accepted. Library
statements, includes, macros and unsupported constructs still produce review
items; connecting a file does not expand the compiler's supported language.

Use **Compare with SAS results** to add output datasets from SAS. Their names
must correspond to converted outputs. Comparison is optional. Without supplied
SAS results, agreement remains not checked. A program that executes is not
therefore a verified conversion.

**Review conversion options** reads the selected files and analyzes the program
without executing it. It lists required and missing inputs, import limitations,
conversion tickets and generated code. Execution rechecks file identities and
uses the reviewed snapshots. Changed files require another review.

- Python can run supported programs through the existing SASchi-Go runtime.
- R and SQL remain visible as targets that need engine work. Their verification
  fixtures are not general program emitters.
- C++ is an advanced bounded scalar code preview and export. The desktop does
  not execute C++.
- Parquet is a data export layer. DuckDB supplies that layer locally. Neither is
  presented as another conversion target. A general DuckDB query editor is not
  part of this desktop implementation.

The interface offers 12, 14 and 16 point text, including code. Code panels have
drag handles and stack when the window narrows. Tables scroll horizontally and
page through observations without reducing text size.

## Import fidelity and limits

Native SAS import retains raw numeric dates, ordinary and tagged missing values,
character byte widths and padding, labels, format names and supported encodings.
Display widths, format decimals and custom format catalog definitions are not
imported. Metadata comparison covers imported fields only. Import caveats remain
attached to saved runs and comparison reports.

The typed runtime supports UTF-8, ASCII and Latin-1. Unsupported encodings,
non-eight-byte SAS numeric storage and incomplete or ambiguous file conditions
are refused. Choose an explicit encoding only when the file's encoding is known.
CSV has no SAS descriptors; its inferred types and widths are disclosed. Leading
zero identifiers remain character data. Imported SAS dates display as raw numbers.

The adapter uses pandas' SAS reader internals to retain missing tags and complete
character bytes before conversion to the typed runtime. Synthetic binary tests
cover byte order, header width, RLE compression and missing values. This is bounded
format coverage, not a claim that every SAS dataset encoding is supported.

## Review, save and reopen

Each execution receives a unique immutable run directory with a checksummed
record. Execution status is separate from SAS result agreement. Completed output
is retained when comparison differs. Failed execution records the error and
preserves the setup for a new review.

The run view presents output tables, saved source and converted code, comparisons,
reports, the execution log and the underlying record. Comparisons use exact typed
values, observation position, variable order and stored metadata. There is no
implicit tolerance or key-based row alignment. Paired value differences, unpaired
cells, shape differences and unchecked items are distinct.

Additional comparisons append evidence without rerunning or replacing the first
comparison. Reopen a saved run without its original files. **Check original files**
distinguishes unchanged, moved, changed and missing files. Reconnect originals for
optional export copies or a new setup. Using changed data requires an explicit
choice and another review; saved output remains unchanged.

Select two saved runs to compare program snapshots, file identities, available
original input values, runtime details and output values. Unavailable original
input versions remain not checked. A value that now matches the same SAS results
is not an explanation of its earlier difference or an analyst signoff.

## Export and validation

Export creates a new ZIP with converted code, produced results, a portable record
and an HTML comparison report. Complete typed JSON result files are always
included; analysts do not prepare these themselves. Parquet and CSV are separate
export choices. When DuckDB is unavailable, Parquet is visibly disabled and CSV
is selected as a convenience copy. Optional copies include source, original input
files and original SAS results. Original file copies are checked against their
saved content digests before inclusion. Export never overwrites an existing file.
Differences, unchecked evidence, import limitations and omitted copies travel with
the package. Compared values remain included even when original files are omitted.

Parquet exports require their metadata sidecars: tagged missing values are null in
Parquet, while exact tags and SAS descriptors live in the sidecar. CSV is a
convenience representation. Generated Python requires the recorded SASchi-Go
runtime and an input catalog supplied by its caller; it is not a standalone data
loading script. The runtime is not bundled in review ZIPs.

Build without downloading dependencies, using an interpreter with pip, setuptools
and wheel already installed:

```sh
python3 tools/build_desktop_deb.py --output output/saschi-desktop_0.4.0+desktop2_all.deb
python3 -m unittest saschi.test_desktop saschi.test_desktop_service saschi.test_data_files saschi.test_workspace
```

The normal `python verify_all.py` gate includes the desktop service, data importer
and workspace suites. Package smoke checks validate control metadata, installed
payload, native SAS import and window behavior under Xvfb, plus the headless entry
point error. Human review should still cover native
chooser ergonomics, real display scaling, keyboard navigation and representative
analyst programs and datasets before the first analyst-facing release.
