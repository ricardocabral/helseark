# Reviewed publication

`prepare_candidate(vault, candidate, *, clock, uuid_factory, reextract=False,
reconciliation=None)` consumes the strict intake reader and baseline validator.
It allocates final logical IDs, revision UUIDs, UTC times and versioned references
once. `clock` and `uuid_factory` are injectable; production defaults are current
UTC and UUIDv4. It creates native FHIR Provenance for compilation by a local actor;
this actor is not a clinician or approver. The accepted source status (`final`,
`current`, etc.) remains distinct from workflow acceptance status.

`render_review(vault, proposal)` returns identity and base, every emitted resource,
changed revisions with previous resources/evidence, preserved omitted resources,
paired old/new duplicate/contradiction comparisons with both sources, source
quotes and page locators, issues and validation coverage. Read original sources
beside all results. Quote consistency does not prove the row association correct.
`record_review(vault, proposal, ReviewDecision(...))` requires explicit human person
confirmation, a local reviewer label, an acceptance decision and an individual
`{issueId, code, resourceRef, reason}` for exactly each displayed review/warning
issue, including each unchecked validation family. No blanket
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
without consulting work directories. Export, backup and doctor preserve this complete retained closure without
consulting mutable work or runtime caches.

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


## Exact issue decisions and historical compatibility

New receipts use the independently versioned review contract `0.1.1` from
`schemas/0.1.1/review.schema.json`. Other archive envelopes remain `0.1.0`.
New publication requires this pinned schema; an older vault must not be silently
repinned. Its accepted history remains readable with its original definitions.

The displayed `issueId` hashes `helseark-json-1` encoding of
`{version: "exact-issue-v1", validationSha256: SHA256(validation.json), issue: ISSUE}`.
ISSUE contains code, severity, pointer, resourceRef and message. This binds the
selection to the original report, before any reference rewriting or display
sorting. A changed report requires fresh review. The view collapses truly
identical five-field issues into one explicit limitation; different messages,
pointers, resources or severities remain separate. It includes one
`VALIDATION_NOT_CHECKED` limitation per unchecked family, with its reason and
`/coverage/FAMILY` pointer (JSON Pointer escaped). Acknowledgment records awareness
of that gap; it does not turn an unchecked family into a passed check.

The original `ReviewDecision` outer shape is unchanged. Three-field acknowledgment
inputs remain supported only when code/resourceRef selects exactly one displayed
required issue; ambiguous input fails and requires the displayed issueId.
No reason, person confirmation or missing selection is generated. New receipts
always retain exact issueIds. Unknown, extra, duplicate, missing or mismatched
selections fail. Errors and unresolved identity remain blocking.

Historical `0.1.0` receipts retain their original bytes and code/resourceRef
semantics. Accepted views label these `legacy-code-resourceRef`: their inventory
proves the retained decision bytes, **not individual acknowledgment of distinct
issues sharing that key or unchecked coverage**. Reading or retrying an already
accepted transaction does not reapprove it. An unaccepted old receipt cannot
publish; the human must review again to create a `0.1.1` receipt. New receipts are
verified against retained validation after all work/runtime directories are gone.

## Combined clinical foundation release

Toolkit 0.1.2 initializes new vaults with kit 0.1.15 and profile-set 0.2.0. This combines selected-person
bounded candidate reads, original host-bound source/extraction read receipts and
repeated prompt-slot byte accounting with exact issue review and per-call verified
query snapshots. Import skill 0.1.6 retains qualitative attribution guidance;
extract-report prompt 0.1.3 retains the explicit extraction read contract. Query
skill and prompt 0.1.1 describe accepted current/as-of facts and evidence.

Review receipts dispatch independently by contract: new receipts use 0.1.1,
retained accepted 0.1.0 receipts remain readable with their stated limitations.
Other envelopes remain 0.1.0. Existing toolkit 0.1.1 archives, original accepted
receipts, schemas and copied kits keep their original hashes; opening or querying
an old vault does not repin it. A new combined kit version is necessary because
earlier branches used the same kit version for different byte inventories.

The standalone synthetic installed qualification is
`tests/qualify_clinical_integration_installed.py`: it exercises public CLI intake,
validation, preparation, individually acknowledged fixture review, publication,
query, explicit re-extraction, exact historical report children and retry after
work/runtime removal. It invokes no model and establishes no extraction accuracy
or clinical approval. Independent combined-artifact review and remote CI remain
release gates. Backup/export and broader corrections remain separate tasks.

## Optional official validation before review

`validate proposal --official-config PATH` replaces only the unreviewed
`validation.json`. The exact OperationOutcome, count summary, package/profile
pins and shared revision/fullUrl mapping remain in `officialRun`. The proposal
never hashes this report; human review hashes both unchanged proposal and report.
Review/commit recheck baseline/source scope and the derived context binding,
without rerunning Java or changing elapsed time. Existing reports with no
`officialRun` preserve their original byte representation. A requested full tool
that is absent blocks; required terminology blocks in the qualified `-tx n/a`
mode. See [offline validator](../how-to/run-offline-validator.md).

## Original official-execution authority

A pending report is compared with its independently retained host execution
checkpoint before review or commit. The checkpoint binds the entire report,
outcome, original coverage, effective command/environment, complete selected Java
runtime and other inputs, source inventory, person, vault, proposal and base, and
required terminology policy. Starting another request supersedes the previous
checkpoint once its exact authorized pending proposal is resolved, before
configuration loading, baseline checks or runtime checks. Missing/invalid
configuration leaves an explicit failed request without a configuration digest.
Render, review and commit reject the previous result until a fresh actual
successful execution. Copied or mismatched paths cannot revoke another pending
proposal, and accepted history remains immutable. Partial or missing host state fails
closed; mutable producer fields, report hashes or a `change.json` pathname cannot
create authority.

Human `review.json` retains the checked `officialValidationAuthority`; the ordinary
immutable change inventory binds that receipt. Work/runtime controls may then be
removed without losing the original binding. Accepted legacy receipts without it
remain readable under their unchanged schema pins, with explicit unattested
coverage in readonly review. Unaccepted legacy workflows require fresh preparation
and an actual tool rerun where compatible schemas support it. No automatic repin,
retrospective attestation or general clinical-correctness claim occurs.

Reconciliation compares complete baseline family identities, multiplicities,
results and reasons. It rejects omissions, duplicates and invented passing
families, including `medical-diagnosis`; it never fills missing limitations from
a fresh report for display. Only authenticated official `full-fhir`/`terminology`
results replace those two baseline families. Host execution authority is a
separate requirement and does not make incorrect reconciliation acceptable.

New official reports use the separately pinned 0.1.1 validation schema. The 0.1.0 schemas and existing vault pins stay unchanged. Exact-issue 0.1.1 human receipts retain the execution binding as well as individual acknowledgments.
