# Security policy

## Supported versions

Security maintenance targets the latest code on main; older snapshots
have no separate support promise. Helseark is still under implementation and has
no stable release. This policy makes no claim of clinical correctness or release
qualification.

## Reporting a vulnerability

Do not publish vulnerabilities in public GitHub issues or pull requests.

Report vulnerabilities privately to [ricardo@rnc.sh](mailto:ricardo@rnc.sh).
You can also use [GitHub private vulnerability reporting](https://github.com/ricardocabral/helseark/security/advisories/new)
when available. Do not include vulnerability details in public issues or pull requests.

Include affected version/commit, OS/Python/filesystem, expected and actual
behavior, reproduction steps or proof of concept, likely impact and suggested
remediation if known. Use synthetic records only. Never send a real vault, source
PDF, packet, export, credential or patient identifier. Removing names alone does
not make a health document safe to share.

Reports may concern disclosure, wrong-person access, review bypass, accepted-history
mutation, unsafe file access, parser resource exhaustion, unintended network access
or dependency vulnerabilities. This policy does not authorize access to anyone
else's systems or data and does not establish a bounty program.

## Vulnerability disclosure process

Maintainers aim to acknowledge receipt within seven
days and provide a status update within fourteen days when possible. These are
targets, not guaranteed response times. Confirmed vulnerabilities receive a
reviewed fix and focused tests plus branch CI. Maintainers coordinate disclosure
with the reporter, targeting public disclosure within ninety days of confirmation
or after a fix is available unless another timeline is agreed.

## Data handling and incidents

Local files/backups need user-managed OS protection. Hashes are not encryption
or proof of clinical truth. Household folders do not enforce per-person secrecy
against someone able to read the vault. Prompts are not a sandbox; cloud agents
receive the packets users share. See [privacy boundaries](docs/explanation/privacy-and-agent-boundaries.md).

If private data or a secret reaches GitHub, stop sharing it, notify the owner
privately, rotate affected credentials and preserve restricted incident evidence.
Deleting the latest file does not remove history, caches or forks. Coordinate
cleanup with the owner; never rewrite shared history without authorization.
Changing visibility cannot recall public copies.
