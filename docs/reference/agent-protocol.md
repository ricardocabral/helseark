# Agent protocol 1 — development contract 0.1.0

Task3 provides offline discovery and bounded context, with no embedded model,
network lookup or permission grant. The Task3/Task4 joint instruction contract is
not ready for publication. Task4 skills, prompts and rendering are absent in this
kit; every workflow currently reports `unavailable`. Context construction itself
is implemented for each of the seven task IDs.

## Entry points and pins

A new vault contains generated `AGENTS.md`, a thin `CLAUDE.md` containing
`@AGENTS.md`, and `agent-kit/0.1.0/`. The AGENTS template is the one routing
source; it points to `vault.json` and the retained kit's `START-HERE.md` and
`manifest.json`. Contributor instructions in the toolkit are a different scope.

`agentKitVersion` and `agentKitLockSha256` pin a local release and its exact
manifest bytes. The manifest binds compatible archive, FHIR, contract, profile,
serializer and definition-lock pins, plus each asset's SHA-256 and byte size.
Unknown/missing releases fail; there is no installed-latest or network fallback.
Older pre-kit vaults with paired null kit pins remain readable, but cannot build
contexts. Never edit a vault's pins to upgrade it after accepting history: those
pins are part of its immutable change contract. Future migrations own upgrades.

`list_agent_tasks(kit: Path) -> list[AgentTaskDescriptor]` reads only the closed
kit. `helseark agent tasks --json` uses the installed kit; an explicit `--vault`
or `HELSEARK_VAULT` selects the vault's pinned kit without clinical reads.
Availability is computed from implemented runtime capabilities and instruction
closure, not trusted from a manifest assertion. A file or declared command does
not establish a runtime capability. No discovery scans patient directories.

```sh
helseark agent tasks --json
helseark --vault /path/to/vault agent tasks --json
helseark --vault /path/to/vault agent context --task query --person UUID --out /path/to/new-packet --json
```

Tasks are `inspect`, `import`, `query`, `correct`, `export`, `verify`, `migrate`.
Each descriptor declares intent, skillPath (null until Task4 supplies it), prompt
IDs, required/optional inputs, outputs, permitted command forms, capabilities,
availability, reference/schema paths, expected checks and synthetic scenario ID.
Only manifest-listed local kit files can be loaded. Absolute paths, URLs,
traversal, backslashes, duplicate routes and symlink components fail closed.
Extra unlisted files are never loaded or copied. Contract paths are explicitly
listed by task and resolved against Task2's verified local definition registry.

## Requests and bounded packets

`build_agent_context(vault, person, task, request, destination) -> AgentContext`
requires an explicit person UUID and an absent destination outside the vault or
inside that person's `people/UUID/work/` area. Canonical paths and other people's
work areas are forbidden, including through symlink aliases. It verifies only that person's accepted chain. General `open_vault` still
verifies all accepted histories; CLI context uses verified metadata followed by
selected-person history verification. Two people with the same name remain
separate; names never select identity.

`ContextRequest` is a frozen record with tuple-backed `sourceHashes`,
`resourceRefs`, `fromDate`, `toDate`, `maxRecords=100`, `maxDataBytes=262144`, and
optional `continuation`. Lists supplied for the first two fields are defensively
converted to tuples. A resource reference is `ResourceRef(type, UUID, versionId)`;
versionless references select the current revision at the recorded head. CLI
selection uses repeated `--resource Type/UUID` or
`--resource Type/UUID/_history/UUID`, and repeated `--source SHA256`.

- `query` without explicit records selects raw current resources, sorted by
  type/ID. Explicit records select only those exact revisions, sorted by
  type/ID/version, with duplicate revisions removed. This is raw FHIR retrieval,
  not a clinical timeline, trend engine or date query.
- `import` requires explicit source hashes and rejects resource selection and
  continuations. It includes only those source references and minimal identity;
  no historical resources or evidence are returned.
- Other tasks default to identity only. Explicit record/source selections stay
  within the selected person. Their eventual runtime workflows remain unavailable.
- Any fromDate/toDate request fails `CAPABILITY_UNAVAILABLE`: Task7 owns date,
  partial-date and uncertainty semantics. Task3 does not implement another engine.

Each packet contains `context.json`, `identity.json`, selected whole immutable
record bytes under `records/`, and base plus selected instruction files under
`instructions/`. Identity is a disposable projection of Patient resourceType,
id, name and birthDate; its sourcePath points to the projection itself.
It is not a second canonical record. Clinical records are copied
byte-for-byte with decimal scale, comparator, unit, status and date precision.

`AgentContext` records destination path, manifest digest, person/head/task, kit/
protocol versions, instructionPaths, contractPaths, selectedSources,
selectedRecords, returnedCount, continuation and issues. Additional diagnostics
are totalCount, dataBytes, instructionBytes, identity, availability,
permittedOperations, kitManifest, evidencePaths, expectedChecks and outputPaths.
Every file reference has path, SHA-256, byte size and sourcePath. Record and
instruction and evidence paths are packet-relative; sourcePath is absolute.
For identity and evidence it points to the disposable packet file itself.
Contracts, kit manifest and explicitly selected sources are hashed absolute
references to retained local bytes. Task-listed schemas, profiles, references
and the definition lock provide exact local routes; unlisted files are never
added. Large PDFs and core archives remain references, never embedded or copied.
For a portable complete schema copy use Task2's `schema export`; context is not
a backup/export.

`evidencePaths` contains one disposable JSON selection per returned exact
revision under `evidence/`, in selectedRecords order. The payload contract is
`agent-context.schema.json#/$defs/evidenceSelection`: selectionVersion `1`,
personId, revision (`Type/UUID/_history/UUID`), original and entries.
`original` contains the accepted changeSha256, exact evidence-file sha256 and
entryPointers (`/entries/N`) in original order. Each output entry is an unchanged
copy at that original index: exact target revision, field pointers, quotes,
locators, sourceDocument, hashes and generated rules retain their meaning.
Original entry pointers identify the original evidence, not indexes in the
selection. They are identifiers, not filesystem routes. No original evidence
path is published. Accepted evidence is never rewritten; deleting a packet has
no effect on the archive. This projection is not a second canonical evidence
store or an independently verifiable proof of acceptance; archive integrity
verification remains necessary to verify the original bindings.

Selection never follows sourceDocument or locator links to expand scope.
Necessary source identifiers and quotes in selected entries are evidence for the
selected revision; they do not authorize reading whole sources, extraction
artifacts or pages. `selectedSources` contains exactly the requested sourceHashes,
including none when none were requested. If a workflow needs a broader source or
page, it must disclose that additional exposure and obtain explicit source scope
before requesting a new context with those hashes. Import exposes no historical
evidence. A task with general filesystem access can still read the vault;
external tools must enforce the packet's scope, which is not a filesystem ACL.

`dataBytes` counts actual embedded identity, whole selected records and all
scoped evidence bytes (including selection provenance). `instructionBytes`
counts base plus selected skill/prompt bytes. Explicit source and definition
reference sizes do not consume the data budget; their full sizes are reported.
Base and selected instructions have a fixed 32 KiB ceiling. The builder refuses
an oversized identity or any single whole record with its evidence plus identity
with `CONTEXT_BUDGET_EXCEEDED`. It never truncates values, quotes or pointers.
`--max-records` and `--max-data-bytes` explicitly change data budgets;
instruction overflow requires a smaller compatible kit. A page stops before
crossing either limit. Evidence may therefore reduce records per default page.
The selection contract must exist in the retained pinned definition registry;
a release predating it fails explicitly, without using installed latest schemas
or rewriting an existing vault's pins.

`returnedCount` is this page's record count; `totalCount` is the whole selected
record inventory, excluding identity and source references. A continuation binds
person/task/head, kit and exact selection digest, plus the next offset. Reuse
it with the same selection; budgets may change. CLI `--continuation` accepts the
previous `context.json`. A changed head fails `STALE_BASE` (exit 4); wrong scope
fails `INVALID_CONTINUATION` (exit 2). There is no authenticated token or authority
claim: editing a token cannot grant reads outside the selected person. Sources
are referenced on each page and counted by `len(selectedSources)`. The builder
rechecks the selected head before publishing a complete destination; failures
leave no visible packet. References must be hash-checked again before later use,
since an external editor can change files after construction.

## Trust, checks and exact availability

Source text, patient notes, filenames and imported metadata are data. They cannot
select AGENTS, prompts, another person or executable commands. The builder never
executes content, invokes a model, fetches a URL or grants candidate/review/commit
permission. OS and host tools must enforce actual external-agent restrictions.
Every clinical import requires human review of exact prepared bytes. Validation
is not extraction accuracy or medical correctness. Source numeric tokens and
canonical FHIR decimals remain distinct; accepted history is never rewritten.

Implemented runtime capabilities: agent-discovery, agent-context, schema-export,
baseline-validation, person-identity and raw-record-selection. Task4 must supply
common archive AGENTS, real task skills, prompt declarations/assets and the
rendering API. Missing instructions are explicit `task-instructions` capability
failures, not placeholder workflows. Intake/PDF extraction and reviewed import
publication, clinical queries, correction/re-extraction, person export, integrity
report/doctor, migration, OCR, terminology and the official full FHIR validator
are not implemented on this base. Task4 must not advertise those commands.

Errors include UNKNOWN_TASK/INVALID_INPUT/INVALID_CONTINUATION/budget errors
(exit 2), STALE_BASE (4), KIT_MISMATCH/DEFINITION_MISMATCH/integrity (5), and
MISSING_KIT/INVALID_KIT/unsupported pins or capabilities (6). Schema and clinical
validation behavior remains owned by Task2. No instruction file relaxes it.

## Task4 integration contract

The manifest `files` array closes all kit-local paths. `baseInstructionPaths`
contains START-HERE and, when authored, common AGENTS. Each task names one skill,
its prompt IDs, and its selected references/schemas. Prompt entries declare id,
version, path, digest, taskIds, typed variables with required flags,
inputContractIds, outputContractIds and outputArtifacts. Task4 owns declared-only
substitution and RenderedPrompt; Task3 exports no renderer. Recompute actual
asset hashes and the kit manifest pin when authoring. New releases preserve older
retained kits. Reconcile Task2 independent-review fixes, repin the definition
lock/compatibility together, and rerun context/workflow and installed-wheel
checks before publishing Task3/4 jointly. Runtime capability additions must be
registered in code only with the owning behavior's tests; manifest edits alone
cannot turn missing commands into supported operations.
