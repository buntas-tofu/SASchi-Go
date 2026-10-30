# Bounded rounded numeric rows and projection

Status: DS-052/DS-053 repository/base-R evidence for principal and maintainer
review. This profile proves the stated numeric comparison policy, ordered
descriptors and observations, and declared logical text. It does not establish
live-SAS equivalence, exact SAS BEST12/DECIMALCONV output, physical diagnostic
fidelity or independent transcendental algorithms. No new complete sibling
program proof is claimed.

## Primary characterization

The [SAS variable-selection reference](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a000695119.htm)
distinguishes input options, applied before variables enter the PDV, from output
selection, applied while values are written. Output-excluded variables remain
available for computation. The [DATA-step overview](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a000985872.htm)
describes compilation before execution and discovery of variable types, lengths
and descriptor information during compilation.

The [SET statement reference](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000173782.htm)
describes reading one observation into the PDV per execution of SET. The
[automatic-missing reference](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a001291423.htm)
distinguishes newly created variables from variables read by SET. Newly created
scratch variables begin each iteration missing unless retained; SET variables
retain their state until another assignment or read replaces it. Reading the
next observation replaces imported values, including an ordinary missing value.
The [sum-statement reference](https://support.sas.com/documentation/cdl/en/lestmtsref/63323/HTML/default/n1dfiqj146yi2cn1maeju9wo7ijs.htm)
defines retained zero initialization and missing addends treated as zero.
Sources consulted2026-10-30. These sources characterize SAS state and timing;
they do not define this tool's admission bounds or comparison tolerances.

## Separate admission marker

Design inference: new numeric syntax combined with projection or one SET selects
`numeric_profile` with name `binary64-rows-v1`. The operation shape stays unchanged.
The existing `binary64-v1` marker remains restricted to its earlier profile and
cannot be forged to admit projection or SET. The new marker requires both an
executable power/Pi/trigonometric trigger and an actual supported composition.
Metadata containing a trigger-shaped object does not authorize execution.

DS-052 admits the existing top-level KEEP/DROP statement or DATA output option
with rounded scalar operations. The numeric marker is first. A DATA output
projection can be second only when the validated numeric marker shares its DATA
source line. Earlier explicit OUTPUT snapshots use the completed static output
descriptor, including variables discovered later or in skipped branches. Output
selection does not remove working PDV values or retained state.

DS-053 separately admits exactly one driving SET before executable actions,
optionally with the existing input projection. It can compose with one existing
output selection. Declarations and projection markers before SET retain their
declarative meaning. An executable assignment, PUT, OUTPUT or subsetting action
before the driving read refuses, including for an empty input.

Implementation inference: SET resolves through the existing dataset table map,
whether supplied by the caller or produced by an earlier accepted DATA step in
the same program. Both origins are witnessed. No new provenance field is added.
Earlier plan shapes, exact arithmetic contracts and output profiles remain
unchanged.

## Imported descriptors and state

Full generic catalog normalization precedes input selection. Excluded columns
cannot hide malformed descriptors, row shapes, encoding, metadata or generic
numeric values. Legal excluded columns keep the earlier generic catalog
contract; selecting them out does not impose the new binary64 arithmetic bounds
on their original source table.

After input selection, every selected descriptor must be an ordinary-name
numeric descriptor with the existing8-byte storage contract. Every selected
imported value validates eagerly, including unused values, later-overwritten
values, output-excluded values and values on skipped paths. The bounds remain
ordinary missing, zero or finite normal binary64 with magnitude at
most2147483647. Tags, bool, character values, subnormals, nonfinite and wider
selected values refuse. This eager selected-input contract is tool policy, not a
claim that SAS rejects these values in the same way.

Signed zero normalizes only in a private selected source view. The caller's
catalog and the returned original source table retain their previous values.
Selected descriptors preserve source order, type, length, label and format;
dataset encoding and label survive. An attached format can be transported, but
formatted numeric PUT remains outside the existing text contract.

Selected SET variables participate in the existing input retention and are then
replaced by each complete incoming observation. A missing imported sum target
therefore replaces the prior target before the sum statement executes. An
excluded and reintroduced scratch variable starts missing every iteration. An
excluded and reintroduced sum target uses its independent retained accumulator.
State resets at the established row, step and run boundaries. Empty input still
validates selected descriptors and complete static discovery, producing an empty
observation list with the correct selected output schema.

## Numeric and text policies

All arithmetic, function, domain, ordinary-missing and error-state limits in
[BINARY64.md](BINARY64.md) remain. Counted controls keep their existing integer
contract and per-observation loop budget. Projection lists keep the existing
ordinary-name/range and64-name bounds. No new function or numeric domain is added.

The numerical metric is abs(a-b)/(epsilon*max(1,abs(a),abs(b))), with
epsilon=2**-52 and budget32. Missing masks, schema and observation order,
multiplicity, metadata values and logical records are checked separately and
exactly. The numerical tolerance is an acceptance policy, not a measured SAS
accuracy bound. R and Python may share a host mathematical library.

Logical numeric records retain the inferred fixed-decimal policy:12-character
fields,64-column records, one following blank per field, ordinary missing as a
period, and the earlier midpoint/carry refusals. The renderer is not labeled an
exact SAS BEST12 implementation. Scientific output and wider formatting remain
deferred. INPUT, arrays, WHILE/UNTIL, BY, WHERE, MERGE, initial lookup, general
options, procedures, macros and C++ remain separate contracts.

## Evidence and original program

The separate numeric-projection gate has6 hand source pins,240 generated
source/runtime/R schedules,7 boundary controls (5 shared source refusals and2 explicit old-marker refusals) and6 competing comparator controls.
Its hand pins cover all three output-selection forms, early and late snapshots,
skipped static discovery and counted-loop composition.

The numeric-set gate has8 hand source pins,360 generated multirow schedules,
21 boundary controls (19 shared source refusals and2 explicit old-marker refusals) and6 comparator controls. The hand witnesses cover empty
input, supplied descriptors, missing replacement, scratch reset, imported sum
targets, retained totals and counted loops per observation. Shared refusals check
eager selected values, selected descriptor/name errors, supplied unknown PUT
names, formatted PUT on populated and empty inputs, and the unchanged
unsupported frontier. Independent review found and corrected four R admission
gaps: numeric storage width, executable prefixes, selected reserved names and
static formatted PUT. The accepted witnesses and refusal comparisons were rerun.

The25-test source suite adds metadata and catalog nonmutation, private signed-zero
normalization, selected-out legal generic values, inherited formats, forged
markers and read placement, hidden failure, exact old contracts and two
observations each using the full10000-trip counted budget. Each gate checks
sampled emitted Python, actual CLI acceptance and a refusal that publishes no
accepted result or buffered logical output.

The original `examples/numeric_rows_capture.sas` consumes28 statements across
three DATA steps. It reads three supplied observations, writes two selected
observations to shaped, then reads those two prior-step observations into follow.
The final catalog-free step writes two fresh observations. The step iteration
counts are3,2,1, with zero explicit loop trips. There are six produced
observations and six ordered logical records, separate from the three supplied
observations retained in the returned catalog. Excluded input values do not
reappear in the working PDV, scratch does not carry between rows, and selected-out
working values remain usable for computation and PUT. Source/runtime, independent
R, emitted Python and actual CLI agree under the declared policies.

The R witness independently scans the entire source, parses numeric expressions,
performs static discovery and schedules projection, input reads, retained state,
conditions, counted loops and snapshots. It reuses the earlier independent R
numeric and projection helpers; it never evaluates Python output. Appended code
and missing final terminators refuse. The original is first-party material and
does not copy sibling corpus source.

| Artifact | SHA-256 |
| --- | --- |
| Original source |f662ecd018d7da511da0ec786d008ebac1bddc52a0dc10b4429b82a5985a3ce6 |
| Canonical reference result JSON |bd55e027f5c3edec7ab592051ec71c4bd81b790fbfea4cc775cedafce1436792 |
| Declared logical stdout |2a7648ae08bdc6254170ff46d4618aeb9071bf03a25e86946021d0914c638460 |

The reference JSON pin uses sorted keys and compact separators. Actual numeric
acceptance retains the declared tolerance; the hash does not silently replace
that policy with universal cross-platform bit identity.


## D1 source-boundary promotion event

DS-054..057 separately route newly proved INPUT/array/WHILE/UNTIL combinations
to binary64-pipeline-v1. The old binary64-rows-v1 marker still refuses them.
The C1/C2 gates retain the exact former ARRAY and WHILE frontier source controls:
independent old-profile R still refuses, independent D1 R and source/runtime now
agree on acceptance, and forcing the same parsed plan back to the old marker
refuses. No case was deleted or skipped. C1 retains7 boundary controls, split
into5 shared source refusals and2 old-marker/new-profile controls. C2 retains21,
split into19 shared source refusals and2 old-marker/new-profile controls.
The prior source suite likewise retains its exact ARRAY, WHILE and UNTIL clauses,
proving new-marker acceptance and old-marker refusal. Every other recorded
unproved clause remains source-blocked. These are separately counted admission
boundaries, not new shared source refusals or a relaxation of the older profile.
