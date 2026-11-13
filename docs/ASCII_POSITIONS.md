# Ascii positions

Status: bounded DS-110 implementation for maintainer review. Acceptance requires matching source-stable full verification and both unchanged workloads. Independent hand/base-R evidence, no native SAS validation.

Printable ASCII 0..32767 helper bytes, nonempty primitive literals or descriptor-backed source operands. Seven exact masks; one-based first match, no match/zero/beyond-end start returns zero; negative starts search left from min(abs(start),length). Starts integral within +/-2147483647. Missing start means 1 except ANYPUNCT missing start is held. Stored padding participates.

Held forms: Locale, nonprintable bytes, multilingual functions, fractional starts, tagged missing and all new consumers. ANYPUNCT missing start is deliberately refused because pinned PDF page 261 says both begin-at-start and return-zero for missing. No native observation resolves that documentary conflict. Earlier character-validation contract remains unchanged.

The original [ascii_positions program](../examples/ascii_positions_capture.sas) has 14 statements and complete hand/base-R expectations. The [registered gate](../examples/verify_ascii_positions.py) compares canonical helpers, source/runtime, emitted Python and actual CLI, including six receipt-verified wrong comparisons. The source suite checks empty and skipped paths, descriptor/metadata/order preservation, caller nonmutation and late atomic failure.

Behavior sections are pinned to the externally cached [SAS 9.4 Functions and CALL Routines: Reference, Fifth Edition](https://documentation.sas.com/api/docsets/lefunctionsref/9.4/content/lefunctionsref.pdf?locale=en). Documentary and independent executable evidence do not establish native SAS validation.
