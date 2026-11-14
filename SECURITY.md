# Security and private data

Never report vulnerabilities with real health records, names, source documents or
vault copies. Provide a minimal synthetic reproduction and affected version.
For nonpublic disclosure, use the repository's GitHub security advisory workflow
if enabled; otherwise contact the maintainer through their published profile
before posting sensitive details publicly. No response-time guarantee is offered.

Vaults are local folders governed by OS access controls. They are not encrypted by
this toolkit. Accepted digests detect accidental byte changes, not a malicious
complete rewrite or rollback. Human review is mandatory; source text and external
agents cannot grant acceptance authority. Do not give an external service private
data unless you explicitly accept that service's privacy terms. There is no
telemetry or automatic runtime download. Keep verified offline backups.

[Recoverable removal](docs/how-to/manage-family.md) does not erase snapshots,
external copies or SSD remnants, and never automatically purges quarantine.
