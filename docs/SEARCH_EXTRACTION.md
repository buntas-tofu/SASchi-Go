# Search positions and zero-length extraction

Status: DS-105 bounded implementation with an independently frozen original
hand/base-R oracle. Maintainer acceptance requires matching full verification
and workload receipts. No native SAS comparison is claimed.

FINDC and INDEXC return one-based character-set match positions or zero.
INDEXC accepts 1 through 31 excerpts and searches their union. FINDC accepts a
set of at most 64 printable ASCII bytes, optional I/K modifier combinations
and one integral start within magnitude 2147483647. I ignores ASCII case;
K selects the complement. Positive starts search right; negative starts search
left, clipped at the source end. Zero and excessive forward starts return zero.

FINDW requires an explicit nonempty delimiter set of at most 64 nonalphabetic
ASCII bytes. It supports optional I and signed starts. It searches literal
substrings with delimiter or string boundaries on both sides. A requested word
can itself contain delimiters, so tokenizing the input like SCAN is incorrect.
INDEXW qualifies only default or explicit singleblank delimiters. It removes
edge blanks from the excerpt; an empty resulting excerpt returns 1 only when
the source is empty or all blank, otherwise zero.

SUBSTRN accepts a primitive character source, a position and an optional length.
Position and length must be bounded integers or ordinary missing. Missing
values or nonpositive lengths yield an empty temporary. Otherwise extraction
intersects the requested interval with actual source bounds. Omitted length
extends to the source end, even for negative positions. A new stored destination
inherits the source width, then receives ordinary truncation and blank padding.
The earlier SUBSTR contract remains separately bounded.

Source character operands are nonempty printable ASCII literals or ordinary
variables with descriptors of width 1 through 32767. Helpers also qualify empty
strings. Modifiers and delimiter controls are literals. Every argument validates
before searching; skipped literals and empty input descriptors are checked,
while dynamic faults occur only when reached. Numeric conversion, fractional
indices, extra modifiers, default FINDW delimiter sets and alternate INDEXW
delimiters remain held. The separate [consumer profile](FUNCTION_CONSUMERS.md) qualifies its finite
character-item joins without broadening these primitive operand policies.

The ten-statement original processes all six records, comparing every search
position, extracted stored field, descriptor and logical record. Thirty-seven
hand pins, 400 generated cases, 24 shared refusals and five empty-helper cases
qualify the independent byte-array R witness. Runtime, emitted Python and the
actual CLI compare complete results, with six receipt-verified negative CLI
comparisons. Source tests include late failures for all five functions,
metadata/order preservation, deterministic repeated execution and array names.

Behavioral reference: SAS 9.4 Functions and CALL Routines, Fifth Edition P11,
FINDC, FINDW, INDEXC, INDEXW and SUBSTRN.
