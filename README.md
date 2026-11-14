# Helseark

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/brand/svg/helseark-horizontal-reverse.svg">
  <img src="docs/brand/svg/helseark-horizontal-color.svg" alt="Helseark — Quiet Ark logo" width="480" height="120">
</picture>

A local personal and family health archive toolkit, under development.

Canonical clinical records use FHIR R4, with retained source evidence, explicit human review, and immutable history. Normal archive operations are offline. No medical correctness or release readiness is claimed.

## Current implementation

The current CLI supports vault initialization, explicit person creation, offline
schema export, bounded candidate/proposal validation, and agent task discovery,
context packets and prompt rendering. Optional text-PDF extraction is a library
adapter. Full import/review/commit, query, recovery and other workflows are still
being implemented. Inspect `helseark --help` and task availability; prompt files
are not proof of a supported command. No model provider is required or invoked.

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

## Documentation and participation

- [Archive format and supported commands](docs/reference/archive-format.md)
- [Clinical model](docs/reference/clinical-model.md), [agent protocol](docs/reference/agent-protocol.md), [PDF extraction](docs/reference/pdf-extraction.md)
- [Privacy and agent boundaries](docs/explanation/privacy-and-agent-boundaries.md)
- [Contributing](CONTRIBUTING.md), [coding guide](docs/development/coding-guide.md), [governance](GOVERNANCE.md), [changelog](CHANGELOG.md)
- [Security reporting](SECURITY.md), [support](SUPPORT.md), [code of conduct](CODE_OF_CONDUCT.md)
- [Release guide](docs/maintainers/releasing.md) and [licensing status](docs/maintainers/licensing.md)
- [Logo and brand assets](docs/brand/README.md)

Public launch is planned after implementation and publication checks. Project-authored code, schemas, profiles and documentation use the
[MIT License](LICENSE), matching Rikdom. Existing fixture/upstream terms are
listed in the licensing guide. User records are not licensed by the toolkit.
