# Contributor instructions

- Read the implementation plan and design in ignored `docs/internal` (in the primary clone if absent in a worktree). Never commit these documents or real health data.
- Workers use separate branches/worktrees. Preserve other sessions' changes. Do not amend or rewrite commits.
- Implement the assigned plan task completely, including behavioral tests and its documentation. Report limitations honestly.
- Use synthetic fixtures only. Preserve exact decimal precision, patient isolation, immutable accepted history, offline operation, and mandatory human review.
- Run focused tests locally; full suites run on remote branch CI.
- An independent reviewer checks each implementation before integration. Resolve findings and suggestions, documenting reasons for any declined suggestion.
- Only the coordinator integrates reviewed work into main and pushes. Include a concrete post-merge verification/rollback plan for production-changing PRs.
- Keep durable guidance here; CLAUDE.md imports this file.
