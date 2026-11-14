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
runtime registry; this dependency list does not establish availability. This skill is
draft-only until those dependencies are implemented and evaluated.
