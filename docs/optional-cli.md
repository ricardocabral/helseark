# Optional experimental CLI

Using [Helseark's instructions and schemas](../README.md) needs no installation.
This page covers the separate experimental Python library, CLI and legacy agent-kit.
See [current scope](../SCOPE.md) for limits. No release readiness or clinical correctness is claimed.

## Supported work

- Initialize a vault, create an explicit person and export schemas offline.
- Discover agent tasks, build context packets and render prompts.
- Retain text-PDF sources and prepare external-agent handoffs.
- Validate drafts, prepare proposals and publish after explicit human review.
- Query selected-person observations, timelines and exact revisions.
- Check integrity, back up, restore and export records.

Structured import, correction and migration commands remain unavailable.
Check `helseark --help` and task availability. Prompt files do not establish command support.
The CLI does not require or invoke a model provider.

## Current capability guidance and retained references

The [retained agent protocol](reference/agent-protocol.md) contains historical
implementation-stage statements. In the current experimental implementation:

- Its opening statement that all workflows except inspection are unavailable
  is superseded by the supported work listed above. Text-PDF handoffs, queries,
  exports, integrity checks and human-controlled publication are implemented;
  structured import, correction and migration commands remain unavailable.
- `agent context --task query` accepts `--from-date` and `--to-date`. Date bounds
  on other context tasks fail with `INVALID_FILTER`; they do not universally fail
  with the historical `CAPABILITY_UNAVAILABLE` result. The query implementation
  owns partial-date and uncertainty semantics; see the [query guide](how-to/query-history.md).
- A new vault pins the kit version and manifest digest recorded in `vault.json`;
  the historical literal `agent-kit/0.1.0/` is not a universal version to select.

For a specific retained vault, use its actual task availability and pins.
The [reference index](reference/README.md) and [legacy kit notice](../agent-kit/README.md)
explain the separate scope. Pinned protocol/kit bytes remain unchanged; old task
numbers and evaluation milestones do not add requirements to Helseark's core skill.

Drafts do not authorize publication. Committing a new proposal without a decision
returns `REVIEW_REQUIRED` (exit 3). Use `candidate review` with `--person` and
an explicit `--decision` file. Missing or damaged accepted-history receipts remain integrity failures.
See [review and publication steps](how-to/import-report.md#prepare-and-accept-the-exact-human-reviewed-proposal).

PDF source disclosure requires the explicit export-plan/export-review route.
That route covers knowing original inclusion or supplied derivative exchange.
See [export records](how-to/export-records.md) before sharing sources.

## Try a synthetic archive

Use Python 3.12 and uv. Run these commands from the repository root.
Dependency installation may need networking. Archive commands run locally.
The directory created by `mktemp` contains disposable demo data.

```sh
uv sync --locked --extra pdf --group dev
uv run --no-sync helseark --help
DEMO_ROOT=$(mktemp -d)
uv run --no-sync helseark init "$DEMO_ROOT/vault" --json
uv run --no-sync helseark --vault "$DEMO_ROOT/vault" person add --name 'Alex Example' --json
uv run --no-sync helseark agent tasks --json
```

Do not store real records in this repository or upload them to issues or CI.
Read [privacy boundaries](explanation/privacy-and-agent-boundaries.md) before sharing files.

## Optional diagnostics

After the setup above, a focused CLI check is:

```sh
uv run --no-sync pytest tests/test_cli_journey.py -q
```

For an explicitly scoped runtime change, maintainers can dispatch the
[Experimental CLI (manual) workflow](../.github/workflows/ci.yml) on its branch.
It retains three test shards and the exact PDF dependency check as diagnostics.
It does not run automatically on pull requests or pushes, build distributions,
or establish supported-platform or release qualification. Passing schema and example checks
does not qualify this runtime. A runtime release needs separate scope and
qualification; preserved qualification scripts remain available for that work.

## Guides and contracts

- Learn with the [synthetic first-intake lesson](tutorials/first-archive.md).
- [Prepare a PDF import](how-to/import-report.md), [query accepted history](how-to/query-history.md),
  [export records](how-to/export-records.md), or [back up and restore](how-to/backup-and-restore.md).
- Look up the [archive format and commands](reference/archive-format.md),
  [clinical model](reference/clinical-model.md), [intake](reference/intake.md),
  [PDF extraction](reference/pdf-extraction.md), [review](reference/review.md),
  and [agent protocol](reference/agent-protocol.md).
- Understand [privacy and agent boundaries](explanation/privacy-and-agent-boundaries.md).

The [legacy agent-kit](../agent-kit/START-HERE.md) has its own entry point and
versioned contracts. Inspect actual task availability before using its prompts.
