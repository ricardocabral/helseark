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

The host can run `helseark --vault PATH doctor --json` and the explicit backup/export commands. An agent scope report does not authorize restore, source disclosure or publication. PDF source scope remains blocked without a reviewed derivative workflow.

Require a clean doctor report before either export mode. Report exact UNKNOWN_PATH locations, preserve unknown material, and block pending scope resolution; never copy arbitrary root/person files or unlisted definitions/kit files. Full household backups follow the same unknown-material blocking policy.
