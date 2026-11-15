# Contributing to Helseark

Read the [coding guide](docs/development/coding-guide.md),
[code of conduct](CODE_OF_CONDUCT.md) and [security policy](SECURITY.md).

## Ways to contribute

Fix bugs, improve documentation and examples, add tests, or propose focused
features. Check existing [issues](https://github.com/ricardocabral/helseark/issues)
and [pull requests](https://github.com/ricardocabral/helseark/pulls) first. For
large changes, open an issue to align on scope and design. Keep changes focused.

## Choose the right scope

Helseark's core consists of the [agent skill](skills/helseark/SKILL.md), shared
instructions, three task references, FHIR R4 schemas and a complete invented example.
Preserve precision, explicit person identity, source evidence, human
review and accepted history. See [SCOPE.md](SCOPE.md) for deferred work. Existing
Python/CLI and legacy agent-kit work remains optional and preserved; their setup
is not required to use or improve these files. Do not restart an older application
roadmap or add infrastructure without explicit scope authorization. Keep clinical
meaning in FHIR rather than introducing a parallel format.

Public references, tests and self-contained issues describe the work. Private
plans and coordination logs stay in ignored `docs/internal/`; contributors do
not need them. Ask the coordinator for public acceptance criteria when needed.
Never publish private plans, real health data or health records with only names
removed. Use invented fixtures and keep real archives outside the checkout.

## Core checks

Instructions, templates and the invented example can be read and improved without
installing Helseark or creating a vault. Compare changes against the
[source and review checklist](examples/README.md). Preserve the
explicit person, exact numeric scale, citations and mandatory human review.

For automated checks, use Python 3.12 and uv (CI pins uv 0.11.2). Install only the
existing schema-validation dependencies from the repository root:

```sh
uv sync --locked --no-install-project --no-default-groups
uv run --no-sync python -m unittest discover -s tests -p test_examples.py -v
uv run --no-sync python - <<'PY'
from pathlib import Path
import subprocess
import sys

page = Path('docs/schemas.md').read_text()
command = page.split("python3 - <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
subprocess.run([sys.executable, '-c', command], check=True)
PY
git diff --check
```

The “Schemas and examples” workflow runs these checks on every pull request.
They protect this invented example, not arbitrary clinical truth or human approval.
New examples need corresponding focused checks. Dependency installation may access
registries; checks use local files. Keep uv's seven-day dependency freshness guard.
There is no configured linter yet; the [coding guide](docs/development/coding-guide.md)
defines review standards.

The [experimental CLI](docs/optional-cli.md) has separate optional Python/PDF setup
and a manually dispatched diagnostic suite. Work on it requires explicit scope;
passing schema and example checks does not qualify it or its distributions.

## Development workflow

1. Create a branch from main; use a separate worktree when another session uses
   the checkout. Suggested prefixes: `fix/`, `feat/`, `docs/`, `refactor/`.
2. Make focused commits with clear messages and tests for behavioral changes.
3. Run relevant validation and tests locally. Core checks run automatically in
   branch CI. Optional experimental suites require explicit manual dispatch.
4. Open a pull request with context and rationale, then monitor its CI results.
5. Resolve review comments with code or clear reasons. An independent reviewer
   checks each implementation before the coordinator integrates it.

Preserve other sessions' work. Do not amend others' commits, rewrite accepted
history, or merge without authorization. A plan or green tests do not grant agents
merge authority.

## Pull request guidelines

Describe the problem, approach and tradeoffs. Link the issue, provide test commands
and actual results, and state compatibility/migration effects and limitations.
Use the [PR template](.github/pull_request_template.md).

- Keep scope self-contained and inspect every staged file, including binaries.
- Update relevant tests, references, schema/CLI docs and agent descriptors/prompts.
- Run focused checks locally and confirm the relevant remote checks before
  claiming they passed.
- Keep fixtures synthetic, minimal, representative and deterministic; never upload
  real records, exports, screenshots, context packets or sensitive logs.
- Preserve offline operation, exact precision, person isolation, immutable history
  and review bound to final prepared bytes.

For changes to deployed production behavior, add `## Plano pós-merge` with each
signal's source/query, baseline, regression threshold/window and rollback.
Ordinary documentation and skill changes need only the validation section.

## Coding and testing standards

Follow existing style and module boundaries, prefer small functions and explicit
types, avoid unrelated refactoring, and comment only where intent is not obvious.
Keep public behavior deterministic and local-first. Add behavioral regression
coverage for bug fixes and representative success/edge cases for features. Use
real temporary filesystem/process boundaries for storage and crash tests. A mock
of the same implementation or a source-text assertion does not prove behavior.

## Schema and storage changes

Preserve compatibility where feasible. Document incompatibilities and migrations
when not; update the [archive format](docs/reference/archive-format.md),
[clinical model](docs/reference/clinical-model.md) and
[agent protocol](docs/reference/agent-protocol.md) as applicable. Contract, profile,
serializer and agent-kit versions remain independent. Preserve pinned upstream
bytes and use [vendoring guidance](definitions/README.md) for reviewed updates.

## Reporting and communication

Use the bug/feature issue templates with synthetic reproduction steps, expected
and actual behavior. Be respectful, specific and technical; discuss tradeoffs
with evidence and resolve review feedback. Do not publish vulnerabilities in
issues; follow [SECURITY.md](SECURITY.md) to request a private channel.

## License

By contributing, you agree that your project-authored contributions are licensed
under the [MIT License](LICENSE). You must have the right to submit
the material and identify third-party terms. Existing CC0 fixture dedications,
upstream licenses and retained historical notices remain intact; see
[licensing](docs/maintainers/licensing.md). No separate CLA or sign-off is required.
