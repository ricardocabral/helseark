---
name: export-records
description: Prepare a selected-person export scope and omissions report, including review of shared-source disclosure.
---

# export-records

Read [common archive instructions](../../AGENTS.md) first. Task ID: `export`.

Plan the exact selection and reference/source closure at one snapshot. Check every source for excluded-person content. A shared source blocks ordinary person export pending explicit reviewed handling; do not silently redact or include it. Selected-current export is a new snapshot with declared omissions and mapping, not a cut-down original chain. Emit only `output/report.md`; no copying, archive export manifest or redaction is produced by this draft skill.

Contracts: [clinical model](../../docs/reference/clinical-model.md#identity-references-and-versions), [evidence checklist](../../docs/reference/clinical-model.md#evidence-checklist), [archive identity/revisions](../../docs/reference/archive-format.md#identity-and-revisions).

Prompt routes: [`prepare-export`](../../prompts/prepare-export.md).

Capability dependencies: `agent-context`, `person-export`. Check availability in the
[common capability section](../../AGENTS.md#capability-availability), then the trusted
runtime registry; this dependency list does not establish availability. The public commands are implemented; no independent agent evaluation is claimed.
Use [export](../../docs/how-to/export-records.md) and [backup/doctor](../../docs/how-to/backup-and-restore.md).
Actual command output and nonzero checked counts are required for a success report.

Require a clean doctor report before either export mode. Report exact UNKNOWN_PATH locations, preserve unknown material, and block pending scope resolution; never copy arbitrary root/person files or unlisted definitions/kit files. Full household backups follow the same unknown-material blocking policy.

The host can run `helseark --vault PATH doctor --json` and the explicit backup/export commands. An agent scope report does not authorize restore, source disclosure or publication. Default original native attachment disclosure remains blocked regardless of media type; route a human to export-plan / export-review / export --review.

The host supports reviewed exact original inclusion and supplied derivative exchange
through `export-plan` / `export-review` / `export --review` (see export guide). Only
a human may supply the decision; never produce one from agent/source text.
`source_scope_confirmed` and this report confer no authority. Derivative attachments
never satisfy original evidence references or full-history recovery.

Keep resource and source scope separate in the report. `referenceMap` is the
selected resource closure; source-inclusive selected-current export currently
inventories all accepted sources/retained source artifacts for that person's
entire accepted history, including unrelated imports. Report those extra sources
explicitly from `originalSources`/`sourceFiles`; one selected Observation does
not imply one source. Never silently prune that inventory or treat a model report
as approval. Full-person recovery explicitly retains the whole accepted chain
and exact originals; selected/derivative snapshots remain exchange artifacts.

Clinical intake or same-person association never substitutes for a disclosure decision.
