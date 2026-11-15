# Helseark

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/ricardocabral/helseark/main/docs/brand/svg/helseark-horizontal-reverse.svg">
  <img src="https://raw.githubusercontent.com/ricardocabral/helseark/main/docs/brand/svg/helseark-horizontal-color.svg" alt="Helseark — Quiet Ark logo" width="480" height="120">
</picture>

A local personal and family health archive toolkit, under development.

Canonical clinical records use FHIR R4, with retained source evidence, explicit human review, and immutable history. Normal archive operations are offline. No medical correctness or release readiness is claimed.

[Learn with the synthetic import/query/restore lesson](docs/tutorials/first-archive.md),
[accomplish a task](docs/index.md#accomplish-a-task),
[look up CLI and API contracts](docs/index.md#look-up-facts), or
[understand the design](docs/index.md#understand).

## Current implementation

The current CLI supports vault initialization, explicit person creation, offline
schema export, bounded candidate/proposal validation, and agent task discovery,
context packets and prompt rendering. Text-PDF intake retains sources and creates
scoped external-agent handoffs. Human-controlled preparation, exact-issue review
and publication of PDF candidates are implemented, along with selected-person
observations, timeline and exact-revision queries. Doctor, verified backup/restore
and person export are implemented; PDF source disclosure requires the explicit
export-plan/export-review route for knowing original inclusion or supplied
derivative exchange. Bounded FHIR R4 and explicitly mapped numeric CSV intake,
eight native source-assertion history families, optional local OCR, and derived
static HTML/CSV/SVG reports are integrated in this combined development distribution.
See [structured intake](docs/how-to/import-structured-data.md),
[native history](docs/how-to/query-history.md), [OCR](docs/how-to/run-ocr.md) and
[reports](docs/how-to/generate-reports.md). Corrections, recoverable person removal and non-destructive migration copies are implemented. Inspect `helseark --help` and task availability; prompt files
are not proof of a supported command. No model provider is required or invoked.
These staged guides use paths in this revision; public `main` may lag. Offline,
open `docs/how-to/` in the source distribution, `share/helseark/docs/how-to/`
under the installed Python environment, or `agent-kit/0.1.19/docs/how-to/`
in a newly initialized vault. Existing vaults retain their pinned kit guides.

[Prepare a PDF import](docs/how-to/import-report.md)
or follow the [synthetic first-intake lesson](docs/tutorials/first-archive.md).
Intake produces untrusted drafts; it does not authorize publication.
Committing a newly prepared proposal before recording a decision returns
`REVIEW_REQUIRED` (exit 3). Use `candidate review` with `--person` and an explicit
`--decision` file before committing. Missing receipts in accepted history remain
integrity failures; damaged review records do not authorize publication.

For deeper R4/profile checks, see the [optional offline official validator](docs/how-to/run-offline-validator.md). Baseline use needs no Java; terminology remains not checked.

## Try a synthetic archive

Use Python 3.12 and uv. Dependency installation may need networking; the archive
commands run locally. The directory created by `mktemp` is disposable demo data.

```sh
uv sync --locked --extra pdf --group dev
uv run --no-sync helseark --help
DEMO_ROOT=$(mktemp -d)
uv run --no-sync helseark init "$DEMO_ROOT/vault" --json
uv run --no-sync helseark --vault "$DEMO_ROOT/vault" person add --name 'Alex Example' --json
uv run --no-sync helseark agent tasks --json
```

Do not store real records in this repository or upload them to issues or CI.
Local storage is not encryption or per-person access control. External agents
receive the context you explicitly share with them.

Read the [documentation index](docs/index.md) for supported reader routes.

## Documentation and participation

- [Archive format and supported commands](docs/reference/archive-format.md)
- [Clinical model](docs/reference/clinical-model.md), [agent protocol](docs/reference/agent-protocol.md), [PDF extraction](docs/reference/pdf-extraction.md)
- [Privacy and agent boundaries](docs/explanation/privacy-and-agent-boundaries.md)
- [Contributing](https://github.com/ricardocabral/helseark/blob/main/CONTRIBUTING.md), [coding guide](https://github.com/ricardocabral/helseark/blob/main/docs/development/coding-guide.md), [governance](https://github.com/ricardocabral/helseark/blob/main/GOVERNANCE.md), [changelog](https://github.com/ricardocabral/helseark/blob/main/CHANGELOG.md)
- [Security reporting](https://github.com/ricardocabral/helseark/blob/main/SECURITY.md), [support](https://github.com/ricardocabral/helseark/blob/main/SUPPORT.md), [code of conduct](https://github.com/ricardocabral/helseark/blob/main/CODE_OF_CONDUCT.md)
- [Release guide](https://github.com/ricardocabral/helseark/blob/main/docs/maintainers/releasing.md) and [licensing status](https://github.com/ricardocabral/helseark/blob/main/docs/maintainers/licensing.md)
- [Logo and brand assets](https://github.com/ricardocabral/helseark/blob/main/docs/brand/README.md)

Public launch is planned after implementation and publication checks. Project-authored code, schemas, profiles and documentation use the
[MIT License](https://github.com/ricardocabral/helseark/blob/main/LICENSE), matching Rikdom. Existing fixture/upstream terms are
listed in the licensing guide. User records are not licensed by the toolkit.
