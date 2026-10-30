# Bounded descriptor-only PROC SQL creation

Status: repository/base-R evidence for principal and maintainer review. This
profile describes empty typed descriptors and declared logical stdout. It does
not establish live-SAS equivalence, physical SQL notes, general PROC SQL, a query
backend or DML behavior. Full source/runtime/emitted/CLI acceptance is required
in addition to helper and independent-R evidence.

## Primary characterization

The [SAS SQL Creating Tables reference](https://support.sas.com/documentation/cdl/en/sqlproc/63043/HTML/default/p1l9ypkml4febvn0zsbkwev7v5x9.htm)
describes creating a table without observations by defining columns and their
attributes. The [CREATE TABLE statement reference](https://support.sas.com/documentation/cdl/en/sqlproc/63043/HTML/default/n07kfcv1vbih8rn1k9epo45umxil.htm)
distinguishes column definitions from LIKE and query-based creation. The
[column-definition reference](https://support.sas.com/documentation/cdl/en/proc/61895/HTML/default/a002473683.htm)
defines character width and documents the broader numeric type mapping. This
increment uses only explicit CHAR(n); defaults, aliases and numeric declarations
remain outside its scope.

The [PROC SQL and ANSI comparison](https://support.sas.com/documentation/cdl/en/sqlproc/63043/HTML/default/p0corah7t43hy7n1r7efplde5c8z.htm)
explains that SAS reserves few SQL keywords and often does so contextually; CASE
is always reserved as a column name. The stricter keyword exclusions below are
tool policy, not a universal SAS keyword rule. Primary sources consulted2026-10-30.

## Accepted source and portable shape

Design inference: one bare PROC SQL header, exactly one descriptor-only CREATE
TABLE statement, and QUIT form a supported procedure. Multiple separate supported
procedures can occur in one program. RUN does not substitute for QUIT in this
profile. The existing splitter owns comments, statement termination and opaque
source boundaries; each declaration must be consumed completely.

The destination is one unqualified ordinary ASCII identifier. Columns are an
ordered list of1..64 unique ordinary ASCII identifiers. Names begin with a letter
or underscore, contain letters, digits or underscores, have at most32 characters,
and normalize to lowercase. Case-insensitive duplicates refuse. Automatic names,
_NULL_, and the explicit conservative keyword set in saschi/sql_create.py refuse
in either table or column position. That set includes the grammar words and common
SQL clause, type, constraint and DML keywords. Quoted names, name literals,
qualified names, macros and non-ASCII identifiers remain deferred.

Each column requires CHAR with an explicit unpadded ASCII decimal width1..32767.
Bare CHAR, CHARACTER, VARCHAR, NUMERIC and other aliases/types refuse. The splitter
statement passed to the CREATE helper has a16384-character ASCII cap after the
shared scanner canonicalizes source whitespace. A direct standalone helper call
applies that cap to its supplied declaration string. Raw whitespace padding is
not a whole-source byte limit. These list,
name, width-spelling and resource bounds are implementation policies.

The new version2 step kind is `sql_create`; its name is the normalized destination.
It has exactly one `sql_create` operation with an ordered `columns` list. Each
column contains exactly name, type and length, with type character. The operation
has a positive source line at or after the PROC header. All ordinary Step fields
for inputs, keys, retention, lengths, display metadata and predicates keep their
empty/default values. Shape, types, bounds and normalized names validate
independently of the source compiler. No recursive expression walker or SQL engine
is needed for materialization.

The result is an ordered schema of character type/byte-length descriptors and an
empty rows list. No observation, label, attached format, encoding or SQL diagnostic
is invented. The existing typed table contract supplies any later consumption;
this increment does not create string values or claim transcoding behavior.

## Destination and failure policy

Design inference: every preexisting destination refuses, even an empty table or
a case-different spelling of the same name. A second CREATE of the same normalized
name in the same program also refuses. This avoids inferring overwrite behavior
across SAS storage engines. It is not an emulation of SAS overwrite warnings,
replacement settings or recovery behavior.

Catalog normalization remains the shared runtime boundary. Materialization
returns a fresh table, preserves column order and fixed widths, and does not
mutate the caller's catalog or portable plan. A later refusal discards the whole
accepted result and buffered logical output, including earlier DATA-step logs.
C++ execution remains refused.

AS SELECT, LIKE, constraints, column modifiers, labels, formats, informats,
table/PROC options, schemas/librefs, INSERT, UPDATE, DELETE, ALTER, joins,
expressions, reports, macros and general SQL remain unsupported. A recognized
PROC SQL header does not authorize any of these operations.

## Evidence and original programs

The fixture pairs8 hand descriptor pins with400 generated declarations. The
independent base-R witness tokenizes declarations and scans complete source,
checks procedure boundaries and destination collisions, and accounts for every
statement and declared column. It does not invoke Python, an SQL engine or a SAS
runtime. The193 shared declaration refusals cover type, width, name, duplicate, keyword,
constraint and trailing-text boundaries. Five naive alternatives lose separate
controls for descriptor order, default-width substitution, an invented blank row,
invented metadata and a numeric replacement for a character descriptor. Each
alternative is rejected by the ordered-tree comparison, the typed table
comparator and an actual CLI job using its expected-file comparison. Every failed
comparison records comparison=failed, publishes observed.json for diagnosis and
does not publish an accepted result.json. Ten
additional procedure-boundary refusals and one independent existing-name refusal
check whole-source admission and destination policy. A separately named helper-only
resource refusal and an accepted normalized-whitespace source control distinguish
the standalone helper input cap from scanner normalization.

The original sql_create_capture.sas contains6 executable statements across two
procedures. It creates contacts with widths8,40,2 and widths with lengths1,32767,17.
Both tables have zero observations. The entire unchanged sibling
table_creation_postal_addresses.sas contains3 statements and creates address with
ordered character widths8,50,25,2,20. Both programs require empty logical stdout;
physical SAS SQL notes are excluded from that record contract. No sibling source
is copied into this repository.

Complete-program acceptance requires source hashes, complete ordered descriptor
and empty-result pins, independent whole-source R accounting, emitted Python and
actual CLI agreement. Compiler-clean status alone is insufficient. Tests also
require refusal of unsupported trailing source, forged portable descriptors,
existing destinations and C++ execution, plus atomic failed publication after an
earlier DATA-step log. The original and corpus source pins are recorded in the
fixture verifier; receipts bind the tested checkout and environment.
The result pins preserve mapping insertion order rather than sorting schema keys;
independent R, runtime, emitted and CLI trees are compared with ordered mappings.
