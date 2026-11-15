# Python API reference

For toolkit 0.1.2 / kit 0.1.18. Import public functions from their owning
modules; `helseark.__init__` does not re-export the entire API. Paths are pathlib
Path, IDs are validated UUID strings, and decoded FHIR trees use Decimal for JSON
fractions. Types and immutable workflow dataclasses live in `helseark.contracts`.
Do not call underscore-prefixed storage primitives to bypass review.

## Storage and exact JSON

`helseark.serialization` exposes `encode_json(value) -> bytes`,
`decode_json(data: bytes)` and `hash_bytes(data: bytes) -> str`. Encoding sorts
object keys, retains numeric scale/array order and rejects duplicate keys,
nonfinite numbers, malformed UTF-8 and excessive numeric/depth limits. Use it
rather than converting clinical decimals to float.

`helseark.archive` exposes:

| Function | Contract |
|---|---|
| `init_vault(root, config=None) -> Vault` | Absent destination; default pinned installed definitions and kit; explicit config must match bundled bytes |
| `open_vault(root) -> Vault` | Verify versions/definitions and accepted histories; no migration-on-open |
| `open_definitions(root) -> Vault` | Open local definitions without clinical graph scan |
| `add_person(vault, PersonDraft(displayName, birthDate=None, note=None), *, clock=None, uuid_factory=None) -> str` | Narrow self-reported Patient genesis; no arbitrary clinical-write constructor |
| `head(vault, person) -> Head or None` | Selected-person chain tip |
| `resolve(vault, person, ResourceRef(resourceType, id, versionId=None), at=None)` | Current or exact native FHIR revision in selected snapshot |
| `iter_current(vault, person, at=None)` | Iterator of current native resources |
| `commit_candidate(vault, proposal, receipt) -> CommitResult` | Verify exact bytes/base/review and publish once; retry returns already-accepted |
| `doctor(vault) -> IntegrityReport` | Counts, safe issues and recovery paths; no repair |

A small executable example (run in a clean directory):

```python
from pathlib import Path
from decimal import Decimal
from helseark.archive import init_vault, add_person, resolve
from helseark.contracts import PersonDraft, ResourceRef
from helseark.serialization import decode_json, encode_json
vault = init_vault(Path('api-vault'))
person = add_person(vault, PersonDraft('Alex Synthetic'))
assert resolve(vault, person, ResourceRef('Patient', person))['id'] == person
assert str(decode_json(encode_json({'value': Decimal('0.050')}))['value']) == '0.050'
```

## Intake, validation and review

`helseark.intake.add_source(vault, person, source) -> SourceReceipt` retains
within-person source bytes; `build_packet(vault, source, destination, *, identityConfirmed=False, outputDirectory=None,
limits=IntakeLimits()) -> ImportPacket` builds the actual
external-agent handoff and returns host authority. `read_candidate(vault,
candidateDirectory, *, person=None) -> Candidate` performs bounded safe reads.
`prepare_candidate(vault, candidate, *, clock=None, uuid_factory=None,
reextract=False, reconciliation=None, authorized_sources=None,
amendment_target=None, amendment_reason=None) -> PreparedProposal`
compiles final bytes. Authorized sources and reconciliation come from host/user
control, never hostile candidate metadata. A map uses candidate urn keys and
ResourceRef values or None for new facts.

`helseark.validation` provides `load_definition_registry(vault)`,
`schema_packet(vault, resourceTypes, destination) -> Path`,
`validate_candidate(vault, candidate) -> ValidationReport` and
`validate_proposal(vault, proposalDirectory) -> ValidationReport`. Coverage families
are passed/failed/not-checked; terminology and full FHIR remain not-checked here.
Registry identifiers resolve locally or fail; no network fallback.

`helseark.review` provides `read_prepared(vault, directory, *, candidate_path=None,
base=None)`, `render_review(vault, proposal) -> ReviewView`,
`record_review(vault, proposal, decision, *, clock=None) -> ReviewReceipt`, and
`read_receipt(vault, proposal) -> ReviewReceipt`. `ReviewDecision` has
confirmedPerson, decision, acknowledgedIssues and reviewerLabel. Each displayed issue has an issueId bound to the exact validation report.
Acknowledgments select code/resourceRef/issueId/reason individually, including
unchecked coverage; legacy three-field input must select one unambiguous issue. The
receipt is a local consistency record, not authenticated human identity. Preserve
the returned receipt/host control through publication; do not synthesize authority
by hashing a mutable file. See [review contract](review.md).

## Query and portability

`helseark.query.observations(vault, person, filters: ObservationFilter, *, at=None)`
yields ObservationRow; filters default to no code/label/date restrictions and
includeInvalidated=False. `timeline(vault, person, *, at=None)` yields TimelineRow.
`parse_reference(text)` produces ResourceRef. Query results preserve native value
shapes, effective precision, method/range/status and exact evidence; consume the
iterator to observe errors. No database is required.

`helseark.portability.backup(vault, destination, *, includeWork=False)` and
`export_person(vault, person, destination, selection: ExportSelection, *, review=None)` return
ExportReceipt. ExportSelection requires mode (full-person or selected-current), with defaults
resourceRefs=() and includeSources=True. `verify_export(bundle) -> IntegrityReport` reports failed
verification as issues; inspect them. `restore(bundle, destination) -> Vault`
verifies and publishes an absent destination. `fhir_collection(vault, person,
resourceRefs=(), *, at=None)` returns a collection and exact-reference mapping
for supported graph closure, not an independent canonical store. See
[exports](../how-to/export-records.md) for PDF restrictions and snapshot omissions.

## Agent context and rendering

`helseark.agent_context.list_agent_tasks(kit)` reads task descriptors without
clinical discovery. `build_agent_context(vault, person, task, request:
ContextRequest, destination)` returns AgentContext with trustedContextSha256.
ContextRequest defaults to empty sourceHashes/resourceRefs, no dates, maxRecords=100,
maxDataBytes=262144 and no continuation. Keep the construction digest outside
agent-writable files. `read_agent_context(path)` reloads but grants no authority.
`render_task_prompt(context, promptId, variables, *, trusted_context_sha256)`
verifies the host digest and returns a rendered handoff; it does not run a model.
`document(value)` converts dataclasses to JSON-compatible structures preserving
Decimal. Full typed slots and file-selection rules are in [agent protocol](agent-protocol.md).

## Corrections, family removal, migration and disclosure

`helseark.intake.start_correction(vault, person, target: ResourceRef, reason) -> Candidate`
starts a current-base draft; it never commits. The explicit amendment keywords to
prepare_candidate require a new retained source, target and human reason.

`helseark.portability` exposes `plan_person_erasure(vault, person, quarantineDestination)`,
`apply_person_erasure(vault, plan, approvedDigest)`, `restore_person_erasure(vault,
quarantine, approvedDigest)` and `read_erasure_plan(path)`. Plans bind selected paths,
heads, file hashes and retained shared metadata. Native no-replace recovery preserves
actual partial-move locations. No purge or secure erasure API is provided.

`helseark.migrations` exposes `open_migration_source(root, *, allowTestFixture=False)`,
`plan_migration(vault, target: VersionSet)`, `apply_migration(vault, plan, destination,
*, reviewedPlanSha256=None, resume=False)`, `read_migration_plan(path)` and
`plan_fhir_migration(vault, version)`. See [compatibility](compatibility.md) for the
closed dispatch, receipt contract and unsupported FHIR conversion. These retain
source history and pins and publish a separate vault.

`helseark.source_disclosure.prepare_disclosure(vault, person, selection, destination,
*, derivatives=()) -> Path` and `record_disclosure(vault, folder, decision) -> Path`
prepare and record human disclosure authority. Supply the resulting plan folder as
export_person's review keyword. See [export](../how-to/export-records.md) for exact
original/derivative decisions, bounded inventories and no-clobber semantics.

## Errors

Domain functions raise `ArchiveError` with code, safeMessage and details; reports
may also contain Issue records. A successful function returning a report requires
inspection of issues/coverage. Raw caller filesystem failures can raise OSError;
the CLI maps those to safe IO_ERROR. See [CLI error recovery](cli.md#errors-and-recovery).
## Structured intake, history and derived output

| Owning module / function | Contract |
|---|---|
| `adapters.fhir_r4.import_fhir_r4(source, person, mapping: IdentityMapping) -> Candidate` | Explicit assignment, retained full source, supported profile graph and coverage; no publication |
| `adapters.csv_metrics.import_metrics_csv(source, person, mapping: CsvMetricMapping) -> Candidate` | Explicit numeric CSV dialect, columns, units, decimal/time handling; no inferred codes |
| `query.history(vault, person, kinds, at=None)` | Native assertions for selected kinds with status, uncertainty and evidence |
| `adapters.ocr.extract_ocr(source, config: OcrConfig) -> ExtractionArtifact` | Optional pinned local macOS execution, derivatives and transforms; uncertain text |
| `presentation.render_static_report(vault, person, destination) -> Path` | Fresh HTML/CSV/SVG snapshot with citations; accepted bytes unchanged |
| `fhir_validator.validate_with_official_tool(proposal, config: ValidatorConfig or Path or None, *, vault) -> ValidationReport` | Explicit pinned offline execution; records host authority and coverage; never accepts |
| `fhir_validator.load_validator_config(path) -> ValidatorConfig` | Bounded host configuration, no downloads |

IdentityMapping and CsvMetricMapping live in their adapter modules; OcrConfig is
defined in adapters.ocr, and ValidatorConfig in contracts. Refer to [structured intake](../how-to/import-structured-data.md),
[OCR](../how-to/run-ocr.md) and [validator setup](../how-to/run-offline-validator.md)
for required local inputs and qualification limits. A copied/edited candidate,
report or prompt cannot establish source or execution authority.
