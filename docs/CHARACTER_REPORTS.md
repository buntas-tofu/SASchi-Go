# Character records and titled logical reports

Status: bounded repository and independent base-R evidence for maintainer review.
The source-bound unified receipt decides acceptance. These profiles do not claim
live-SAS equivalence, physical listing layout, ODS output or general CSV support.

`DS-069` introduces `character-records-v1`: a named DATA step containing exactly
`INFILE DATALINES DSD`, one INPUT declaration, DATALINES4, its opaque physical
records, a standalone unindented `;;;;` terminator and explicit RUN. INPUT has
1..32 unique ASCII names and at least one colon character declaration such as
`word :$7.`. Character lengths are1..64; numeric length is8. The new portable
Step is `character_data`, with one `character_input` operation. Its ordered
columns, records and six physical source lines are validated before execution.

Each of0..1000 records has at most80 printable ASCII bytes. Commas preserve empty
fields, and every record must supply exactly one complete field set. Only outer
ASCII spaces are removed. Character cells pad to their declared width; empty
cells become spaces. Overwidth cells, a character period token, either quote,
control bytes and non-ASCII text refuse. Backslashes and semicolons are ordinary
record data. There is no FLOWOVER, truncation or quote interpretation in this
subset. Empty numeric fields become ordinary missing. Other numeric tokens use
the unchanged exact converter: at most32 bytes,15 significand digits, exponent
magnitude15, exact binary64 and absolute value at most2147483647. Tagged missing
values and inexact decimals remain outside that converter.

`ST-019` introduces `mixed-print-v1`; `ST-020` introduces `logical-title-v1`.
A genuine validated character producer selects the new program family. Programs
contain only character producers, existing ascending SORT, TITLE and default
`PROC PRINT DATA=name; RUN;`, with left-to-right dataset lineage and no supplied
initial catalog. Limits are64 Steps,32 TITLE statements and two PRINT invocations.
A producer requires a fresh destination. SORT may update its existing table;
previous reports retain their captured contents.

TITLE accepts a reset or one quoted literal with1..128 printable ASCII bytes and
a nonspace character. Literal leading/trailing spaces survive. Ampersand and
percent refuse because macro processing is outside this profile. TITLE state and
report ordinals start fresh for each run. Reports are named `print_01.txt` and
`print_02.txt`, in execution order. The separate report contract is
`ascii-titled-mixed-integer-v1`.

An active title produces `TITLE: ` followed by the literal and LF. The header is
`obs ` followed by lowercase column names in descriptor order. Each row has its
own1-based observation number, restarting for each PRINT, then single-space
separated values. Character values use JSON quotes after removing only padding
spaces from the right; stored dataset values retain their full width. Numeric
cells are ordinary missing, rendered as a period, or exact integers with absolute
value at most2147483647. Booleans, fractions, tagged missings and nonfinite cells
refuse before normalization. Each PRINT permits1..32 columns with at least one
character column, at most1000 rows, header1055 bytes, row415 bytes and total417056
bytes. These are independent rendering limits. An `obs` input column, labels,
formats, VAR, NOOBS, BY and pagination are outside this profile.

The old `numeric-print-v1` family keeps its one PRINT, `print.txt` name and
`numeric-space-fixed12-v1` contract. Its source and portable refusals stay in
force. The new expected-report reader is explicitly selected by contract and
permits one or two entries in at most two MiB; the previous default stays one
entry and one MiB. Exact basename-set and UTF8-byte comparison precedes successful
publication. A failure during the second PRINT publishes no accepted dataset,
report or export artifact. Portable validation also rejects hidden new operations,
cycles and invalid empty/skipped structures. C++ refuses these new Steps.

## Separate vendor benchmark

[The manifest](vendor-benchmark-manifest.json) pins the original1896-byte SORT
example and its Apache-2.0 LICENSE from `sassoftware/sas-code-examples` at commit
`579e057f90cd699f744fd6a1c8acaf9243f7ff67`. Source SHA256 is
`33ca0b33fb43b9cefe27c8879e204bfbe7ee0fe675769ec266bf9c5ed75d77c5`.
Run `python tools/prepare_vendor_sources.py` explicitly to acquire the two pinned
files into an external content-addressed cache. The default is
`/tmp/saschi-vendor-cache`; `SASCHI_VENDOR_CACHE` selects another external location.
`--check` and the fixture gates only verify existing bytes. A missing or corrupt
cache fails visibly, with no fixture-time network fallback or source execution.
Sources, LICENSE and derived complete outputs stay outside the Go checkout.

`examples/verify_vendor_sorted_copy.py` checks the entire unchanged source,
including both TITLE resets and PRINT invocations, against separately authored
hand and base-R lexers, descriptor/row accounting and rendering. The original
contains16 language statements plus one opaque payload,14 records,15 INPUT
attempts including EOF, eight execution Steps and38 semantic events. Fourteen
compiled rule applications are a different unit: existing SORT records its header
once while its BY and RUN remain separate source statements. Stable ASCII order
uses source ordinals3,5,4,10,11,12,13,14,2,1,6,7,8,9. Both datasets preserve
seven-byte character descriptors and cells. The two logical reports have375 and
402 bytes, with SHA256 values
`965c813bf45fcd5a95ee4d557820536b7126ad67dd3e207d729f7af78574d997`
and `5a0143b93d250c94d696e29a31acdfbd65003984ff448a1291778b592f807036`.
Runtime, emitted Python and actual CLI comparisons include the complete result;
eight wrong expected artifacts and a late second-report failure exercise rejection.

This vendor benchmark is separate from the56-file Roku corpus. Its proof marker
is `VERIFIED vendor:`, never `VERIFIED corpus:`. It does not increase the21 Roku
whole-program proofs. The character-input, mixed-print and logical-title gates
also use original synthetic sources, independent R witnesses, generated cases,
portable refusals and actual CLI controls. No third-party implementation or source
body is added to this repository.
