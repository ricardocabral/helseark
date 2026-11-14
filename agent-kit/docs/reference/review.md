# Reviewed publication

`prepare_candidate(vault, candidate, *, clock, uuid_factory, reextract=False,
reconciliation=None)` consumes the strict intake reader and baseline validator.
It allocates final logical IDs, revision UUIDs, UTC times and versioned references
once. `clock` and `uuid_factory` are injectable; production defaults are current
UTC and UUIDv4. It creates native FHIR Provenance for compilation by a local actor;
this actor is not a clinician or approver. The accepted source status (`final`,
`current`, etc.) remains distinct from workflow acceptance status.

`render_review(vault, proposal)` returns identity and base, every emitted resource,
changed revisions, preserved omissions, duplicate/contradiction suggestions, source
quotes and page locators, issues and validation coverage. Read original sources
beside all results. Quote consistency does not prove the row association correct.
`record_review(vault, proposal, ReviewDecision(...))` requires explicit human person
confirmation, a local reviewer label, an acceptance decision and an individual
`{code, resourceRef, reason}` for exactly each review/warning issue. No blanket
acknowledgment exists. Errors, failed validation and unresolved identity block.
The label is not a verified identity or a digital signature.

`commit_candidate(vault, proposal, receipt)` is the public mutation boundary.
It revalidates under the existing writer lock and calls the private atomic
publication primitive. It never regenerates resource bytes, timestamps or IDs.
An exact already-accepted proposal returns its original transaction before stale
base checks. Other concurrent changes require fresh preparation and review.

## Noncircular byte inventory

The fixed `proposal.json` inventories final resources, evidence, original and
derived assets, retained source/extraction receipt digests, and three exact
`inputs/*.json` snapshots (candidate metadata, original Bundle and evidence).
Its candidate digest hashes an inventory of the original artifact paths and exact
byte digests. `validation.json` hashes the proposal; `review.json` hashes both.
`change.json` inventories these files and every input snapshot and hashes the
unchanged proposal. It never hashes itself. Reopening verifies all retained bytes
without consulting work directories. Future export, backup and doctor implementations
must preserve this complete closure; those commands are not implemented here.

During preparation/acceptance, the original candidate path is host workflow state
in `PreparedProposal.candidatePath` and `.runtime/prepared/<proposal digest>.json`,
separate from agent packets. Original candidate edits invalidate review. Do not
let an external agent modify this control directory or human decision files.
After publication only accepted snapshots and retained assets are authoritative;
work directories and runtime preparation control can be removed. An exact retry
can use the accepted directory returned by a repeated prepare operation.

## Existing imports and reconciliation

Source bytes detect an existing import within one person, never medical equivalence.
Source-local anchors hash resource role and evidenced source coordinates, quotes
and target pointers. Exact normalized extraction matches reuse the accepted target
before clock/UUID allocation, including a source supplied under another filename.
Distinct source documents keep distinct logical IDs even when values are equal.
Matching analyte/date assertions are flagged for human duplicate/contradiction
review, never silently merged. This finite suggestion rule is not general clinical
matching or diagnosis.

A changed extraction requires user-controlled `reextract=True` (CLI `--reextract`).
Unchanged anchors map to existing IDs; changed anchors require an explicit
reconciliation map from candidate `urn:uuid:...` to an existing same-source
`ResourceRef` (CLI `Type/UUID`) or `None`/JSON null for a new fact. This map is not
read from candidate/source instructions. Omitted old facts are listed and retained.
The new proposal and its exact revision mappings/omissions require human review.
No cancellation cascade or deletion is inferred. Independent sources remain separate;
intentional cross-source clinical correction belongs to the later correction workflow.

This is offline baseline structural/evidence validation, not terminology validation,
full FHIR conformance, OCR, model accuracy, or proof of clinical correctness.
Only synthetic pre-authored candidates are used in deterministic tests.

## Host source selection

New intake packets retain the original person, exact source hashes and confirmed
assignment under `.runtime/intake/<candidateId>.json`, outside agent-writable
packets. Preparation checks this original host selection; editing packet metadata
cannot broaden it or confirm identity. The original context authority remains a
separately held builder value; it is never recovered by hashing a mutable packet.
For an older or independently authored candidate without this host record, the
approved user must supply `authorized_sources=(hash, ...)` or repeat CLI
`candidate prepare ... --source HASH` for exactly the intended sources. This is an
explicit workflow input; never derive it automatically from hostile candidate text.
Final human person confirmation is still mandatory in every review decision.

The CLI reloads review receipts using the original digest recorded separately in
`.runtime/reviews/<proposal digest>.json`. It never treats hashing an edited
receipt file as proof of the original human decision. In-memory callers retain the
returned `ReviewReceipt`. Once accepted, the immutable change inventory supplies
the receipt digest, so all preparation/intake/review runtime control and work
files may be removed without losing the accepted review target. A process failure
between writing a review file and retaining its host digest fails closed; prepare
and review a fresh proposal rather than manufacturing missing host state.

New publication requires a vault initialized with the matching Task6 proposal/input
contracts. Older copied kits/definitions and accepted history remain readable; the
toolkit does not automatically repin or migrate them. An old schema that cannot
represent the new review inventory blocks preparation. Schema migration is a later
workflow; preserve the original vault and its definitions.
