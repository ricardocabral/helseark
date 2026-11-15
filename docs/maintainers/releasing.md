# Publishing Helseark

Before the first public launch and each release, record a responsible person,
exact candidate commit/tag, date, evidence location,
result and unresolved findings for each item. Store sensitive scan/review evidence
in ignored `docs/internal/`, not public issues or uploaded CI artifacts. A failed,
empty or wrong-context read is not a pass.

- [ ] Confirm the candidate matches [current scope](../../SCOPE.md) and has
  independent review. Check the agent instructions, three templates, schema
  references and invented source/FHIR/evidence example; verify their links and
  the [core checks](../../CONTRIBUTING.md#core-checks). Preserve explicit identity,
  exact precision, source evidence, accepted history and mandatory human review.
  Schema validity does not establish clinical truth or approval.
- [ ] Review [licensing.md](licensing.md) and the MIT license/metadata. Confirm
  provenance and redistribution rights for code, fixtures, brand and vendored
  material, and include notices in each artifact.
- [ ] Review the candidate tree AND all Git history/refs that will become public,
  including branches/tags, LFS, PR content, issue attachments, Actions logs/artifacts,
  release assets and hosted documentation. Run an approved secret scanner over
  those refs with version/config recorded. Have a human inspect synthetic-data
  provenance and binary assets; secret scanners do not identify all health data.
  Confirm no internal plans, real records, tokens, private paths or packets leak.
  `.gitignore` does not remove tracked or historical content. Coordinate any
  cleanup separately; never rewrite history without explicit authorization.
- [ ] Verify account access and least-privilege tokens, collaborator roles and
  two-factor authentication. Confirm CODEOWNERS resolves to an active maintainer.
- [ ] Configure main protection/rulesets: PRs, independent approval, required
  checks using the actual CI job names, resolved conversations, no force pushes
  or branch deletion. Verify that the rules are enforced; CODEOWNERS alone is not
  a merge gate. Review bypass permissions and restrict Actions token defaults.
- [ ] Establish and test a private security contact before changing visibility.
  Enable GitHub private vulnerability reporting as soon as available (the feature
  requires a public repository); verify a responder receives reports immediately
  after launch. Resolve conduct contact and owner-conflict
  escalation before inviting public participation. Replace temporary contact
  instructions with working private routes; never solicit sensitive issue details.
- [ ] Enable dependency graph/alerts, supported security updates, secret scanning
  and push protection where available. Verify CodeQL, dependency-review and OpenSSF
  Scorecard jobs after
  public launch; they are gated off while the repository is private. Their Actions
  are SHA-pinned, with scoped permissions. CodeQL uses v4 because
  v3 is approaching retirement. Confirm Dependabot reads uv.lock
  and opens grouped security update proposals without auto-merge. Routine version
  update PRs are disabled; review the weekly update-job results
  and handle deliberate version upgrades separately. Do not bypass uv's cutoff or
  the PDF runtime version guard to get a bot update merged.
- [ ] Require green “Schemas and examples” checks for the exact candidate commit. Inspect
  the portable files being published for missing schemas, broken relative links,
  private content and omitted licenses/notices. Record the candidate and actual
  results; there is no universal wheel/sdist or installed-platform gate for this
  installation-free delivery.
- [ ] Document the published scope, compatibility references, known limits,
  security support status and instructions for copying and using the files. Tag
  the reviewed commit and publish only with owner authorization and least-privilege
  credentials.
- [ ] Owner authorizes the visibility change separately after reviewing evidence.
  Public copies cannot be recalled by making the repository private again.

## Release and follow-up

For each production-changing PR, declare `## Plano pós-merge` before merge: each
signal's source/query, baseline, regression threshold/window and rollback. For policy/configuration
changes, check README/templates/policy links and the
first relevant automation run after integration. Baseline is the reviewed files
at the candidate commit; any missing/broken route or failed update job within
seven days requires correction or reverting the affected configuration. Do not
claim bots or remote protections work until their results are observed.

Check the first core-relevant pull request and main push after workflow changes:
one “Schemas and examples” job should run and pass its documented example and consistency
checks, with no automatic “Experimental CLI (manual)” run. Inspect the Actions runs
for that commit. Investigate any failed core check or a job that exceeds its
five-minute timeout. If routing breaks, revert the workflow change and rerun
the core check. Record remote results only after observing them.

The experimental CLI and historical qualification scripts remain available.
A runtime release requires separate scope and qualification for its promised
behavior and platforms; schema and example checks provide neither. This checklist does not
authorize a runtime release or expand its support claims.

Guidance consulted on 2026-11-14:
[GitHub community files](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file),
[private vulnerability reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository),
[Dependabot options](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference),
[preventing data leaks](https://docs.github.com/en/code-security/tutorials/secure-your-organization/prevent-data-leaks).
