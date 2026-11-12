# Bounded character rewriting

Status: bounded implementation with an independently qualified hand/base-R oracle.
Acceptance requires the current full source-bound receipt; no native SAS comparison.

Printable ASCII source length1..32767. COMPRESS accepts source alone to remove
blanks, or a literal1..64byte character set and optional literal I/K subset. K
keeps selected characters; I matches ASCII letters regardless of case. Empty
results remain raw empty strings and store with ordinary padding. New COMPRESS
and TRANSLATE destinations inherit source width under the pinned SAS9.4 P11
reference. TRANSLATE accepts exactly one literal TO/FROM pair, equal lengths1..64
and distinct FROM bytes. Unequal lists,multiple pairs and duplicate mappings need
separate evidence. Replacement preserves character positions and source width.

TRANWRD accepts literal target length1..64 and literal replacement length0..64.
An empty replacement supplies one blank; matching preserves significant blanks
and consumes nonoverlapping source occurrences without rescanning inserted text.
Raw result length may not exceed200bytes. New destination width is200; existing
destination assignment retains its declared truncation/padding policy. No general
regex,Unicode,implicit coercion,error-state or longer-result claim. Literal
arguments validate even on skipped/empty execution; dynamic overflow or invalid
characters fail atomically when reached.

Reuse only approved wave ordinary DATA direct assignment contexts. Control
arguments are literal; source may be a preceding character variable. Preserve
prior profiles, nested-consumer refusals and numeric arrays bearing these names.
Reference: externally pinned SAS9.4 Functions and CALL Routines Fifth Edition P11,
printed pages568..571,1594..1596,1599..1602.

A later direct-helper audit found that Unicode uppercasing admitted a dotless-i
modifier outside the ASCII source contract. Source admission already refused it.
A separate hand/base-R byte check preceded the repair: the helper and independent
R modifier path now reject non-ASCII before case mapping. Original ASCII pins and
whole-program expectations are unchanged; the frozen original oracle remains in
local history alongside the boundary revision.
