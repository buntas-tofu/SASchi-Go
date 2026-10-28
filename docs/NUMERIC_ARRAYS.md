# Numeric array execution profile

Status: DS-039 repository/base-R evidence for principal/maintainer review.
Original helper and source-program witnesses, not a live-SAS comparison or a new
complete external-program proof. The local session handoff binds the exact
commit, passing receipt, workload compatibility and checkout ownership.

## Declarations and aliases

Numeric arrays bind an ordered list of DATA-row variables. Indexed writes change
the named variable, and ordinary variable writes are immediately visible through
the array. Overlapping arrays share those bindings. The array name is not a data
column, and ordinary scratch elements reset on each input row and each run.

The source profile admits one-dimensional declarations with a fixed integer
extent or lower:upper bounds, or an extent inferred from explicit names. Elements
may be listed individually or with an ascending numbered range such as x1-x3.
Ranges require a shared prefix and unpadded positive suffixes; PDV-order x--y
lists remain deferred. An omitted element list with a fixed extent generates
array-name1 through array-nameN. At most1024 declared element references are
admitted per DATA step, including overlapping declarations. Bounds and their
upper endpoint must be within signed2147483647. This is a tool profile limit.

Declaration bounds accept braces, brackets or parentheses. Element references
accept braces or brackets. Parenthetical element references remain deferred so
unwired function calls retain their existing refusal behavior. Array names must
not collide with row variables, other arrays, automatic names, wired functions
or the excluded statement names checked by the profile. Duplicate elements within
one declaration refuse. Declarations must precede indexed/OF references and
remain outside control bodies. Re-declare an array in each DATA step that uses it.

```sas
data d;
array score{0:2} first second third;
first=3;
score[1]=5;
score[2]=score[0]+score[1];
total=sum(of score{*});
output;
run;
```

This original program writes first=3,second=5,third=8,total=16. These are DATA-row
values, not an additional array object in the result. The gate uses a richer
two-snapshot original program to prove both alias directions and future schema
discovery. Source schema order follows declarations/first use; inherited numeric
labels, formats and lengths survive binding, including declarations before SET.

## Numeric and execution boundaries

Stored members accept finite binary64 numbers of magnitude at most2147483647
and ordinary missing. Character coercion, bool, tagged missing, nonfinite and
wider values refuse. Scalar assignments to array members use the same storage
check; unrelated scalar arithmetic retains its existing profile.

Indices must be integral and within declared bounds. New array expressions
support numeric literals, ordinary numeric variables, _N_, array reads, SUM OF,
and bounded exact +/-. Every arithmetic result must be representable without
rounding and remain within2147483647. SUM OF processes the declared element
order, ignores ordinary missing and returns missing when all elements are missing.
Every nonmissing ordered partial sum must meet the same exactness/range profile.
This differs from the retained sum statement's zero initialization. For example,
an array containing only missing values has a missing SUM OF result, while a
separate total+SUM(OF...) statement leaves its initialized total at zero.

Calls and division inside a new array-expression tree require separate composition
evidence. Store an array result in an ordinary scalar before passing it to an
existing function profile. This is a local expression restriction, not a ban on
other functions elsewhere in the DATA step. New trees have a32-level parse and
128-node-per-step budget; oversized new syntax refuses promptly.

Counted, single-level UNTIL and WHILE bodies can use indexed assignments and
bounded IF/ELSE actions. DS-041 adds [nested/computed counted bodies](COUNTED_LOOPS.md). Their existing scheduling/body limits remain. Declarations,
literal index errors and incompatible descriptors refuse even for empty, skipped
or zero-trip input. Dynamic indices are evaluated only when their statement runs;
out-of-range, missing and nonintegral indices then refuse with source-line
diagnostics. Descriptor discovery and OUTPUT suppression include skipped bodies.
Failures publish no accepted partial dataset or earlier buffered log.

Existing PUT paths and their formatting/width limits are unchanged. PUT a[i],
PUT array-name, new-array PUT_ALL compositions, array references in WHERE, MERGE
arrays, character/multidimensional arrays, temporary/initializer-retained
arrays, array members used as explicit RETAIN/sum-statement/BY/loop-index state,
DIM/LBOUND/HBOUND source calls and C++ array execution remain deferred. Existing
general array helper witnesses continue to cover their broader reference slices.

## Evidence and continuation

[The semantic gate](../examples/verify_numeric_arrays.py) combines hand pins,
1600 constructive cases, shared refusals and an original full synthetic source
program with an [independent native R witness](../examples/numeric_arrays.R).
R uses environment-backed bindings and an error-free addition residual check;
Python uses exact rational arithmetic for the new precision policy. Source
checks in [the array suite](../saschi/test_numeric_arrays.py) cover aliasing,
descriptors, control/OUTPUT composition, state reset, malformed serialized plans,
lazy dynamic indices, eager static refusals and atomic diagnostics. The isolated
wheel smoke also executes this profile with the standard library alone.

DS-040 separately supplies [bounded numeric DO OVER](DO_OVER.md): implicit
current-element binding, declared iteration order, reset and OUTPUT scheduling.
Its own source suite proves the entire pinned loops_foreach.sas program. DS-039
remains the indexed-array slice documented here. With DS-041,100_doors.sas compiles
but still refuses mixed literal/numeric PUT; A3 retains that proof obligation.

Primary syntax inputs: [SAS array syntax](https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a001022719.htm)
and [SAS array references](https://support.sas.com/documentation/cdl/en/lrdict/64316/HTML/default/a000203460.htm).
The narrower limits and atomic refusal behavior above are tool policies backed
by repository/R execution, not SAS diagnostic or _ERROR_ emulation.
