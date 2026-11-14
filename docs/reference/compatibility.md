# Compatibility and migration contracts

Applies to toolkit 0.1.2 and kit 0.1.13. Version axes are independent.

| Axis | Supported value | Unsupported behavior |
| --- | --- | --- |
| Archive | 1 | Explicit error; no migration on open |
| Local contract | 0.1.0 (review receipts also read 0.1.1) | Blocked migration plan; no guessed upgrade |
| Profile | 0.1.0 | Explicit error |
| FHIR | R4 4.0.1 | Separate blocked FHIR conversion report |
| Serialization | helseark-json-1 | Explicit error |
| Agent protocol | 1 | Explicit error |
| Current kit | 0.1.13 | Exact retained compatible manifests required |
| Test-only layout | helseark-test-only-layout-0 | Requires explicit fixture opt-in; no public release status |

Production archive 1 semantics are frozen for this release. New toolkit code does
not replace retained schemas/definitions/kits or reinterpret old clinical values.
Existing compatible kit pins, including 0.1.3 and older, remain byte-identical in
their vaults and migrations. `plan_migration` carries those exact bytes; it does
not upgrade them to the currently installed kit. The real canonical profile base
is `https://github.com/ricardocabral/helseark/fhir/StructureDefinition/`, with explicit
`|0.1.0` versions. These URLs identify local retained definitions; they are not
network resolution requests. No provisional namespace replacement is performed.

## Library and CLI

`VersionSet` contains archiveFormatVersion, contractVersion, profileVersion,
fhirVersion and serializationVersion. `plan_migration(Vault, VersionSet)` returns
a `MigrationPlan` bound to source heads and all retained byte hashes. Plans use
the closed [migration envelope](../../schemas/0.1.0/migration.schema.json).
`requiredDefinitions` enumerates exact source definitions and kit files with
hashes/sizes; the supported target uses those same exact definitions. Nothing is
resolved against a moving installed/latest contract. Historical definitions must
all remain present and match their locks.

`apply_migration(vault, plan, destination, reviewedPlanSha256=..., resume=False)`
recomputes the plan, rejects changed, lossy, ambiguous or unsupported mappings,
and uses Task8 backup/restore followed by atomic absent-destination publication.
The receipt supplies destination, mappingInventoryPath, validatedCounts,
validationCoverage and originalUnchanged. `originalUnchanged` compares retained
source hashes captured by planning with a fresh read under the final writer lock.
The mapping inventory records the full plan and each old/new file path, SHA-256
and byte size. It is migration provenance, not a new clinical amendment.

`migrate plan --to-contract VERSION` emits JSON on stdout; redirect it outside
both vaults. `migrate apply --plan FILE --reviewed-plan-sha256 DIGEST --into PATH`
requires explicit human review of that plan. `--resume` chooses staging reuse.
`--test-only-legacy` must be supplied on both operations for the synthetic layout.
There are no scripts, callbacks or plugin names in input plans.

Only two dispatch entries exist: v1 identity copy and opted-in test-only wrapper
layout to v1. Both preserve every accepted byte and reference without rewriting.
No clinical content transform, omission, unit conversion, ID reassignment or
FHIR release conversion is implemented. Unknown targets yield blocked plans;
unknown source versions fail before a plan is emitted. Missing/changed definitions
or kits fail before publication. Destination must be absent, not an existing
empty directory. ZIP/tar migration inputs are unsupported.

`plan_fhir_migration(vault, version)` / `migrate plan --to-fhir VERSION` returns
`FHIRMigrationPlan` (`planClass=fhir-release`), with unevaluated semantic losses
and a conversion blocker. Archive apply rejects this distinct class. R4→R5 has
no evaluated converter, mapping, loss report or supported destination graph.

Exit codes: 0 supported plan/apply; 2 invalid input/plan/existing destination;
3 missing or mismatched review; 4 stale source, writer conflict or staging awaiting
explicit resume; 5 integrity/I/O; 6 unsupported version or blocked transformation.

## Preservation scope and limits

Every retained file, including work, sources, accepted revisions, review receipts,
definitions, kits and previous migration inventories, is hashed. Task8's transient
`.runtime` and `derived` trees are excluded and never clinical authority. Source
locking may create runtime lock directories; planning itself writes nothing.
Queries are derived from identical accepted bytes, so IDs, precision, evidence,
status and correction chains retain their original meaning. A clean inventory
is not an extraction accuracy, medical correctness, authenticity or complete
FHIR-conformance claim. Terminology and extraction accuracy remain not checked.

POSIX local macOS/Linux publication uses the qualified Task8 no-replace rename;
Task11 process-death tests cover staged failure and resume. Power loss and all
filesystems are not implied by a process-death test. Windows is unsupported.
Original vault/verified backup is rollback; no inverse conversion is promised.

Migration receipts are household metadata: doctor checks their closed receipt
shape, sealed plan and historical self-consistency, and whole-vault backups retain their exact bytes. Person
exports omit these mappings explicitly. A receipt records a historical copy; it
is not authenticated authority or a claim that mutable work still has old hashes.
Unknown or malformed files under `migrations/` block whole-vault recovery/export.

Historical validation requires an exact supported version pair and its single
dispatched operation, safe unique source/destination paths, complete mapping
coverage of the dispatched source inventory, exact old hash/size bindings, complete
required-definition/kit inventory, and unchanged new hashes for both lossless
operations. It never compares historical mutable work or source heads to today's
state, requires no signature, and does not rewrite valid old receipts. Kit 0.1.8
remains a compatible historical input; other branch-local kit numbers are not aliases for this combined inventory.
New vaults use 0.1.13; existing vaults retain their exact pins and accepted history.

Person removal plans/results inventory retained shared receipts in
`retainedLocalMetadata` (path, SHA-256, size, personId, sourceHead). Approval binds
that disclosure; remaining-known-copies also lists their active paths. Removal
does not erase this historical metadata or securely delete quarantine/backups.
Older removal journals without this field remain restorable with their original
digest. Applying an old plan in a vault with undisclosed local receipts requires
a new plan and approval.
