---
name: migrate-archive
description: Prepare a non-mutating migration assessment with explicit target definitions, unsupported mappings and preservation gates.
---

# migrate-archive

Read [common archive instructions](../../AGENTS.md) first. Task ID: `migrate`.

Require original pins, target pinned definitions, a supported mapping and counts of all revisions within authorized scope. A selected-person packet cannot certify a whole-vault migration. Distinguish contract migration from FHIR release conversion. Assess identities, evidence, source/revision hashes, references, facts and query comparison gates. No in-place rewrite or implicit migration-on-open. Emit only `output/report.md`; absent mappings/target contracts/planner mean blocked, not a fabricated executable plan. Future apply requires a new empty destination, full graph validation and explicit human review.

Contracts: [clinical model](../../../docs/reference/clinical-model.md#identity-references-and-versions), [evidence checklist](../../../docs/reference/clinical-model.md#evidence-checklist), [archive identity/revisions](../../../docs/reference/archive-format.md#identity-and-revisions).

Prompt routes: [`plan-migration`](../../prompts/plan-migration.md).

Capability dependencies: `agent-context`, `migration`. At base `1b91620`, only `schema-export` and `baseline-validation` exist; dependencies outside that set are unavailable. This skill is draft-only until those dependencies are implemented and evaluated. Existing validation can check an already supplied candidate, but does not provide intake, preparation or publication.
