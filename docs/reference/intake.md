# Intake contract 1 — kit 0.1.1

`add_source(vault, person, source) -> SourceReceipt` requires an existing explicitly
selected person. It reads at most 100 MiB, rejects symlinks/ancestors, traversal and
nonregular files, and retains original bytes under
`people/<person>/assets/sha256/<digest>/blob`. Equal bytes share this asset within
one person, never across people. Filenames do not select identities or instructions.
`source.json` is an immutable version-1 receipt: person, hash, size, media type,
vault-relative asset path and null existingImport. Live SourceReceipt.assetPath
is an explicit absolute path; copying a vault does not rewrite durable receipts. Every reuse verifies actual bytes.
Existing accepted-import discovery/idempotence belongs Task6; null is not proof
that equivalent medical facts were never accepted.

`build_packet(vault, source, destination) -> ImportPacket` uses the real optional
PDF adapter, `build_agent_context` and `render_task_prompt`. Optional keyword-only
arguments are `identityConfirmed=False`, `outputDirectory=None`, and
`limits=IntakeLimits()`. Default output is the absolute sibling
`<destination>-agent-output`; explicit CLI `--agent-output` is recommended. Neither
packet nor output may overwrite an existing directory or enter canonical vault
paths; selected-person work is allowed. The output root stays absent for the agent.
The packet contains ENTRY.md, prompt.txt, intake.json (packetVersion 1), and the
unchanged context builder's context directory. Its importId is the allocated
candidate UUID. All pinned context/selector contracts remain authoritative, including
v2 metadata-bound generated/user-entry projections and the renderer's escaped byte
budget, counting each actual escaped slot occurrence. Only the selected source hash and necessary identity are requested; no
historical records or automatically broadened source permissions are added.

Intake keeps the original in-memory context builder result through rendering.
`ImportPacket.trustedContextSha256` returns that original construction digest to
the trusted caller; `document(packet)` excludes it. `intake add --json` exposes
it on stdout alongside the receipt; plain output prints the packet path and a
host-retained digest line. Capture stdout directly in trusted operator/job state,
separate from agent-editable packet files. Neither intake.json nor context.json
contains authority. To rerender, use `read_agent_context(packet.path / 'context')`
and pass the retained digest as `trusted_context_sha256=` (CLI:
`agent render --trusted-context-sha256 HOST_DIGEST`). A plain reload fails
CONTEXT_AUTHORITY_REQUIRED; edited selection/count/task/budget metadata fails
against the original digest. Never hash a mutable packet to recover authority.
If host state is lost, explicitly build a new packet with the original authorized
person/source choices. Host identity confirmation and fresh output/candidate
allocations remain separate renderer arguments, outside source_data. The digest
proves continuity with the host construction, not human review or acceptance.

Extraction pages are retained as a second content-addressed blob. An immutable
`extraction.json` beside the original has receiptVersion, sourceSha256,
pagesSha256, pageCount and issues. Exact source/derived bytes, supported artifact
version, pypdf version and preprocessing provenance are rechecked before reuse.
See [PDF extraction](pdf-extraction.md) for parser limits and page-only geometry.
Receipts provide consistency, not signed producer attestation against a host that
can rewrite all files and hashes. Local single-writer directory trees and an
external filesystem/tool boundary are required. The toolkit does not enforce host
ACLs. Packet creation can leave an incomplete private directory on abrupt death;
intake.json is the completion record. No accepted history is changed.

Encrypted/corrupt/over-page PDFs remain retained; safe errors include retainedSource
and fixed codes such as PDF_ENCRYPTED, PDF_INVALID or PAGE_LIMIT. Extraction failure
leaves no invented clinical data. SOURCE_TOO_LARGE rejects before retention without
truncation. Missing/different optional dependency reports PDF_DEPENDENCY_UNSUPPORTED;
there is no installation, provider selection, network call or automatic OCR.
OCR_REQUIRED includes blank/scan pages and never creates results. Reusing a retained
artifact also enforces the caller's page/text limits; corruption is an error, not
an invitation to overwrite history or regenerate it silently.

Multiple distinct explicit line-start `Patient:` or `Paciente:` labels create
MULTIPLE_PERSON_CUES, an error; confirmed selection cannot waive it. This is a
bounded conservative cue check, not arbitrary person recognition. Family narrative,
unlabeled reports, other languages, aliases, OCR mistakes and adversarial layouts
can escape it; SOURCE_IDENTITY_REVIEW always requires review of the original and
uncertainty. Trusted caller assignment is recorded separately from untrusted source
assertions. Source text cannot confirm identity, remove errors or authorize another
person/source. False confirmation or blocking cues renders report only.

`read_candidate(vault, candidateDirectory, *, person=None) -> Candidate` reads strict candidate and
evidence envelopes using retained definitions, checks current person/head, declared
producer pins, exact source bytes and PDF extraction receipts, and preserves Issue
bytes. Artifact paths must be distinct confined relative paths: absolute paths,
`../`, backslashes, symlinks and symlink ancestors fail UNSAFE_PATH. Directory input
itself may be absolute; that does not authorize absolute bundle/evidence paths.
Defaults are 10000 resources, 64 JSON containers, 1 MiB per text field/key, and
64 MiB per candidate JSON file. Number tokens use the exact Task2 serializer;
no binary float conversion. The optional person is caller authority: a mismatch
fails before candidate metadata can select any person's history or assets.
The CLI requires this explicit selection, verifies vault metadata/definitions and
only that person's history; unrelated corrupt histories do not block it.
Whole-vault opening/integrity checks retain their global verification scope.
Every candidate JSON read, including Task2's later metadata/bundle/evidence
binding rereads, enforces the same no-follow, byte, text and depth limits before
parsing. Oversized files fail SOURCE_TOO_LARGE, including sparse metadata.
Changed files cannot bypass those read boundaries; unequal admitted values fail
CANDIDATE_MISMATCH. Local single-writer/external host restrictions still apply.
Boundary/provenance/receipt failures raise safe errors.
Semantic clinical checks use `validate_candidate` and the CLI `validate candidate`;
a returned Candidate is not a validation pass or an acceptance. Missing/downgraded
retained issues fail INTAKE_ISSUES_MISSING; MULTIPLE_PERSON_CUES is never waivable.
Known PDF provenance must match retained pages; invented boxes fail EXTRACTION_MISMATCH.
Historical non-PDF Task2 source assets still work without intake-specific receipts.

Task6 must consume this reader, bind exact candidate/proposal/source/evidence/report
bytes and base to human review, allocate immutable revisions once, preserve history,
handle duplicates/re-extraction/omissions and publish exactly the reviewed proposal.
`prepare_candidate`, `render_review`, `record_review`, `commit_candidate`, query,
backup and restore are not implemented by Task5. Validation does not grant authority
or constitute a review receipt. Old vault kit/definition bytes are never upgraded
or repinned automatically. Retained compatible kit readers remain supported; an
older kit may produce a blocked handoff reflecting its missing capabilities.

## External-agent evaluation preparation

Maintainers can run `scripts/intake_agent_eval.py --phase baseline|post-kit
--fixtures ABSOLUTE_SYNTHETIC_FIXTURES --out ABSENT_PHASE_ROOT --inventory HOST_ONLY_JSON
--source-commit EXACT_INSTALLED_COMMIT --distribution EXACT_INSTALLED_WHEEL`
under the respective installed committed interpreter. It prepares five identical
bounded scenarios in each phase using actual PDF extraction/context/rendering; it
never runs a model or supplies expected facts to it. Baseline synthetic harness
retention is explicitly labeled because the original Task5 API was unavailable.
The baseline renderer stops report-only; post-kit can draft confirmed text sources,
while mixed cues block and scans require OCR. This capability comparison does not
establish comparative extraction accuracy. A coordinator separately launches fresh
selected-model tabs and records actual settings, transcripts, explicit read receipts,
errors/omissions, source-row evidence and forbidden-root observations. Empty/unrun
samples remain unknown. Independent expected facts live outside agent-visible roots.

The inventory must be new and outside the agent-visible root. It retains the
operator-declared installed commit, actual wheel digest/interpreter/package path
and original CLI construction digest, with modelResult null until a real run.
Install the named wheel first; the preparation script does not verify a Git
checkout or turn an operator declaration into an installation attestation.

## Selected extraction read receipts (kit 0.1.2)

New intake contexts request `ContextRequest.includeSourceExtractions=True` for
explicit import sources. Intake resolves each source's immutable extraction
receipt and exact CAS blob with bounded no-follow reads; it never follows a path
from source_data or regenerates missing retained pages during context verification.
The optional `AgentContext.selectedExtractions` holds exact ContextFile receipts,
bound by the original host construction digest and rechecked before rendering.
Only these receipts enter readableFiles. An extractionPath assertion differing
from this selection fails CONTEXT_MISMATCH. Editing the context or substituting a
genuine unselected extraction cannot enlarge the original host authorization.
This does not grant access to other sources, people, tasks or receipt sidecars.

Every selected extraction's full byte size counts in context.dataBytes, even when
referenced rather than copied. Inline artifact/receipt/path text is additionally
charged at each actual escaped template occurrence, preserving the common renderer
budget. Exceeding either construction or rendered budget fails without truncation.
Original PDF and definition references retain their existing reference accounting.
An independent reader must read/hash the retained bytes from the verified receipt;
a decoded/re-encoded inline object is not a byte-identical artifact receipt.

Empty selectedExtractions is omitted from serialization. Existing contexts and
historical pinned definitions/kits retain their bytes/digests and render without
implicit extraction reads. New intake on a retained context schema lacking this
optional field uses that legacy route; it does not repin a vault. An explicit new
includeSourceExtractions request on such a registry fails UNSUPPORTED_VERSION.
Missing receipts/changed blobs fail closed; no parser is invoked by a reread.
Host single-writer/immutable retained assets remain required; this is consistency
and scope binding, not cryptographic attestation of a compromised host.

For qualitative results use the versioned import skill's assertion inventory:
independently labeled assertions can use code.text and exact valueString without
invented codes. A qualifier with ambiguous attribution stays explicitly uncertain;
required status/identity cannot be invented to force a resource. Notes/omissions
remain reviewable and must be disclosed. Behavioral qualification of these shapes
is not evidence that a model follows the instructions; fresh actual trials remain
a separate coordinator gate.


## Structured host issuance — kit 0.1.14

Toolkit-retained non-PDF source receipts require original structured issuance when
reading a candidate. The source-local `structured/<candidate-input-digest>.json`
receipt binds the exact serialized candidate artifacts, coverage digest, person,
source hash, family and local mapping. Candidate path/ID/producer claims and explicit
source flags do not select or waive this authority. Missing/mismatched issuance
fails `CANDIDATE_MISMATCH`; rebuild old unaccepted drafts through an explicit adapter
mapping. Never infer new authority from editable work bytes. PDF and genuine legacy
non-intake source preparation retain their own existing authority contracts.
These protected receipts may outlive `.runtime`; accepted readers still require no
runtime or work tree. Host protection of original/source-side receipts remains required.

## Optional OCR versions

`build_packet(..., ocrConfig=OcrConfig(...))` explicitly opts into the separate
[local OCR capability](../how-to/run-ocr.md). `intake add --ocr-config PATH` reads
that operator-controlled configuration. Without it, PDF-text behavior is unchanged.
OCR artifacts and receipts are immutable and selected by extraction hash; they
never replace the source's existing PDF-text extraction receipt. OCR derivatives
are retained in the person's asset inventory and reviewed proposal closure.
OCR allows genuine word boxes in displayed CropBox coordinates; page-only
PDF-text artifacts still reject invented boxes. All OCR pages remain unresolved
with mandatory OCR_VISUAL_REVIEW. Re-extraction/reconciliation, exact numeric
source tokens, patient scope, review and publication use the existing contracts.

An explicitly selected OCR version uses `ContextRequest.sourceExtractionHashes`
together with `includeSourceExtractions`. Intake resolves exactly one immutable
artifact per selected original; it checks the original/person, extraction receipt
and derivatives without rerunning a parser. The host construction digest binds
these selected receipts and their full sizes count toward the context budget.
Unselected, changed or ambiguous versions fail before rendering.

New accepted structured proposals retain exact `inputs/coverage.json` in addition
to the three candidate inputs. Its mapping/coverage digest permits doctor and
backup to account for a matching source-local issuance receipt when present.
Unknown, altered and unaccepted sidecars remain visible audit issues. Issuance is
resumable host state: accepted queries/history do not require it, work or runtime.
