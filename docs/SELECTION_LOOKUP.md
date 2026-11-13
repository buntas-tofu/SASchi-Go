# Selection and lookup

Status: bounded DS-111 implementation for maintainer review. Acceptance requires matching source-stable full verification and both unchanged workloads. Independent hand/base-R evidence, no native SAS validation.

Direct primitive arguments. All reached arguments validate eagerly, including unselected values. Finite numeric operands within +/-1000000 and ordinary missing. IFN/IFC use true/nonzero, false/zero and optional missing branch; missing without fourth argument selects the false branch. CHOOSE uses 1..31 candidates and a nonzero signed integral index whose absolute value is within list length. Zero/missing/fractional/out-of-range index forms refuse diagnostic/error state. Character operands printable ASCII <=200 bytes; IFC and CHOOSEC infer 200-byte destinations. WHICHC compares padded character equality, WHICHN numeric equality; first duplicate wins, missing search returns ordinary missing, no match zero.

Held forms: Tagged missing, implicit conversions, OF lists, queues, nested arguments and profile joins.

The original [selection_lookup program](../examples/selection_lookup_capture.sas) has 14 statements and complete hand/base-R expectations. The [registered gate](../examples/verify_selection_lookup.py) compares canonical helpers, source/runtime, emitted Python and actual CLI, including six receipt-verified wrong comparisons. The source suite checks empty and skipped paths, descriptor/metadata/order preservation, caller nonmutation and late atomic failure.

Behavior sections are pinned to the externally cached [SAS 9.4 Functions and CALL Routines: Reference, Fifth Edition](https://documentation.sas.com/api/docsets/lefunctionsref/9.4/content/lefunctionsref.pdf?locale=en). Documentary and independent executable evidence do not establish native SAS validation.
