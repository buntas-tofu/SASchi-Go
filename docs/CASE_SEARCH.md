# Case and search contract

Status: DS-096 bounded implementation under the approved function-wave plan,
requiring its current full verification receipt for acceptance. Independent
hand/base-R evidence supports the stated slice; no live SAS comparison.

UPCASE and LOWCASE preserve printable ASCII bytes and source-derived fixed width.
INDEX searches exact leading/trailing blanks with one-based positions and zero
on absence. FIND accepts two character arguments, optional literal I/T modifiers
and an optional literal finite integral forward start in either documented argument
order, bounded 0..2147483647. Zero start returns zero. Negative starts require a
later slice. A T-trimmed empty needle refuses, pending a separate empty-search
contract. Original character operands are nonempty ASCII of length1..32767;
all-blank ordinary operands are otherwise supported. Numeric coercion, controls,
non-ASCII, invalid modifiers and nonintegral starts refuse.

Source calls are direct assignment RHS in version2 ordinary DATA steps, optionally
with one SET, declarations, simple IF/ELSE, prior counted loops, OUTPUT and existing
PUT. Primitive literal or preceding variable arguments only. Assignment storage
retains existing truncation and padding. No new WHERE, BY, RETAIN, arrays, rounded
profile, PROC, nested temporary or C++ admission. Static shape/type/literal checks
cover skipped branches and empty input; reached dynamic invalid values fail
atomically. Unreached dynamic calls remain lazy. Existing producers and profiles
do not inherit new forms. Logical evidence uses existing PUT records, not physical
SAS layout or a new PRINT/REPORT contract.

Authority: SAS 9.4 Functions and CALL Routines, Fifth Edition, externally pinned
PDF SHA2567ed4ed1d5ac861bfbf5ec6e99803de583549eb86a1e1662c40894dc7cc3468c5,
printed pages787..791,1051..1052,1199..1200,1618..1620.
Reference body remains outside Go. Original hand pins and source-reading sequential
base-R witness must agree before this contract is implemented.

The scalar hand pins and R witness were qualified before helper implementation.
During integration the first-party program moved LENGTH before SET to retain
the existing source boundary, and its complete-result expectation was corrected
to retain the supplied input table. Both revisions received independent hand/R
checks. Local history preserves the initial source, oracle revisions and failed
focused run. The final result envelope is integration evidence, not a claim that
that exact envelope was frozen before the first implementation.

Existing numeric array names UPCASE,LOWCASE,INDEX and FIND remain available for
bracket/brace indexing. A new scalar call inside an array-bearing step still
refuses under the separate composition boundary.

The new profile limits its expanded container traversal to16384visits and rejects
cycles. Presence detection uses a read-only deduplicated scan without that cap,
so prior plans with no new calls retain their existing size limits. The full
reference hash is updated for the approved appended helpers; an additional hash
and AST check pins the entire original103888-byte reference unchanged.
