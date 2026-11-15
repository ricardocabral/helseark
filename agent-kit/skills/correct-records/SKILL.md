---
name: correct-records
description: Draft a transcription correction for a confirmed source fact while preserving logical identity and clinical status.
---

# correct-records

Read [common archive instructions](../../AGENTS.md) first. Task ID: `correct`.

Require a revision-pinned target, current base, explicit correction reason and confirmed correspondence to the source fact. A transcription fix retains the logical resource ID and source clinical status; preparation later allocates a new revision with revision provenance. Do not call it a laboratory amendment. A source-issued amendment needs its actual new source/status and separate intent. Show added/changed/omitted facts, retained old revisions and unresolved correspondence. Use candidate/report routes only; uncertain correspondence or stale base blocks handoff. Omitted old facts remain accepted.

Contracts: [clinical model](../../docs/reference/clinical-model.md#identity-references-and-versions), [evidence checklist](../../docs/reference/clinical-model.md#evidence-checklist), [archive identity/revisions](../../docs/reference/archive-format.md#identity-and-revisions). For candidate production use [`candidate.schema.json`](../../schemas/0.1.1/candidate.schema.json) and [`evidence.schema.json`](../../schemas/0.1.1/evidence.schema.json); never substitute a parallel clinical format.

Prompt routes: [`propose-correction`](../../prompts/propose-correction.md).

Capability dependencies: `agent-context`, `correction`, `baseline-validation`,
`reviewed-publication`. Check availability in the [common capability
section](../../AGENTS.md#capability-availability), then the trusted runtime registry;
this dependency list does not establish availability. The route produces untrusted drafts; human review/commit is separate. No model
accuracy qualification is implied by capability availability.

Follow the [implemented correction commands](../../docs/how-to/correct-record.md).
Report stale parent children and explicit cancellation dispositions. Never erase
a person as part of a correction; [removal](../../docs/how-to/manage-family.md)
has its own digest-bound approval and recoverable quarantine.
