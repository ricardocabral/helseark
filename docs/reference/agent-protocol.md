# Agent protocol 1 — development contract 0.1.0

Offline discovery, bounded context and declared-only prompt rendering are
implemented with no embedded model, network lookup or permission grant. Inspect
is routing-only and has no prompt. The other six workflows remain unavailable
until their runtime dependencies exist. Actual external-agent evaluation remains
a separate gate; templates do not establish command support or extraction accuracy.

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
Each descriptor declares intent, skillPath, prompt
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
id, name and birthDate; its original accepted Patient path is retained for
traceability. It is not a second canonical record. Clinical records are copied
byte-for-byte with decimal scale, comparator, unit, status and date precision.

`AgentContext` records destination path, manifest digest, person/head/task, kit/
protocol versions, instructionPaths, contractPaths, selectedSources,
selectedRecords, returnedCount, continuation and issues. Additional diagnostics
are totalCount, dataBytes, instructionBytes, identity, availability,
permittedOperations, kitManifest, evidencePaths, expectedChecks and outputPaths.
Every file reference has path, SHA-256, byte size and sourcePath. Record and
instruction paths are packet-relative; sourcePath is absolute. Contracts, kit
manifest and sources are hashed absolute references to retained local
bytes. Task-listed schemas, profiles, references and the definition lock provide exact
local routes; unlisted files are never added to the context response. Large PDFs and core
archives are references, not embedded or copied. For a portable complete schema
copy use Task2's implemented `schema export`; context is not a backup/export.
Evidence payloads are packet-relative, disposable exact-revision selections.
The closed agent-evidence-selection schema defines selectionVersion 1. Each
includes original evidence path/hash/size and original /entries/N pointers;
these original paths are provenance, not a readable payload authorization. Only
selected revision entries are present. The immutable accepted evidence stays
unchanged. A source hash in evidence does not authorize reading the whole source;
shared sources/pages need a separately confirmed scope. Import exposes no history.

`dataBytes` counts embedded identity, whole selected records and selected evidence;
`instructionBytes` counts base plus selected skill/prompt bytes. Reference sizes
are explicit but do not consume embedded data budget. Base and selected
instructions have a fixed 32 KiB ceiling. The builder refuses an oversized
identity or any single record plus identity with `CONTEXT_BUDGET_EXCEEDED` and an
actionable message. It never truncates clinical values. `--max-records` and
`--max-data-bytes` explicitly change data budgets; instruction overflow requires
a smaller compatible kit. A page stops before crossing either data limit.

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
baseline-validation, person-identity, raw-record-selection and task-instructions.
Common archive AGENTS, selected skills and typed prompt declarations are bundled. Missing instructions are explicit `task-instructions` capability
failures, not placeholder workflows. Intake/PDF extraction and reviewed import
publication, clinical queries, correction/re-extraction, person export, integrity
report/doctor, migration, OCR, terminology and the official full FHIR validator
remain unimplemented and are not advertised as working commands.

Errors include UNKNOWN_TASK/INVALID_INPUT/INVALID_CONTINUATION/budget errors
(exit 2), STALE_BASE (4), KIT_MISMATCH/DEFINITION_MISMATCH/integrity (5), and
MISSING_KIT/INVALID_KIT/unsupported pins or capabilities (6). Schema and clinical
validation behavior remains owned by Task2. No instruction file relaxes it.

## Task4 integration contract

The manifest `files` array closes all kit-local paths. `baseInstructionPaths`
contains START-HERE and common AGENTS. Each task names one skill,
its prompt IDs, and its selected references/schemas. Prompt entries declare id,
version, path, digest, taskIds, typed variables with required flags,
inputContractIds, outputContractIds and outputArtifacts, plus declared skill
identity/version/digest. Markdown reports have an empty outputContractIds list;
no report schema is invented. The renderer implements declared-only substitution and
the exact RenderedPrompt record. Recompute actual
asset hashes and the kit manifest pin when authoring. New releases preserve older
retained kits. Reconcile Task2 independent-review fixes, repin the definition
lock/compatibility together, and rerun context/workflow and installed-wheel
checks before publishing Task3/4 jointly. Runtime capability additions must be
registered in code only with the owning behavior's tests; manifest edits alone
cannot turn missing commands into supported operations.

## Prompt rendering and host handoff

`render_task_prompt(context, promptId, variables)` returns the protocol's frozen
RenderedPrompt record: text, promptId, promptVersion, promptSha256, skillSha256,
kitSha256, inputContractIds and outputContractIds. It verifies the packet against
its retained manifest, definitions, selected person's accepted revisions, evidence,
identity, current head and byte budgets. Changing the packet or advancing its base
requires rebuilding. It loads only manifest-declared instructions; slot values
never trigger file reads, shell commands or expression evaluation.

CLI: `helseark --vault PATH agent render --context PACKET --person UUID --prompt
query-with-evidence --variables SLOTS_JSON --json`. SLOTS_JSON is an explicit host
input file, not an include mechanism inside a slot. The CLI checks the selected
vault/person against the packet before rendering. Provide `source_data` as an
object and `output_directory` as an absolute absent directory. `request` defaults
to an empty string; null is allowed only where the manifest explicitly declares
it. Toolkit selectors are filled from the verified packet. Repeated selectors
must match it. Import/correction human confirmations are separate required
boolean arguments supplied by the host after an explicit human decision; source
assertions cannot supply them. Candidate IDs are explicit host allocations.

Each slot is substituted once as exact JSON. Delimiter characters `<`, `>` and
`&` are Unicode escaped without changing decoded values. Marker-looking source
strings remain literal data. Escaped inline data (including optional user-data
slots) and context data together must fit the selected maxDataBytes. The handoff
reports contextDataBytes, inlineDataBytes and handoffDataBytes. Escaping overhead
counts; reduce inline payloads or explicitly rebuild with a larger budget rather
than silently increasing limits or truncating values. Unknown, missing, unbounded or ill-typed variables,
unknown template markers and incompatible task routes stop rendering.

Context files are immutable inputs. The separately selected fresh output directory
is a host authorization request for disposable artifacts only; rendering creates
no directory and grants no OS permission. Configure the external agent's file/tool
restrictions separately. No accepted-file edit, publication, implicit source read
or network permission is conveyed. Blocked workflows may write only their report
under that output root; missing runtime capabilities and missing human confirmation
are explicit stop reasons. A template never makes an unavailable command available.

Producer provenance has an explicit closed sub-contract `provenanceVersion: 1` in
candidate and evidence envelopes. `status: known` records prompt ID/version/hash,
skill hash and kit version/hash supplied by the renderer. Both envelopes must
agree; known provenance is checked against a retained kit, including task routing.
External producers without genuine kit information record `status: external-unknown`
and a reason. Do not infer a known producer from free-text names. Legacy accepted evidence and retained old candidate contracts without this field
remain unchanged and mean only legacy unspecified provenance. New candidates under
the current contract require it, and their evidence must match. No accepted history
is rewritten or silently upgraded. New kit-produced candidates
copy the supplied provenance into both envelopes. This identifies instructions,
not a proof of extraction accuracy or a human approval.

The release inventory is refreshed by `python scripts/pin_agent_kit.py`. It copies
reference bytes from their authoritative repository paths into the closed kit so
relative Markdown links work in the wheel and retained release. These are exact
release copies, not alternate contracts. Definition-lock bytes are pinned first,
then the manifest pins the lock and all kit bytes; the lock never pins the manifest.
Old vaults retain their own definitions and kit. No latest-install fallback occurs.
Actual agent evaluation is separate from deterministic tests and remains required;
Tasks5–14 own evaluations of their command journeys when implemented.

Retained pre-renderer protocol-1 kits remain readable under their original schemas
and pins. Their contexts omit the later budget fields; selected evidence is still
projected and bounded using their original pinned evidence entry contract. No
installed newer definition is substituted. Those kits have no Task4 prompt routes;
a missing prompt remains incompatible. A retained context contract without explicit
rendering limits cannot render a later typed prompt. Upgrade requires an explicit
future migration; reopening never repins a vault or rewrites accepted history.
