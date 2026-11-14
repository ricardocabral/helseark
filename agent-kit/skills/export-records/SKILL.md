---
name: export-records
description: Prepare a selected-person export scope and omissions report, including review of shared-source disclosure.
---

# export-records

Read [common archive instructions](../../AGENTS.md) first. Task ID: `export`.

Plan the exact selection and reference/source closure at one snapshot. Check every source for excluded-person content. A shared source blocks ordinary person export pending explicit reviewed handling; do not silently redact or include it. Selected-current export is a new snapshot with declared omissions and mapping, not a cut-down original chain. Emit only `output/report.md`; no copying, archive export manifest or redaction is produced by this draft skill.

Contracts: [clinical model](../../../docs/reference/clinical-model.md#identity-references-and-versions), [evidence checklist](../../../docs/reference/clinical-model.md#evidence-checklist), [archive identity/revisions](../../../docs/reference/archive-format.md#identity-and-revisions).

Prompt routes: [`prepare-export`](../../prompts/prepare-export.md).

Capability dependencies: `agent-context`, `person-export`. At base `1b91620`, only `schema-export` and `baseline-validation` exist; dependencies outside that set are unavailable. This skill is draft-only until those dependencies are implemented and evaluated. Existing validation can check an already supplied candidate, but does not provide intake, preparation or publication.
