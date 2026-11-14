# Contributing to Helseark

Helseark is under active implementation. Public availability is planned after
implementation and the [publication checks](docs/maintainers/public-release.md).
Read the [code of conduct](CODE_OF_CONDUCT.md), [security policy](SECURITY.md),
and [coding guide](docs/development/coding-guide.md) before contributing.
Never submit real health records, even with names removed. Use invented fixtures.

## Start here

Search existing [issues](https://github.com/ricardocabral/helseark/issues) and
[pull requests](https://github.com/ricardocabral/helseark/pulls). Small fixes can
be submitted directly; discuss changes to archive contracts, clinical semantics,
dependencies or supported platforms before implementing them. A maintainer
coordinates scope; a contribution is not a promise of acceptance or a release date.

The public references and tests describe implemented behavior. Maintainer planning
and coordination evidence stays in ignored `docs/internal/`; contributors do not
need access to it. Ask for a self-contained public issue with acceptance criteria
when context is missing. Do not copy private plans into issues or commits.

## Set up a checkout

Use Python 3.12 and uv (CI currently pins uv 0.11.2). macOS and Linux are the
qualified targets; do not infer Windows support from Python compatibility.
Create a branch, or a separate worktree when another session uses the checkout.

```sh
git clone https://github.com/ricardocabral/helseark.git
cd helseark
git switch -c your-change
uv sync --locked --extra pdf --group dev
uv run --no-sync helseark --help
```

Installation can access package registries. Normal archive operations must stay
offline. Keep demo vaults and output outside the checkout. The README's synthetic
example is a safe starting point; never point tests at an existing family vault.

## Make and verify a change

- Preserve the [coding and data contracts](docs/development/coding-guide.md).
- Add behavioral regression coverage for changed behavior. Use real temporary
  filesystem/CLI boundaries for storage and crash behavior, not mocks of the
  implementation. Documentation-only fixes need link/example checks.
- Run the smallest relevant checks locally, for example:

  ```sh
  uv run --no-sync pytest tests/test_cli_journey.py -q
  python3 -B scripts/vendor_definitions.py --verify
  git diff --check
  ```

- Let branch CI run the full Linux/macOS suite and package builds. Report which
  checks ran and their results; an unexecuted test is not passing evidence.
- Update the relevant references, agent task descriptors/prompts and compatibility
  records when a supported command or contract changes. Do not casually regenerate
  pinned artifacts; follow their maintainer guides and review resulting hashes.

## Submit for review

Keep each pull request focused. Explain the problem, resulting behavior, relevant
issue, tests and limitations. Inspect every staged file, including binary assets,
for health data, secrets, local paths and unrelated edits. Use the PR template.
Independent review and passing required CI precede integration. Only the
coordinator integrates and pushes main; agents need explicit merge authorization.
Do not amend others' commits or discard another session's work.

Production changes include a `## Plano pós-merge` section: for each signal give
its source/query, baseline, regression threshold and window, plus rollback steps.
A docs-only PR may state that no production behavior changes. Never repair a
release by rewriting accepted patient history.

By contributing, confirm that you have the right to submit the material and
identify third-party sources and their terms. See [licensing](docs/maintainers/licensing.md)
for the current license decision and exclusions. No separate CLA or commit sign-off
is currently required. Do not submit material whose terms are incompatible with
the project's chosen license.
