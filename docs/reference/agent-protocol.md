# Agent protocol 1 — development contract 0.1.0

Offline discovery, bounded context and declared-only prompt rendering are
implemented with no embedded model, network lookup or permission grant. Inspect
is routing-only and has no prompt. Query and human-controlled reviewed imports are implemented; bounded structured intake, native history, person export, reviewed source disclosure, integrity checks and static presentation are implemented. Correction and migration remain unavailable. Actual external-agent evaluation remains
a separate gate; templates do not establish command support or extraction accuracy.

## Entry points and pins

A new vault contains generated `AGENTS.md`, a thin `CLAUDE.md` containing
`@AGENTS.md`, and its explicitly pinned agent-kit directory (current new-vault kit `0.1.9`). The AGENTS template is the one routing
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
`agent-context.schema.json#/$defs/evidenceSelection`: selectionVersion `2`,
personId, revision (`Type/UUID/_history/UUID`), original, entries and
entrySelections. Version 1 is no longer emitted or accepted by this selector.
`original` contains the accepted changeSha256, exact evidence-file sha256 and
entryPointers (`/entries/N`) in original order. The three arrays `entries`,
`entrySelections` and `original.entryPointers` have equal lengths and correspond
positionally. Every original entry targeting the exact revision is represented;
none is silently dropped, including duplicate entries and multi-field targets.
Indexes refer to the original array, never the shorter selection. Each
entrySelections item binds `originalEntrySha256 = SHA256(encode_json(original
entry))` and one mode:

- `metadata-bound`: generated/user-entry metadata is represented by kind and
  the unchanged target (or the original legacy resourceRef/pointer pair).
  Arbitrary rule/value prose, including identity notes, is withheld and bound
  through originalEntrySha256. The selected record retains its actual values;
  this projection is not a canonical evidence envelope. No quoteSpan is added.
  Explicit source scope does not authorize unrelated non-source metadata.
- `whole-value`: a source entry contains only kind, target, sourceSha256,
  sourceDocument and quote. The original target and all its pointers are intact.
  `quoteSpan: {start, end}` indexes Unicode characters in the original quote,
  zero-based with exclusive end. Only surrounding ASCII space/tab/CR/LF can be
  removed. The quote must support **every** targeted scalar leaf by literal
  equality, or by a complete exact quantity token. No substring search, prose
  interpretation, fuzzy matching, date reduction, unit conversion or numeric
  normalization is used. The only reference-name binding is an explicit
  subject pointing to the selected Patient plus exact identity name.text.
- `explicit-source`: if this entry's sourceSha256 was explicitly requested, the
  entire original entry is copied unchanged. This can expose unrelated source
  content. Larger budgets, another source, or selecting a referenced record do
  not authorize it. This mode records the request; it does not authenticate
  whether a caller obtained human permission.

For quantity value/unit/comparator leaves, the quote must contain the complete
selected quantity: exact comparator (including absence), exact fixed-point
number with preserved scale (dot or decimal comma), then the exact unit. Missing
or altered qualifiers, precision or units fail. All pointers of a shared target
must pass. An unknown source transformation also fails narrow selection. Exact
partial dates remain exact; a longer clock passage cannot be cropped into a
partial date. These mechanical checks establish text consistency and disclosure
bounds, not medical accuracy or correctness of the original field mapping.

Unrestricted locator, extraction parameters and transformation descriptions can
carry broader source text too. In whole-value mode those original metadata are
bound by the original entry digest rather than published. The original locator
still locates the **original** quote; quoteSpan is relative to that quote, never
an edited locator or a claim that the source was rewritten. A consumer needing
that metadata must use a trusted internal verifier or request explicit source
scope. This deliberate metadata projection is not a complete canonical evidence
envelope. Entries in explicit-source mode retain original metadata and exact
numbers; accepted originals are never changed.

An ambiguous/broader quotation, unsupported mapping, empty target container or
unsafe required entry fails the entire build with `EVIDENCE_SCOPE_REQUIRED`.
There is no partial output or fallback that discards support. The safe error includes a nonclinical mechanicalReason (unsupported transformation
or whole-value/complete-quantity requirement) and names the selected revision, original entry pointer and required sourceSha256,
but never the quote. It explains that requesting this hash exposes the whole
source, possibly including unrelated records or people. A caller must explain
that exposure and obtain explicit approval before resubmitting with that hash,
or select other records. Arbitrary prose, shared rows, negation, repeated text
and reduced date precision are deliberately not automatically separable.
Whitespace-only sub-selection is supported; general redaction is not.

No original evidence path is published. Accepted evidence is immutable;
deleting a packet has no effect on the archive. SourceDocument/digest metadata
is provenance, not permission to read whole sources, extraction artifacts or
pages. `selectedSources` is exactly the explicit deduplicated sourceHashes.
Import exposes no historical evidence. A packet is not a filesystem ACL.

`select_revision_evidence` in `helseark.agent_context` is the single selection
owner for builders and downstream consumers. Its inputs are the selected person,
accepted resource inventory entry, exact original evidence bytes, accepted Head
and change document, exact decoded resource, retained DefinitionRegistry, and
keyword-only packet identity and explicit source_hashes. It returns canonical
v2 selection bytes. A trusted consumer first verifies the selected person's
accepted history and exact change/resource/evidence hashes, pinned definitions,
identity, head/task/request scope and safe file routes; it then recomputes this
selection and compares **bytes**, enforcing complete original index ordering,
quote transformation, metadata projection and explicit source authorization.
It must not maintain a duplicate selector or treat self-declared hashes/schema
validity as proof of original binding or completeness. Original evidence may be
read internally for verification; neither it nor its route goes to the agent.
The renderer performs this recomputation internally against verified original
selected-person bytes. It rejects missing/tampered projections, redirected paths,
stale snapshots, omitted entries and fabricated/rehashed selections. The standalone
agent-evidence-selection schema aliases this same v2 definition; it is not a
second evidence envelope. Producer instruction provenance remains in immutable
accepted evidence and is verified internally, not added to narrow quotations.
Historical kits remain readable through their retained contracts; a kit lacking
the v2 selection definition cannot build a new selection or render it. No pins
or accepted history are upgraded implicitly. Independent combined review and
actual model evaluation remain required.

`dataBytes` counts actual embedded identity, whole selected records and all
scoped evidence bytes (including selection provenance), plus any explicitly selected
retained extraction bytes. See [intake extraction read receipts](intake.md#selected-extraction-read-receipts-kit-012). `instructionBytes`
counts base plus selected skill/prompt bytes. Explicit source and definition
reference sizes do not consume the data budget; their full sizes are reported.
Selected extraction read receipts are an exception: their entire retained byte
size consumes data budget in addition to every escaped inline occurrence.
Base and selected instructions have a fixed 32 KiB ceiling. The builder refuses
an oversized identity or any single whole record with its evidence plus identity
with `CONTEXT_BUDGET_EXCEEDED`. It never truncates clinical values or pointers; quote selection follows only the explicit rules above.
`--max-records` and `--max-data-bytes` explicitly change data budgets;
instruction overflow requires a smaller compatible kit. A page stops before
crossing either limit. Evidence may therefore reduce records per default page.
The selection contract must exist in the retained pinned definition registry;
a retained release lacking the v2 selection contract fails explicitly, without using installed latest schemas
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
baseline-validation, person-identity, raw-record-selection, task-instructions,
pdf-intake, candidate-read, reviewed-publication, clinical-query, person-export
, reviewed-source-disclosure, fhir-r4-import and csv-metrics-import. Runtime discovery derives availability from these actual
implementations; instruction presence alone does not enable a workflow.
Reviewed publication is human-controlled. Correction, migration, terminology and
the official validator remain unavailable. Optional OCR is operator-configured;
static reports are host commands, never agent publication authority.
[Local OCR](../how-to/run-ocr.md) is an explicit optional host intake step; task
availability never implies native tools/models are installed or accuracy is proven.
[Portability](../how-to/backup-and-restore.md) supplies doctor/backup/restore;
[export](../how-to/export-records.md) supplies selected-person snapshots with
explicit reference mapping and a conservative PDF source-scope gate. Agent reports
remain report-only and do not grant publication/disclosure/restore permission.
No model evaluation success is inferred from runtime availability.

Errors include EVIDENCE_SCOPE_REQUIRED (default integrity/blocked exit 5),
UNKNOWN_TASK/INVALID_INPUT/INVALID_CONTINUATION/budget errors
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

Rendering requires host-retained construction authority outside editable packet
files. `build_agent_context` keeps `trustedContextSha256` on its returned frozen
in-memory AgentContext. This is SHA256 of `encode_json(document(context))`, covering
the complete constructed metadata: vault/kit routes, person, accepted head, task,
exact selected revisions/sources, limits, sizes/hashes, counts and continuation.
The field is **never serialized in context.json** or `document(context)`. Retain
that original builder object in the host and use the original three-argument
renderer API, or retain its digest separately and pass `trusted_context_sha256=`.
The builder's verified request determines the resulting selection; an edited
packet cannot replace that host decision. The renderer also verifies original
bytes/projections and the current accepted head, including a final freshness check.

`read_agent_context(path)` only decodes untrusted metadata and returns no authority.
Rendering that result without an independently retained digest fails
`CONTEXT_AUTHORITY_REQUIRED` (exit 2). An authority field inserted in context.json
is rejected. Another digest in an editable packet, a recomputed digest of files at
render time, or a source-supplied digest cannot authorize the packet. Altered
sources, removed/swapped revisions, counts, limits and continuation fail
`CONTEXT_MISMATCH` (exit 5), even if all newly named source bytes are genuine.

For a process boundary, the CLI `agent context --json` returns the metadata plus
`trustedContextSha256` **on stdout only**. The plain-text response prints it too.
The trusted caller captures this response directly from the builder invocation it
made with explicit person/task/request, retains the digest in its own session or
host-managed job state, and passes it via `agent render --trusted-context-sha256`.
Do not let the external agent replace that argument from packet files or request
an automatic wider rebuild. No receipt cache or additional clinical store is
created. Losing the host digest requires a new explicit build, not trusting a
packet's self-report. A digest establishes continuity with that construction; it
is neither a signature nor authentication of the operator or human source consent.

Task5 intake consumer contract: after explicit person/source selection, call the
same `build_agent_context(..., 'import', ContextRequest(sourceHashes=(...)), ...)`
and retain its original result/digest in the intake host. Pass that result to
`render_task_prompt`, or on reload pass the retained digest as the keyword/CLI
argument above. Keep host output/candidate allocations and human confirmation
arguments separate from extracted source data. If persisting job state, protect
its authority through the host's actual trust boundary; a second agent-editable
work file is not trusted job state. Do not load authority from intake packet JSON,
assert authenticated human review, add sources after EVIDENCE_SCOPE_REQUIRED, or
rewrite accepted bytes. Later review of prepared clinical bytes remains mandatory.
Offline hosts can carry the digest separately with the retained packet/definitions;
plain files remain readable and portable under their existing path/reference
contract. This handoff adds no OS ACL, model runtime or network dependency.


`render_task_prompt(context, promptId, variables, *, trusted_context_sha256=None)` returns the protocol's frozen
RenderedPrompt record: text, promptId, promptVersion, promptSha256, skillSha256,
kitSha256, inputContractIds and outputContractIds. It verifies the packet against
its retained manifest, definitions, selected person's accepted revisions, evidence,
identity, current head and byte budgets. Changing the packet or advancing its base
requires rebuilding. It loads only manifest-declared instructions; slot values
never trigger file reads, shell commands or expression evaluation.

CLI: `helseark --vault PATH agent render --context PACKET --person UUID --prompt
query-with-evidence --variables SLOTS_JSON --trusted-context-sha256 HOST_DIGEST --json`. SLOTS_JSON is an explicit host
input file, not an include mechanism inside a slot. The CLI checks the selected
vault/person against the packet before rendering. Provide `source_data` as an
object and `output_directory` as an absolute absent directory. `request` defaults
to an empty string; null is allowed only where the manifest explicitly declares
it. Toolkit selectors are filled from the verified packet. Repeated selectors
must match it. Import/correction human confirmations are separate required
boolean arguments supplied by the host after an explicit human decision; source
assertions cannot supply them. Candidate IDs are explicit host allocations.

Every declared slot occurrence is substituted as exact JSON in a single pass. Delimiter characters `<`, `>` and
`&` are Unicode escaped without changing decoded values. Marker-looking source
strings remain literal data. Escaped inline data (including optional user-data
slots) and context data together must fit the selected maxDataBytes. The handoff
reports contextDataBytes, inlineDataBytes and handoffDataBytes. Escaping overhead
counts for **every actual occurrence**, including repeated declared slots. Trusted
selectors and explicit host metadata (output/candidate IDs and human decisions)
remain separate from inline source/user data. Validate the complete template before
counting; marker-looking inserted strings are never scanned again. Reduce inline payloads or explicitly rebuild with a larger budget rather
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

Retained pre-renderer protocol-1 archives and kits remain readable under their
original schemas and pins through archive reading and task discovery. A new
context projection requires the retained v2 selection definition; its absence
fails MISSING_DEFINITION before any packet is published. Those releases have no
Task4 prompt routes or typed rendering limits. No installed newer definition is
substituted, no v1 projection is fabricated, and reopening never repins a vault
or rewrites accepted history. New context support requires an explicit future
migration to compatible retained definitions and instructions.

The rendered handoff header includes contextPath and the verified readableFiles
with exact paths, sizes and hashes, plus packet data/instruction budgets and
continuation. Identity/evidence routes identify only disposable projections.
These budgets measure packet payloads and selected instruction files; rendered
text additionally includes routing metadata and separately bounded typed slots.
The renderer neither embeds original evidence nor grants filesystem authority.

## Task5 retained intake handoff (kit 0.1.2)

The [intake contract 1](intake.md) defines source/extraction receipts and the real
CLI entry, typed confirmed assignment and candidate-reading boundary. Intake uses
this protocol's existing v2 selector and renderer, never a competing prompt or
projection owner. Its PDF draft is available; current kit 0.1.9 also supports the two [bounded structured families](../how-to/import-structured-data.md). Reviewed
publication is available only through explicit human host control. The runtime handoff discloses whole-workflow
availability separately. Source-specific packets request exactly one user-selected
source and minimal identity; source assertions cannot grant broader authorization.
Old copied compatible kits/definitions remain unchanged; no automatic vault repin.

New intake contexts additionally bind optional selectedExtractions read receipts
into the original host construction digest. Only the selected immutable extraction
bytes enter readableFiles; source_data paths grant no authority. The import-only
ContextRequest.includeSourceExtractions defaults false for existing context callers.
Historical packets omit this field and receive no implicit read expansion. See the
[intake contract](intake.md#selected-extraction-read-receipts-kit-012) for budget,
no-follow verification, retained-schema compatibility and qualitative attribution.


## Exact reviewed publication (host workflow)

PDF and supported structured candidates can be prepared, reviewed by a human and atomically committed
through the [review contract](review.md) and [import how-to](../how-to/import-report.md).
`reviewed-publication`, `fhir-r4-import` and `csv-metrics-import` are implemented kit capabilities. No generic arbitrary-format importer is advertised. Availability never grants an external agent commit permission.
Human decision JSON, re-extraction intent, reconciliation and runtime preparation
control stay outside hostile source text and agent-writable packet/output trees.
The agent can emit a candidate or report only; it cannot self-authorize acceptance.
Retain exact accepted proposal/input/report/receipt/assets after clearing work.

Human-controlled publication retains review contract `0.1.1` exact issue identities.
See [exact issue decisions](review.md#exact-issue-decisions-and-historical-compatibility)
for unchecked coverage, legacy input ambiguity and qualified historical receipts.
An agent never supplies a person's confirmation or acknowledgment on their behalf.
