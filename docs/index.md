# Helseark documentation

Helseark keeps a local personal or family archive of evidence-linked FHIR R4
records. This documentation describes toolkit 0.1.2 and kit 0.1.13, archive format 1,
contracts/profiles 0.1.0, exact-issue review 0.1.1 and serializer helseark-json-1.
It is under development and is not production-qualified. Human review remains
mandatory; baseline validation does not establish clinical accuracy.

## Learn

[First archive](tutorials/first-archive.md) walks through a supplied synthetic PDF,
explicit fixture review, accepted publication, idempotent retry, query and recovery.
It needs no model account and makes no extraction-accuracy claim.

## Accomplish a task

- [Import a report with an external agent](how-to/import-report.md): retain sources,
  restrict the agent, inspect a proposal and record your own decision.
- [Query accepted history](how-to/query-history.md): preserve native result shapes,
  units, precision, revisions and evidence.
- [Manage explicit family identities](how-to/manage-family.md): distinguish same-name
  people and select the intended UUID.
- [Correct a record](how-to/correct-record.md): inspect the old revision and evidence,
  publish a human-reviewed correction, amendment or invalidation.
- [Migrate an archive](how-to/migrate-archive.md): review a lossless copy plan into
  a separate absent destination, preserving historical pins.
- [Back up and restore](how-to/backup-and-restore.md): verify an entire household
  archive into a new directory without replacing history.
- [Export records](how-to/export-records.md): distinguish full-person history from
  a selected clinical snapshot, and handle source-disclosure restrictions.
- [Troubleshoot safely](how-to/troubleshoot.md): preserve blocked work and recover
  through supported commands.

## Look up facts

[CLI](reference/cli.md) · [Python API](reference/python-api.md) ·
[Compatibility](reference/compatibility.md) · [Archive format](reference/archive-format.md) ·
[Clinical model](reference/clinical-model.md) · [Agent protocol](reference/agent-protocol.md) ·
[Intake](reference/intake.md) · [PDF extraction](reference/pdf-extraction.md) ·
[Review](reference/review.md) · [Archival definitions bundle](reference/archival-bundle.md).

## Understand

[Architecture](explanation/architecture.md) explains file authority and FHIR.
[Provenance and revisions](explanation/provenance-and-revisions.md) distinguishes
source facts from review and acceptance.
[Privacy and agent boundaries](explanation/privacy-and-agent-boundaries.md) explains
scope and host authority. [Evolution](explanation/evolution.md) explains independent
version pins. [Evaluation and limits](explanation/evaluation-and-limits.md) separates
deterministic toolkit evidence from actual agent observations.

## Offline location and current limits

In a vault read its root AGENTS.md, then vault.json and
`agent-kit/<agentKitVersion>/START-HERE.md`. This index is at
`agent-kit/<agentKitVersion>/docs/index.md`; its links resolve within that retained
release. The definitions copy also retains documentation, but the pinned kit is
the onboarding route. The contributor repository AGENTS.md is not archive guidance.

This branch supports text-PDF drafts, human-controlled prepared publication,
queries, doctor, household backup/restore, reviewed original-source or derivative
person export, corrections, recoverable person removal and lossless migration copies.
Structured imports, official validator integration, broader history profiles, OCR
and static reports are not available here. Full all-feature guide reconciliation
and qualification remain later gates with their independently owned features.
Templates do not establish capability. Actual-agent/model acceptance is separate
from this deterministic tutorial; no extraction accuracy is implied.
