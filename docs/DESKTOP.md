# Ubuntu desktop

Status: desktop frontend for maintainer test drives. Uses the existing bounded
CLI job pipeline. No live SAS or completed human usability claim.

Install the locally built package with Ubuntu's package manager:

```sh
sudo apt install ./saschi-desktop_0.4.0+desktop1_all.deb
```

Launch SASchi-Go from Applications, or run `saschi-desktop`.
For a source checkout, install `python3-tk` and run
`.venv/bin/python -m saschi.desktop`.

Choose a SAS program, any supporting typed JSON input catalog, and an existing
output folder using the file and folder dialogs. Optional JSON expectations
cover datasets, reports, exports and ordered log records separately. Blank
expectations mean no comparison was requested. Inputs use the same schema as
`saschi run --inputs`; arbitrary CSV, SAS binary datasets, includes, macros and
external libraries are not automatically imported. Unsupported source produces
review tickets rather than a partial successful translation.

Run selected program creates a unique `saschi-<UTC time>-<id>` child directory.
The existing CLI publishes plan.json and receipt.json together, plus result.json
for accepted execution or observed.json when execution produced rejected output.
Accepted report and export files are saved in reports/ and exports/. Original
selected files are read only. Previous jobs are retained. The app displays a
bounded preview; complete artifacts remain on disk. Open saved job opens the
result folder in the file manager. Wait for the current job before closing.

ACCEPTED means execution and requested comparisons passed. It does not imply
a per-job independent R comparison or native SAS equivalence. Failed requested
comparisons remain distinct from not requested and not reached. The desktop
starts no HTTP listener or assistant service.

The Debian package contains the Python application and canonical rulebook.
Ubuntu supplies Python, Tk and xdg-utils. Runtime execution is standard library;
optional completeness accounting reports unavailable if DuckDB is absent.
R, C++ and scientific Python packages remain verification dependencies rather
than mandatory desktop runtime dependencies. The postal profile still needs its
explicitly prepared external pinned USPS reference. No reference data is bundled.

Build locally with the installed wheel/build tooling:

```sh
.venv/bin/python tools/build_desktop_deb.py --output output/saschi-desktop_0.4.0+desktop1_all.deb
.venv/bin/python -m unittest saschi.test_desktop
```

The package has no automatic updater, network service or privileged runtime.
Installing it is separate from building and reviewing it. Human testing should
cover native chooser cancellation, long paths, removable drives, comparison
errors, blocked source, saved artifacts, keyboard navigation and display scaling.
