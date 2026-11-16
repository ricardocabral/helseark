# Contributor instructions

Current delivery is [Helseark's agent instructions, schemas and examples](README.md),
governed by [SCOPE.md](SCOPE.md). Prior application plans do not authorize restarting
deferred work. Keep the experimental CLI and legacy agent-kit intact; they are
optional, not prerequisites for organizing records with an agent. Internal plans
are historical context where they conflict with the approved scope.

- Follow [CONTRIBUTING.md](CONTRIBUTING.md), the [coding guide](docs/development/coding-guide.md), and [SECURITY.md](SECURITY.md).
- Public contributors use the references, tests, and self-contained issues. If private planning context is needed, ask the coordinator for public acceptance criteria; never publish internal plans.
- Maintainer agents: read the implementation plan and design in ignored `docs/internal` (in the primary clone if absent in a worktree). Never commit these documents or real health data.
- Workers use separate branches/worktrees. Preserve other sessions' changes. Do not amend or rewrite commits.
- Implement the assigned plan task completely, including behavioral tests and its documentation. Report limitations honestly.
- Use synthetic fixtures only. Preserve exact decimal precision, patient isolation, immutable accepted history, offline operation, and mandatory human review.
- The shipped `vocabulary/` contains authorized terminology, not patient fixtures.
  Preserve upstream fields/notices and source provenance. Alias retrieval never
  establishes clinical equivalence or human approval; normal lookup remains offline.
- Default checks cover schemas, agent instructions and the invented example.
  Run focused checks locally; the optional experimental CLI suite runs remotely
  through manual dispatch only when explicitly requested. Schema and example
  checks do not qualify CLI behavior or distributions.
- An independent reviewer checks each implementation before integration. Resolve findings and suggestions, documenting reasons for any declined suggestion.
- Only the coordinator integrates reviewed work into main and pushes. Include a concrete post-merge verification/rollback plan for production-changing PRs.
- Keep durable guidance here; CLAUDE.md imports this file.

## Rex tab lifecycle

- Coordinators close task-owned Rex tabs as soon as they are no longer needed. Before closing, inspect every pane's current process state; preserve active workers, user terminals, and uncertain states. A quiet terminal or observation timeout is not proof of completion.
- Save required handoff reports, exit status, and terminal/transcript evidence under ignored `docs/internal` before closing completed tabs. Closing a tab must not delete branches, worktrees, files, or pending review evidence.
- Launch worker/evaluation commands without `--keep-open` by default, redirecting their output to retained task logs. Use `--keep-open` only when a concrete inspection or handoff requires it, and close that tab immediately after the need ends.
- Workers finish by writing their handoff and exiting; the coordinator owns cleanup. Remove empty task-created coordination shells and retire completed waves after confirming no active or needed panes remain. Include tab cleanup in each wave's completion check.
