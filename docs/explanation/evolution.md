# Why migrations produce a new vault

Applies to toolkit 0.1.2, archive 1 and kit 0.1.15.

Clinical corrections and storage migration are different decisions. A correction
records a reviewed new assertion and preserves its predecessor. Migration should
preserve those assertions, their review, sources and evidence while changing a
representation only through an evaluated mapping. It cannot turn a missing fact
into a deletion or a changed serializer into a laboratory amendment.

This release has no production breaking contract change. Its nontrivial engine
example is an explicitly labeled synthetic legacy container: a verified backup
nested at `snapshot/`. Removing its layout prefix creates a regular vault while
retaining accepted bytes exactly. This exercises dispatch, mappings, full graph
verification, human review, staging, process-death recovery and rollback without
inventing an old production clinical schema. Production v1-to-v1 copying uses
the same gates. Future semantic migrations need independent fact/query fixtures,
explicit loss and ambiguity handling, and an adopted compatibility decision.

The plan binds the entire retained input and required definitions. Apply accepts
only code-owned transformations and recomputes the plan, so editing a plan cannot
install a converter or waive losses. It snapshots/restores through the existing
portability boundary and verifies the destination before no-replace publication.
A final source hash comparison detects a changed base. Migration provenance sits
outside immutable accepted history. Source and backup remain the recovery path.

A FHIR release conversion is a different plan class because changing an entire
resource vocabulary can alter meaning and references. R4→R5 remains unsupported;
a blocked conversion report cannot pass archive apply. Read the [compatibility
reference](../reference/compatibility.md) for exact supported versions and the
[migration guide](../how-to/migrate-archive.md) for the operational procedure.
