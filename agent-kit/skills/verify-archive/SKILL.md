---
name: verify-archive
description: Report integrity evidence and recovery choices without modifying accepted history or presenting incomplete reads as clean.
---

# verify-archive

Read [common archive instructions](../../AGENTS.md) first. Task ID: `verify`.

Distinguish a supplied failure from a verifier run you actually performed. Report exact affected paths, check families, counts and coverage; zero/incomplete checks cannot establish integrity. On a hash or chain error stop dependent interpretation. Preserve originals; propose a separately verified backup/compatible-reader recovery path, without editing inventory hashes, dropping changes or deleting orphans. Emit only `output/report.md`. A definition-bundle check is not a clinical archive doctor.

Contracts: [clinical model](../../docs/reference/clinical-model.md#identity-references-and-versions), [evidence checklist](../../docs/reference/clinical-model.md#evidence-checklist), [archive identity/revisions](../../docs/reference/archive-format.md#identity-and-revisions).

Prompt routes: [`verify-archive`](../../prompts/verify-archive.md).

Capability dependencies: `agent-context`, `integrity-report`. Check availability in the
[common capability section](../../AGENTS.md#capability-availability), then the trusted
runtime registry; this dependency list does not establish availability. The public commands are implemented; no independent agent evaluation is claimed.
Use [export](../../docs/how-to/export-records.md) and [backup/doctor](../../docs/how-to/backup-and-restore.md).
Actual command output and nonzero checked counts are required for a success report.

The host can run `helseark --vault PATH doctor --json` and the explicit backup/export commands. An agent scope report does not authorize restore, source disclosure or publication. PDF source scope remains blocked without a reviewed derivative workflow.

Use the actual doctor report: retain successfully checked counts and exact issue paths/actions, including UNKNOWN_PATH and unsafe staging entries. Preserve unknown files and symlinks without following or deleting them; unresolved unknown material blocks backups and both person export modes. Never label unlisted support files accepted or person-scoped.

A failed directory enumeration or entry stat is IO_ERROR, not an empty successful read. Retain verified counts and the confined path/action; block all backup/person outputs until inspection is possible. Never change access or quarantine material automatically.

Optional official R4 validation is an explicit host operation over a prepared
proposal, using pinned local Java/JAR/packages and OS network confinement.
Its report states exact resource/error/warning counts and supported-profile
coverage. It never establishes clinical correctness. Terminology is not checked
in the qualified `-tx n/a` mode; requiring terminology blocks. Tool absence never
blocks baseline use, but an explicit required full-check policy does block.
See [offline validator](../../docs/how-to/run-offline-validator.md).

An explicit official-validator request requires host-selected pinned configuration. Its complete actual execution authority must match at render, human review and publication. A failed or superseding request revokes prior authority; only a fresh successful actual run restores it. Optional baseline use needs no Java. Required official or terminology policy fails closed. Accepted legacy unattested reports remain readable without inventing attestation. See [offline validator](../../docs/how-to/run-offline-validator.md).
