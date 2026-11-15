# Main branch protection

This is the desired configuration and activation runbook, not evidence that
protection is active. Confirm live settings before claiming enforcement.

Use one native classic protection rule for exactly `main`, with:

- Pull requests and one approval from a human other than the PR author, with
  counted-approval access; dismiss stale approvals and resolve conversations.
- The exact required check `Validate documented starter example`, bound to the
  numeric GitHub Actions App ID observed on a successful check run. Require
  branches to be up to date before merging.
- Enforcement for administrators; force pushes and branch deletion disabled.
- No bypass allowances or added deployment, signing, or linear-history requirement.

CODEOWNERS routes review requests; it does not enforce this policy. Do not require
code-owner approval while the sole code owner must also author changes: that can
block the owner's pull requests. Agent review under the author's identity is not
an independent GitHub approval.

## Activation and verification

1. Record repository identity, `main` SHA, rulesets, classic protection and
   collaborator roles in restricted evidence. Name an owner-approved independent
   reviewer with counted-approval access before activation. Do not invite or grant
   access as part of this procedure. A 403 or 404 alone proves no protection state.
2. Integrate the reviewed all-PR starter workflow first, with separate merge
   authorization, and observe its successful check. Keep the main-push path filters,
   job name, read-only token, pinned Actions and five-minute timeout. The
   experimental CLI stays manual.
3. Refresh the settings and App ID from actual check runs. Reconcile drift and save
   old settings, the complete proposed API payload and a restore procedure in
   ignored `docs/internal/`. Obtain owner authorization for the exact remote change;
   apply only classic protection for `main`, without a duplicate ruleset. If the
   private repository's plan does not support protection, report the restriction;
   do not change visibility or weaken the policy.
4. Read back `main.protected` and every configured control, including the exact
   check/App binding, strict checks, review count, stale-review dismissal,
   conversation resolution, admin enforcement, force pushes, deletions and bypasses.
   JSON validation alone does not prove server acceptance.
5. With authorization, use a ready-for-review, conflict-free, up-to-date README-only
   validation PR. Inspect `gh pr checks` and `gh pr view --json
   headRefOid,isDraft,mergeable,reviewDecision,mergeStateStatus,statusCheckRollup`.
   Observe the named check on the current head or GitHub test-merge SHA, all required
   checks green, `isDraft: false`, `mergeable: MERGEABLE` and `REVIEW_REQUIRED` before
   approval. A real independent approval must resolve the review gate. Also retain
   successful core-change PR evidence. Do not merge validation PRs or probe direct
   pushes to main. Close a task validation PR only with authorization.

## Plano pós-merge

Include this plan in the workflow PR before its separately authorized merge.
Within 30 minutes of routing integration and protection activation, query branch
protection, rulesets and check runs, plus the first core and README-only PRs using
`gh pr checks` and the fields above. Record query, UTC time, SHA, sample count and
PR/check links in restricted evidence. Baseline is the reviewed candidate's passing
starter check and the captured protection snapshot. Target is one successful named
starter check per PR, all desired controls active and the independent approval gate
observed. Any missing/skipped/ambiguous check, unexpected automatic CLI run, bypass
or reviewer lockout is a regression: stop integration and repair routing in a
reviewed commit. If settings restoration is necessary, obtain owner authorization
and restore only task-changed settings from the snapshot; do not add temporary
bypasses or claim an unprotected launch is ready.

When renaming the check, coordinate the required-check setting and preserve all-PR
routing. Recheck reviewer access and bypasses periodically. Public security checks
have separate activation criteria; skipped private-repository jobs are not proof.

API reference consulted 2026-11-15:
[branch protection REST API](https://docs.github.com/en/rest/branches/branch-protection),
[protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).
