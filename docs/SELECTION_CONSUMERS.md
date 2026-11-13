# Nested and if consumers

Status: bounded DS-115 implementation for maintainer review. Acceptance requires matching source-stable full verification and both unchanged workloads. Independent hand/base-R evidence, no native SAS validation.

Separately marked function-consumers-v2 ordinary DATA steps. Root IFC with NOTALNUM(primitive)=0 or EQ 0 and primitive character choices; root IFN(primitive,primitive,LARGEST(primitive,...primitive)); root CATS with primitive items or one primitive-argument PROPCASE/DEQUOTE item, at least one such new call; root TRANSTRN(primitive,primitive,TRIMN(single literal blank)). Selected direct validator/MISSING IF comparisons use existing numeric aliases and right literal integer0..32767. Other direct calls retain their own family domains. Reached selector arguments evaluate eagerly; statement branches remain reached-only. Static literal/descriptor checks run on empty/skipped paths. New stored IFC/CATS/TRANSTRN widths200.

Held forms: General WHERE, subsetting IF, compound Boolean, bare-call truth, swapped comparisons, deeper/unlisted nesting, loops, arrays, queues, BY, RETAIN, multiple driving inputs, SQL, C++, mixed marker versions and specialized numeric profiles.

The original [selection_consumers program](../examples/selection_consumers_capture.sas) has 13 statements and complete hand/base-R expectations. The [registered gate](../examples/verify_selection_consumers.py) compares canonical helpers, source/runtime, emitted Python and actual CLI, including six receipt-verified wrong comparisons. The source suite checks empty and skipped paths, descriptor/metadata/order preservation, caller nonmutation and late atomic failure.

Behavior sections are pinned to the externally cached [SAS 9.4 Functions and CALL Routines: Reference, Fifth Edition](https://documentation.sas.com/api/docsets/lefunctionsref/9.4/content/lefunctionsref.pdf?locale=en). Documentary and independent executable evidence do not establish native SAS validation.

The [wave 3 register](FUNCTION_WAVE_3_COMPOSITION.md) records the exact finite assignment/IF grammar, engineering resource bounds, earlier-profile isolation and both complete-program consumers. The portable marker is checked independently before recursive runtime validation.
