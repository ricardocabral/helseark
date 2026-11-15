# Export one person's records

Select the person explicitly. Export never matches identity from names or source
text. A full-person folder retains that person's entire immutable chain and its
sources, with definitions and pinned interpretive support; other people and work
are excluded. Both full-person and selected-current export block when doctor
finds unknown files, including unlisted files in definitions/ or agent-kit/.
Only explicit pinned support and the verified canonical closure can be copied;
a directory name does not establish scope. Preserve unknown files and resolve
ownership outside the export before retrying; see the backup guide's unknown-material
policy.

```sh
helseark --vault ./family export --person UUID --out ./person-export --json
helseark backup verify ./person-export --json
```

A person's intake assignment does not establish disclosure authority for every
page of a PDF. Ordinary source-inclusive PDF export still fails
`SOURCE_SCOPE_REVIEW_REQUIRED`, including known mixed-person PDFs and PDFs whose
scope is unproven. A model, prompt `source_scope_confirmed`, `source_data`, source
text or edited packet cannot grant disclosure. Full household backups retain
originals. A human may choose one of the explicit reviewed routes below.

For a source-free exchange, explicitly choose a new selected snapshot:

```sh
helseark --vault ./family export --person UUID --mode selected-current \
  --resource Observation/UUID/_history/REVISION_UUID --no-sources \
  --out ./selected-snapshot --json
helseark backup verify ./selected-snapshot --json
```

Omitting --resource selects all current records. Exact historical references stay
exact. Versionless references resolve at the single captured person head.
Every required local reference is included recursively; unresolved or cross-person
references block export. This may include historical results or Provenance targets
beyond the initial selection. Inspect the final closure before sharing.

**Resource selection does not narrow original-source scope.** In the current
source-inclusive `selected-current` mode, the resource closure above is separate
from the source inventory: export includes **all accepted source assets and
retained source/extraction receipts for the selected person's entire accepted
history**, including unrelated imports and older revisions. Selecting one
Observation can therefore include other accepted reports or CSV files that are
not dependencies of that Observation. Read every `originalSources` and
`sourceFiles` entry in `export-plan`, not just `referenceMap`, before deciding
what to share. Reviewed original inclusion binds this complete inventory;
derivative planning also inventories it and declares original omissions. There
is no selected-dependency-only source option. Choose `--no-sources` for an
explicit source-free exchange, or review the complete original inventory or
supplied derivative route below; never silently prune sources or reuse approval
for a narrower inventory. Full-person recovery explicitly retains the complete
accepted chain and exact original evidence. Selected snapshots remain exchange
artifacts, even when they include every original source.

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
Verification requires exactly the original reference key set and checks every
binding against its unique mapped target and the derived resource, for exact and
versionless references alike. Missing, extra, contradictory or dangling bindings
fail verification even when all file digests match. Accepted bytes are never rewritten.

Only regular folders are supported. All output paths must be absent and outside
the vault. Verification checks inventory bytes, pinned support, original revision
identity and the derived mapping/closure. Hash inventories are not signatures or
proof of clinical accuracy. A successful export is not evidence of model quality.

See [backup and restore](backup-and-restore.md) for recovery and integrity limits.

## Review exact original inclusion

Capture a plan, read **all** of `plan.json`, inspect the original sources and
retained artifacts listed there, then supply a decision over the returned digest:

```sh
helseark --vault ./family export-plan --person UUID --mode full-person \
  --out ./disclosure-plan --json
# Human inspects plan.json and exact source bytes; writes decision.json below.
helseark --vault ./family export-review --plan ./disclosure-plan \
  --decision ./decision.json --json
helseark --vault ./family export --person UUID --mode full-person \
  --review ./disclosure-plan --out ./reviewed-export --json
helseark backup verify ./reviewed-export --json
```

The human-authored decision has exactly these fields. Replace the digest with
`export-plan`'s `planSha256`, and supply your own label and reason. This example
is a contract illustration, **not an approval**:

```json
{
  "format": "helseark-source-decision-1",
  "planSha256": "REPLACE_WITH_EXACT_DISPLAYED_SHA256",
  "humanReviewed": true,
  "confirmedPerson": true,
  "acknowledgedDisclosure": true,
  "reviewer": {"kind": "local-user", "label": "YOUR LOCAL LABEL"},
  "reason": "YOUR HUMAN REASON FOR THIS EXACT DISCLOSURE"
}
```

Acknowledgment applies to the complete plan: selected person, captured Head,
exact selection/reference closure, hashes **and sizes** of original sources and
retained source receipts/extraction artifacts, original inclusion/omission,
derivative mapping and limitations. Including exact originals may disclose
excluded people on any page or in retained text. The export README prominently
warns of this. Original vaults, household backups, earlier exports and unknown
external copies remain. This flow does not delete or sanitize them.

The receipt is host-recorded under `.runtime/source-disclosures/`; an edited,
stale or foreign plan/receipt fails. Losing runtime controls requires a fresh
plan and human review. Exported receipts document a past disclosure and cannot
authorize another export on a different host. Local labels are **not authenticated
identities**. Hashes are not signatures or protection against a malicious rewrite
of the entire host state. Software cannot prove that a human inspected a file;
review flags are explicit human assertions. Agents must not generate decisions.
Qualification fixtures use `reviewer.kind: synthetic-test` and conspicuous
SYNTHETIC labels/reasons; these are never real-user approvals.

## Deliver a supplied reviewed derivative

Supply individual files yourself; Helseark does no OCR, redaction, patient
recognition, clinical correction or source overwrite. Use a selected exchange
snapshot, with a JSON list such as:

```json
[{
  "sourceSha256": "EXACT_ORIGINAL_SOURCE_SHA256",
  "path": "./manually-prepared-derivative.pdf",
  "mediaType": "application/pdf",
  "mapping": "YOUR ORIGINAL PAGE/REGION TO DERIVATIVE PAGE MAPPING",
  "omissions": "YOUR EXPLICIT REMOVED CONTENT AND REMAINING LIMITATIONS"
}]
```

Paths resolve from the command working directory. Only those individual regular
files are read, up to 100 MiB per file. Directories, symlinks (including any
ancestor), and `..` traversal fail with `UNSAFE_PATH`; use a path without symlink
aliases or traversal. The same boundary applies to the plan directory and captured
derivative rereads. Oversized files fail with `SOURCE_TOO_LARGE`; files changed
during a read fail with `SOURCE_CHANGED`. No failed capture publishes a plan.
Derivative-list and disclosure-decision JSON inputs use the same no-follow
regular-file boundary, with a separate 64 MiB limit. Plan and receipt rereads
use that 64 MiB limit as well.
Map every original PDF explicitly. Multiple originals may map to one combined
derivative, and one original may have multiple mappings. Every mapping and omission
is retained; identical bytes are stored once in both the plan and export. Entries
sharing a blob must agree on its SHA-256, size and declared media type, otherwise
`REVIEW_MISMATCH` blocks capture/export (`INTEGRITY` during portable verification).
Media type and clinical equivalence remain declarations, not content recognition.
Other original source artifacts are omitted and remain inventoried by hash/size.

```sh
helseark --vault ./family export-plan --person UUID --mode selected-current \
  --resource Observation/UUID/_history/REVISION_UUID \
  --derivatives ./derivatives.json --out ./derivative-plan --json
# Human reviews this plan and the captured derivative bytes, then writes a decision.
helseark --vault ./family export-review --plan ./derivative-plan \
  --decision ./derivative-decision.json --json
helseark --vault ./family export --person UUID --mode selected-current \
  --resource Observation/UUID/_history/REVISION_UUID \
  --review ./derivative-plan --out ./derivative-exchange --json
```

Repeat the **same selection** at export. A changed person, Head, selection,
original hash/size, derivative byte or receipt requires a new plan/review.
`derivatives/HASH/blob` contains the exact supplied bytes. `sourceDisclosure` in
`export.json` retains the original hash relation, human mapping, omissions,
review and reason. All original sources, extraction artifacts and source receipts
are absent from this derivative snapshot. Original selected FHIR resource bytes
and their source hash references remain unchanged: the derivative **does not
satisfy original evidence references or source quotes**. The manifest and README
state that original-source evidence verification and full-history recovery are
unsupported. Obtain originals separately if those are required; no substituted
quotes or rewritten evidence are produced. Redaction is never claimed reversible
or medically lossless. This snapshot cannot be restored as a vault. A derivative
cannot replace original evidence in a full-person recovery chain.

Reviewed exports use `helseark-export-2`; ordinary exports/backups remain format 1.
Readers dispatch strictly by format. Older readers reject format 2; use this
compatible reader to verify/restore reviewed full-person exports. Existing
accepted history, definition/kit pins and format-1 bundles remain unchanged.
