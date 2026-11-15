# Helseark documentation

Helseark keeps a local personal or family archive of evidence-linked FHIR R4
records. This documentation describes toolkit 0.1.2 and kit 0.1.19, archive format 1,
contract 0.1.0, profile-set 0.2.0, exact-issue review 0.1.1 and serializer helseark-json-1.
It is under development and is not production-qualified. Human review remains
mandatory; baseline validation does not establish clinical accuracy.

## Learn

[First archive](tutorials/first-archive.md) walks through a supplied synthetic PDF,
explicit fixture review, accepted publication, idempotent retry, query and recovery.
It needs no model account and makes no extraction-accuracy claim.

## Accomplish a task

- [Import a report with an external agent](how-to/import-report.md): retain sources,
  restrict the agent, inspect a proposal and record your own decision.
- [Import structured data](how-to/import-structured-data.md): bounded native FHIR R4
  and explicitly mapped numeric CSV, with coverage and source identity review.
- [Retain local OCR](how-to/run-ocr.md): pinned optional macOS tools and uncertain text.
- [Generate static reports](how-to/generate-reports.md): derived HTML/CSV/SVG with evidence.
- [Run the optional official validator](how-to/run-offline-validator.md): separate pinned
  Java/package setup, offline execution and host-held review authority.
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

This distribution supports text-PDF drafts, bounded native FHIR R4 and mapped
numeric CSV intake, eight source-assertion history families, exact human-reviewed
publication, queries, static reports, doctor, backup/restore, reviewed source
exports, corrections, recoverable person removal and lossless migration copies.
OCR is optional and currently macOS-only; official validation needs separately
provisioned pinned Java/packages. Neither operation runs a model or accepts facts.
Full remote Linux/macOS CI, independent final-union review and actual final-kit
agent scenarios remain open. See [evaluation and limits](explanation/evaluation-and-limits.md).
