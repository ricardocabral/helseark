---
name: migrate-archive
description: Prepare a non-mutating migration assessment with explicit target definitions, unsupported mappings and preservation gates.
---

# migrate-archive

Read [common archive instructions](../../AGENTS.md) first. Task ID: `migrate`.

Require original pins, target pinned definitions, a supported mapping and counts of all revisions within authorized scope. A selected-person packet cannot certify a whole-vault migration. Distinguish contract migration from FHIR release conversion. Assess identities, evidence, source/revision hashes, references, facts and query comparison gates. No in-place rewrite or implicit migration-on-open. Emit only `output/report.md`; absent mappings/target contracts mean blocked, not a fabricated executable plan. Host apply requires a new empty destination, full graph validation and explicit human review.

Contracts: [clinical model](../../docs/reference/clinical-model.md#identity-references-and-versions), [evidence checklist](../../docs/reference/clinical-model.md#evidence-checklist), [archive identity/revisions](../../docs/reference/archive-format.md#identity-and-revisions).

Prompt routes: [`plan-migration`](../../prompts/plan-migration.md).

Capability dependencies: `agent-context`, `migration`. Check availability in the [common
capability section](../../AGENTS.md#capability-availability), then the trusted runtime
registry; this dependency list does not establish availability. The engine supports only v1 identity copy and an explicitly opted-in test-only layout.
No model evaluation or clinical conversion support follows from engine availability.
Use the [migration guide](../../docs/how-to/migrate-archive.md) and
[compatibility reference](../../docs/reference/compatibility.md).
A human separately runs the whole-vault planner and reviews its exact digest;
this selected-person skill only produces an assessment.
