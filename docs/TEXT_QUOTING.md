# Text and quoting

Status: bounded DS-109 implementation for maintainer review. Acceptance requires matching source-stable full verification and both unchanged workloads. Independent hand/base-R evidence, no native SAS validation.

Printable ASCII only. Primitive direct assignments first. PROPCASE requires explicit 1..64-byte delimiters, argument-derived destination. QUOTE uses default double or a literal single/double quote, output <=200 bytes and inferred width 200; destination exhaustion refuses diagnostic/error state rather than truncating. DEQUOTE scans doubled quotes, terminates at the first unpaired quote and retains the remainder when no closing quote occurs; width inherits its argument. COUNTC uses explicit <=64-byte character set and literal I/V/T modifiers, at most three bytes, including empty-after-T returns zero. TRANSTRN nonoverlapping exact-byte matches, target 1..64 bytes, replacement 0..64 helper bytes, result <=200 bytes and inferred width 200. Direct empty literals remain held. Zero-length replacement source form is deferred to the consumer phase. Ordinary character assignment truncates except QUOTE buffer exhaustion.

Held forms: Locale, Unicode, default PROPCASE delimiters, COUNTC class/state modifiers, implicit conversion, nested calls and new profiles.

The original [text_quoting program](../examples/text_quoting_capture.sas) has 11 statements and complete hand/base-R expectations. The [registered gate](../examples/verify_text_quoting.py) compares canonical helpers, source/runtime, emitted Python and actual CLI, including six receipt-verified wrong comparisons. The source suite checks empty and skipped paths, descriptor/metadata/order preservation, caller nonmutation and late atomic failure.

Behavior sections are pinned to the externally cached [SAS 9.4 Functions and CALL Routines: Reference, Fifth Edition](https://documentation.sas.com/api/docsets/lefunctionsref/9.4/content/lefunctionsref.pdf?locale=en). Documentary and independent executable evidence do not establish native SAS validation.
