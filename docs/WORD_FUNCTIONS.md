# Explicit delimiter word functions

Status: DS-097 implementation with independently qualified original hand/base-R
oracles under the approved wave. Acceptance requires its current full source-bound
receipt; no live SAS comparison.

Pin the SAS9.4 Functions and CALL Routines Fifth Edition P11 reference, PDF SHA256
7ed4ed1d5ac861bfbf5ec6e99803de583549eb86a1e1662c40894dc7cc3468c5, printed
pages595..599 and1484..1490. This edition gives a new DATA-step SCAN destination
the first argument width. Earlier documentation used200; no cross-version claim.

Source character arguments are printable ASCII length1..32767. Require an explicit
literal delimiter set of1..64printable ASCII bytes. Optional literal M or m admits
empty words; all other modifiers, default delimiters, quote handling and temporary
consumers remain refused. SCAN requires an integral nonzero count with magnitude
at most2147483647, literal or preceding numeric variable. Positive counts select
from the left; negative counts select from the right. With M, delimiters bound
empty words; without M, omit empty words. Out-of-range SCAN is empty with M and a
blank without M; assignment then uses its declared target width. COUNTW shares
that word definition. All-blank source values are allowed. Empty source literals,
implicit coercion, missing counts, invalid bytes and unqualified modifiers refuse.

Reuse only the wave's direct assignment version2 DATA contexts, one optional SET,
existing declarations/simple IF/counted loops/OUTPUT/PUT, static empty/skipped
checks and atomic reached failures. Preserve existing source and portable refusals
and numeric arrays named SCAN or COUNTW. The original whole program retains the
complete supplied table, fixed descriptors, six logical PUT records and all rows.

Wave provenance is emitted in deterministic family/name order. Cross-process
plan and generated-Python hashes must agree across Python hash seeds. The
initial passing full run precedes this repair and remains separate from final
acceptance evidence. Deep new-root and old-outer source probes refuse cleanly.
