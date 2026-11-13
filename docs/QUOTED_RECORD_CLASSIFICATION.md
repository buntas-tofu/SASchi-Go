# Quoted record classification

Status: complete bounded program evidence for principal and maintainer review. Acceptance requires a matching stable full receipt and both unchanged workloads. Independent hand/base-R evidence, no native SAS or new external-program proof.

Separately marked function-consumers-v2 ordinary DATA steps. Root IFC with NOTALNUM(primitive)=0 or EQ 0 and primitive character choices; root IFN(primitive,primitive,LARGEST(primitive,...primitive)); root CATS with primitive items or one primitive-argument PROPCASE/DEQUOTE item, at least one such new call; root TRANSTRN(primitive,primitive,TRIMN(single literal blank)). Selected direct validator/MISSING IF comparisons use existing numeric aliases and right literal integer0..32767. Other direct calls retain their own family domains. Reached selector arguments evaluate eagerly; statement branches remain reached-only. Static literal/descriptor checks run on empty/skipped paths. New stored IFC/CATS/TRANSTRN widths200.

The [original program](../examples/quoted_record_classification_capture.sas) has 26 statements, 6 hand records and 26 completely checked columns. The [registered gate](../examples/verify_quoted_record_classification.py) compares its whole independent R witness, runtime, emitted Python, actual CLI and30complete input catalogs. Six actual wrong CLI comparisons require their intended failure receipts. Late faults publish no partial result or logical output.

Held forms: General WHERE, subsetting IF, compound Boolean, bare-call truth, swapped comparisons, deeper/unlisted nesting, loops, arrays, queues, BY, RETAIN, multiple driving inputs, SQL, C++, mixed marker versions and specialized numeric profiles.
