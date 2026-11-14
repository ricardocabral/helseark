# Security policy

## Status and scope

Helseark is pre-release software under implementation. No stable release or
long-term security support window is promised. Reports against current main are
welcome; maintainers may require reproducing older snapshots on current main.
Do not use this status as evidence of clinical correctness or production readiness.

Report suspected health-data disclosure, wrong-person access, review bypass,
accepted-history mutation, unsafe file access, parser resource exhaustion,
unintended network access and dependency vulnerabilities privately.

## Reporting

Use GitHub's [private vulnerability report](https://github.com/ricardocabral/helseark/security/advisories/new)
when enabled. Enabling and testing that channel is a publication requirement;
its presence here does not establish that it is active while the repo is private.
If unavailable, contact the [repository owner](https://github.com/ricardocabral)
to request a private channel. If no private contact is available, open only a
minimal issue titled “Private security contact requested”, without technical
vulnerability details, patient data or attachments. Wait for a private route
before sending the report. Do not put an exploit in a public issue or PR.

Provide the affected commit/version, OS/filesystem/Python, expected and observed
behavior, likely impact and a minimal synthetic reproduction. Never send a real
vault, source PDF, credential, packet, export or patient identifier. Redaction of
names alone does not make a clinical document safe to share.

Maintainers triage privately, agree on safe reproduction, prepare a reviewed fix,
run focused tests and branch CI, and coordinate an advisory and affected-version
information when appropriate. There is no guaranteed response or fix deadline,
bounty program, or authorization to access another person's data or systems.

## Limits and safe handling

Local files and backups need user-managed OS access controls and protection.
Hashes detect inconsistency; they are not encryption, an authenticity guarantee,
or protection against an attacker rewriting every binding. Household folders do
not enforce per-person secrecy against someone who can read the whole vault.
Prompts are not a sandbox. A cloud agent receives whatever packet you give it.
See [privacy and agent boundaries](docs/explanation/privacy-and-agent-boundaries.md).

If a secret or private record enters GitHub, stop sharing it, notify the owner
privately and revoke/rotate affected credentials. Preserve restricted incident
evidence; do not repeat it in logs or issues. Deleting a file from the latest
commit does not remove history, caches or forks. Any history cleanup requires
owner coordination and explicit authorization; do not rewrite shared history on
your own. Making a repository private again cannot recall public copies.
