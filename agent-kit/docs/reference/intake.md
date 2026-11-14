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
budget. Only the selected source hash and necessary identity are requested; no
historical records or automatically broadened source permissions are added.

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

`read_candidate(vault, candidateDirectory) -> Candidate` reads strict candidate and
evidence envelopes using retained definitions, checks current person/head, declared
producer pins, exact source bytes and PDF extraction receipts, and preserves Issue
bytes. Artifact paths must be distinct confined relative paths: absolute paths,
`../`, backslashes, symlinks and symlink ancestors fail UNSAFE_PATH. Directory input
itself may be absolute; that does not authorize absolute bundle/evidence paths.
Defaults are 10000 resources, 64 JSON containers, 1 MiB per text field/key, and
64 MiB per candidate JSON file. Number tokens use the exact Task2 serializer;
no binary float conversion. Boundary/provenance/receipt failures raise safe errors.
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
--fixtures ABSOLUTE_SYNTHETIC_FIXTURES --out ABSENT_PHASE_ROOT --inventory HOST_ONLY_JSON`
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
