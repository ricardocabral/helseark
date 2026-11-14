# Export one person's records

Select the person explicitly. Export never matches identity from names or source
text. A full-person folder retains that person's entire immutable chain and its
sources, with definitions and pinned interpretive support; other people and work
are excluded.

```sh
helseark --vault ./family export --person UUID --out ../person-export --json
helseark backup verify ../person-export --json
```

A person's intake assignment does not establish disclosure authority for every
page of a PDF. Format 1 has no reviewed derivative/scope receipt, so source-inclusive
person export of a PDF fails SOURCE_SCOPE_REVIEW_REQUIRED. This includes known
mixed-person PDFs and PDFs with unproven scope. No automatic name matching,
redaction or unsafe inference is used. Full household backups preserve originals.
For a source-free exchange, explicitly choose a new selected snapshot:

```sh
helseark --vault ./family export --person UUID --mode selected-current \
  --resource Observation/UUID/_history/REVISION_UUID --no-sources \
  --out ../selected-snapshot --json
helseark backup verify ../selected-snapshot --json
```

Omitting --resource selects all current records. Exact historical references stay
exact. Versionless references resolve at the single captured person head.
Every required local reference is included recursively; unresolved or cross-person
references block export. This may include historical results or Provenance targets
beyond the initial selection. Inspect the final closure before sharing.

This is a **new snapshot**, with a new export ID and declared omissions, never a
truncated accepted chain. It omits original history, unselected revisions, work,
runtime and derived files. --no-sources also omits source/evidence/review envelopes.
It cannot be restored as a reviewed vault; use a full backup for recovery.
Original selected resource bytes are retained under resources/REVISION.json.

collection.json is a derived FHIR R4 collection. Each entry.fullUrl is
urn:uuid:REVISION_UUID. All internal References, including versionless Patient
references, are rewritten to that mapping. Logical IDs, revision IDs, status,
units and Decimal precision remain intact. export.json referenceMap records
person/type/id/versionId/fullUrl plus original-reference-to-fullUrl bindings.
The public portability.fhir_collection(vault, person, resourceRefs, at=Head)
returns this same collection and mapping for offline validator callers. Task10
must consume this boundary rather than reimplementing revision resolution.
Accepted bytes are never rewritten.

Only regular folders are supported. All output paths must be absent and outside
the vault. Verification checks inventory bytes, pinned support, original revision
identity and the derived mapping/closure. Hash inventories are not signatures or
proof of clinical accuracy. A successful export is not evidence of model quality.

See [backup and restore](backup-and-restore.md) for recovery and integrity limits.
