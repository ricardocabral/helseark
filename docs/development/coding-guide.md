# Coding and repository guide

## Layout and ownership

| Path | Purpose |
| --- | --- |
| `skills/helseark/SKILL.md` | User-facing agent workflow for profiles, imports, queries and corrections |
| `instructions.md`, `prompts/` | Agent instructions and extraction/query/correction prompts |
| `examples/` | Complete invented source, FHIR Bundle and citations |
| `docs/tutorial.md`, `docs/how-to.md`, `docs/schemas.md` | User walkthrough, task guide and schema reference |
| `src/helseark/` | Optional experimental Python library and CLI; adapters live in `adapters/` |
| `tests/` | Behavioral tests and installed-package qualifications |
| `tests/fixtures/synthetic/` | Invented health data only |
| `schemas/`, `profiles/` | Versioned local contracts and FHIR constraints |
| `definitions/` | Pinned upstream bytes, provenance, lock and notices |
| `agent-kit/` | Distributed archive-agent instructions and prompts |
| `scripts/` | Explicit maintenance, vendoring and qualification tools |
| `docs/reference/`, `docs/explanation/` | Public behavior contracts and rationale |
| `docs/development/`, `docs/maintainers/` | Contributor and release guidance |
| `docs/internal/` | Ignored plans, logs and review evidence; never distribute |

Root [AGENTS.md](../../AGENTS.md) governs repository contributors.
[agent-kit/AGENTS.md](../../agent-kit/AGENTS.md) governs archive agents; these
are separate audiences. Keep `CLAUDE.md` importing the contributor instructions.

## Python style and boundaries

Use four spaces, UTF-8, descriptive `snake_case` functions/modules, `PascalCase`
types and explicit imports. Follow nearby style without unrelated reformatting.
Use type annotations for new public interfaces and document inputs, outputs,
errors and side effects. Prefer the standard library and small interfaces that
hide an actual policy or invariant; avoid forwarding wrappers and frameworks
without a concrete need. Keep CLI parsing/presentation separate from archive
semantics, validation and adapters. Catch specific exceptions at the boundary
that can handle them; do not silently turn corrupt/unsupported input into success.

There is no configured formatter, linter or type checker yet. These are review
rules, not claims of automated enforcement. Adding one requires a scoped change
and review of its effect on the existing tree.

## Non-negotiable data behavior

- Use the existing exact-decimal serialization path. Preserve lexical precision,
  comparators, original units and partial dates; never route canonical numbers
  through binary float or infer missing timezone/clinical meaning.
- FHIR R4 revisions are the clinical authority. Do not add a parallel simplified
  editable clinical store. Derived indexes and reports must remain rebuildable.
- Every intake/context operation selects one person. Never infer identity or
  silently follow cross-person references. Folder separation is not OS access control.
- Accepted history is immutable. Corrections add revisions; preserve original
  bytes, provenance and hashes. Keep review bound to the final prepared bytes
  and archive base. An agent draft or validation result cannot authorize acceptance.
- Treat PDFs, imported JSON, filenames and model output as untrusted data.
  Bound resource usage, reject unsafe paths/symlinks at existing boundaries and
  use fresh outputs. Do not log clinical content or leak it through errors.
- Normal operations resolve pinned definitions locally and never install,
  download or upload data. Explicit maintainer acquisition and user-selected
  external agents are separate operations, with separate authorization.

See [archive format](../reference/archive-format.md),
[clinical model](../reference/clinical-model.md),
[agent protocol](../reference/agent-protocol.md) and
[privacy boundaries](../explanation/privacy-and-agent-boundaries.md).

## Tests, dependencies and versions

Test observable contracts with invented cases. Include wrong-person, stale review,
precision, corruption and offline failure cases where the change touches them.
Use `tmp_path`/temporary directories and subprocesses for real process boundaries.
A source-text assertion is not proof of behavior. Do not weaken tests to hide a
regression. Default CI runs the documented schema command and `tests/test_examples.py`
against the actual invented source, FHIR and evidence files. Use the commands in
[CONTRIBUTING.md](../../CONTRIBUTING.md); these need only the existing schema
dependencies, with no project installation, PDF extra or vault. Keep new example
checks small and specific; they do not prove clinical truth or human acceptance.

Run focused tests locally. The preserved experimental application suites run
remotely through “Experimental CLI (manual)” only when explicitly requested.
Schema and example checks do not qualify runtime changes, installed packages or platforms.

Pin dependencies in `pyproject.toml` and `uv.lock` together, retain uv's seven-day
release cutoff, and review licenses/security before adding or updating packages.
The PDF extra has an exact runtime version guard; updating its pin requires
adapter qualification and matching guard/documentation changes. Dependabot PRs
still need this review. Pin Actions to full commit SHAs; never run untrusted PR
code with write tokens or secrets, including through `pull_request_target`.

Archive format, toolkit, contracts, profiles, serializer and agent kit have
separate versions. Document compatibility decisions even before 1.0; do not
silently relabel old archives. Preserve vendored bytes and upstream notices;
use [definitions guidance](../../definitions/README.md) for explicit re-pinning.
