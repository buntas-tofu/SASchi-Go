# Next DATA step function wave

Status: principal-approved plan of2026-11-11, implemented locally through the six
profiles and two original composition programs on2026-11-12. Acceptance requires
the current full source-bound receipt and both workload suites.
See the [implementation evidence register](FUNCTION_WAVE_COMPOSITION.md).
The principal authorized the six groups in their recorded order and the final
composition programs. Expected usefulness remains an engineering inference;
acceptance requires each slice's independent oracle and passing verification.
Publication remains a separate action.

Principal selection recorded 2026-11-11: in response to the choice between broadly
useful DATA-step function families and remaining official example programs,
the principal selected "DATA-step function families (recommended)".

Principal implementation authorization recorded 2026-11-11: "signing off on that
plan. free to engage!" This authorizes environment restoration, the six ordered
groups, their required evidence and the two final composition programs.

Prioritize six reusable function groups, then prove them together in original
programs. The candidate list contains 25 distinct function names. Some already
have reference fixtures or restricted source support; the objective is useful
source execution and composition, not 25 claims of entirely new semantics.

## Starting evidence

The clean planning entry is commit `0ad76bb4a2d29a316bfff191e0458245c4e5042d`.
Its implementation source matches the successful local receipt from 2026-11-03
ET: source digest
`42d9c3a26fbd759967139114804cc8bcea362533bdc6305a385778f5b842b774`,
111 fixture gates, 73 suites, 1655 unit tests, zero skips and synthesis.
The receipt is retained under
`telemetry/night-shift-20261103/full-run-02/verify/receipt_20261104T034744_6243282d4ca2.json`.
These are historical passing outcomes for that source, not a fresh run in this
session or an acceptance of subsequent documentation changes.

A newer local attempt from 2026-11-08 failed and reported unstable source.
Sample failures include missing pandas and DuckDB and denied loopback access.
The current repository virtual environment also lacks required gate packages.
Keep that failed attempt distinct from the matching successful receipt, and
classify remaining failures after restoring the environment.

The [six FORMAT stages](FORMAT_CANDIDATE_PLAN.md) are implemented in bounded
forms. Four added unchanged official-example gates; originals H11 and H12 remain
held in the [source register](SOURCE_HOLDS.md). Eleven official programs are
registered from the pinned 51-entry inventory, leaving 40 entries outside that
registered set. The earlier review classified 31 entries as SASHELP-dependent.
Those are inventory and source-review counts, not new execution results.

The [capability manifest](capability-manifest.json) still enumerates statements
and data-set options. Its functions/CALL reference universe remains null.
Do not report a percentage of all SAS functions from the implementation registry.

## Entry work

Restore gate dependencies from [the existing lock](../requirements-verify.lock),
check Python, base R and the C++ compiler, verify the pinned sibling corpus and
explicitly prepare the external vendor and postal caches. Run the unchanged
golden command with the loopback access required by its interface tests. Require
a stable source and ALL VERIFIED before beginning implementation. Preserve failed
attempts and resolve actual failures without weakening gates.

Build a per-function admission matrix before freezing the first contract:
reference helper, registered gate, accepted source profile, portable form,
supported consumers and current refusals. Read both the general function registry
and specialized numeric, date, week and postal profiles. For example, UPCASE in
the postal family does not establish general DATA-step UPCASE; INTCK/INTNX
reference helpers do not establish general source-call support.

Keep this matrix separate from the capability manifest until a complete published
reference index has been enumerated under that manifest's rules. Resolve the
SAS 9.4 reference edition and behavior sources before freezing each contract.

## Approved implementation order

| Order | Function group and candidate names | Contract to freeze first | Original program finish line |
| --- | --- | --- | --- |
| 1 | Case and search: UPCASE, LOWCASE, INDEX, FIND | Printable ASCII, fixed byte widths, search positions, trailing blanks and an explicit FIND argument/modifier subset | Normalize and search supplied character rows, then compare selected output, descriptors and logical report text |
| 2 | Word parsing: SCAN, COUNTW | Explicit delimiter set first; positive and negative word positions; repeated delimiters, blank input, missing words and destination widths; modifiers admitted separately | Tokenize padded fields and reconcile word counts, extracted values and complete output rows |
| 3 | Character rewriting: COMPRESS, TRANSLATE, TRANWRD | Character deletion versus replacement, argument ordering, empty/blank replacements, new destination widths and truncation | Clean original label and identifier fields with exact stored bytes and declared logical output |
| 4 | Missing values and row summaries: MISSING, N, NMISS, CMISS, COALESCE, COALESCEC, MEAN | Numeric versus character missing, ordinary versus tagged values, coercion policy, all-missing rows, character result widths and numeric comparison policy | Complete row-cleaning and summary program with independent expectations for every cell and descriptor |
| 5 | Numeric helpers: ABS, SIGN, CEIL, FLOOR | Signed and missing inputs, bounded binary64 domains, near-integer fuzz behavior and explicit refusal boundaries | Reconciliation program that distinguishes SAS rounding behavior from naive host-language functions |
| 6 | Calendar components and intervals: YEAR, MONTH, DAY, INTCK, INTNX | SAS epoch-day storage, valid date domain, leap days, reverse intervals, discrete boundary counting and individually characterized alignments | Monthly cohort program that compares stored dates, interval results and separately declared formatted reports |

Inference: this sequence reuses existing fixed-width character, missing-value,
numeric and date foundations while keeping unrelated runtime contracts apart.
It is an approved order, not a schedule or a promise that every modifier and
consumer will fit one slice. Split a group when its oracle or profile composition
requires separate acceptance.

Character work begins with assignment and already characterized consumers.
WHERE, nested temporaries, formatted output and cross-profile use each need
explicit composition evidence. Do not broaden specialized profiles by inference.
For calendar work, start with explicit dates and bounded intervals; clock inputs,
datetime/timezone behavior and additional interval methods need separate contracts.

## Evidence required for each slice

1. Freeze the bounded contract and independently authored hand/base-R oracle
   before translator implementation. Include cases that distinguish plausible
   but wrong translations.
2. Add an R twin and registered semantic gate for each new construct, source and
   portable-plan coverage, and original complete-program evidence. Check return
   values, stored widths, descriptor order and applicable row state.
3. Exercise empty input, skipped branches, malformed portable forms, invalid
   dynamic values and atomic failure. Require agreement through runtime, emitted
   Python and actual CLI execution. Preserve prior profile refusals.
4. Keep `sas_semantics.py` as the canonical reference. Readable twins belong in
   the external reference home and are excluded from this tree. Update rules and bounded capability evidence without inventing a function
   universe or claiming a whole external program from a component test.
5. Close the unchanged full verification command and required workload checks
   for the final source of that slice before advancing. Record actual outcomes
   and source hashes separately from registration counts.

Finish the wave with two additional original composition programs: one combining
the three character groups with missing-value handling, and one combining numeric
helpers, row summaries and calendar intervals. Freeze each program's oracle before
its composition implementation. Each program must exercise real source execution,
complete ordered results and only separately characterized report/output paths.

Inference: these programs provide a stronger finish line than helper counts alone.
They do not project additional Roku or official-example completions. Re-screen
those inventories after implementation and admit a target only after the entire
unchanged source passes its own independent comparison.

## Follow on work

After this wave, characterize bounded source-level PROC FREQ and broader SQL
SELECT, alongside an explicit external sample-data policy where an official
target requires SASHELP. Existing statistical and SQL reference gates remain
separate from source execution. Macros, general FCMP, DS2, IML, optimizers,
stochastic streams and external engines keep their separate backend contracts.
Retain H11/H12 and other source holds until their named questions are resolved.

## Public artifact boundary

Principal instruction recorded 2026-11-11: content prepared for `buntas-tofu` on
GitHub must be sanitized for local filesystem and related environment details.
Apply [the publication review](OPERATIONS.md#repository-synchronization) to code,
docs, commit and PR text, attachments, screenshots and generated evidence.
Use repository-relative paths and generic examples. Keep usernames, hostnames,
private addresses, credentials, local receipts and external source/reference
bodies outside the publication set. Preserve raw evidence locally and derive
sanitized public summaries without rewriting its historical provenance.

## Behavioral research starting points

Use the [SAS 9.4 Functions and CALL Routines reference](https://documentation.sas.com/api/docsets/lefunctionsref/9.4/content/lefunctionsref.pdf)
to fix the project version and selected index. Detailed earlier first-party
pages identify questions to recheck against that edition:
[SCAN](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p0jshdjy2z9zdzn1h7k90u99lyq6.htm),
[CMISS](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p1tth4ltf640din1ey86ubo2lky2.htm),
[COALESCEC](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p1g9btrql8d9x6n1iz6yowaqrq1v.htm),
[CEIL](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/n12bhb0oxndi2bn11205ojzgbdrw.htm)
and [INTCK](https://support.sas.com/documentation/cdl/en/lefunctionsref/63354/HTML/default/p1md4mx2crzfaqn14va8kt7qvfhr.htm).
Documentation supports characterization; executable independent oracles and
passing gates establish acceptance under the project's bounded policies.

## Verification history correction

An earlier version of this wave's negative CLI controls reused an output
directory. Their nonzero exits did not prove comparison failure. Those negative
control claims are withdrawn. Current gates give each control a fresh directory
and require its receipt to identify the dataset or logical-log comparison failure.
Each family now checks values,types,row order,column order,metadata and logical
records through six actual CLI controls. Typed whole-result checks also retain
dataset and descriptor order. Original hand values and independent R program
expectations are unchanged. Acceptance requires the corrected current source
to pass the full verification command and both workload suites.

## Publication integration

The publication change carries the approved wave onto the sanitized current
mainline,preserving the desktop work and its four additional suites. It retains
the mainline single-reference policy rather than restoring the retired mirrored
file. The combined registry has119fixture gates and84suites; publication requires
a fresh full receipt and both workload suites for that integrated source.
