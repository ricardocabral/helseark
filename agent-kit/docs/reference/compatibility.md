# Compatibility on this foundation

| Dimension | Supported new-vault value |
|---|---|
| Toolkit distribution | 0.1.0 (staged branch, not release qualification) |
| Python | 3.12+; focused local evidence may use a newer interpreter |
| Archive | 1 |
| Local contract / profile | 0.1.0 / 0.1.0 |
| FHIR | R4 4.0.1 |
| Serializer | helseark-json-1 |
| Agent protocol | 1 |
| Documentation kit | 0.1.15; exact manifest and definition-lock digest pinned per vault |
| PDF extra | pypdf 7.0.0, optional local text extraction |

Historical retained kits and locks are copied unchanged by backup and restore.
A version string alone does not establish equivalence: exact hashes and inventories
must match. Opening is not migration. No supported contract/profile upgrade pair,
FHIR R5 conversion, official-validator policy, OCR engine or structured adapter is
available in this branch. Unknown/missing pins produce typed errors instead of a
fallback or network lookup. New publication requires matching proposal/input
contracts; read-only historical compatibility does not promise new writes.

Local POSIX macOS/Linux filesystems are the intended boundary; remote platform CI
and independent integration review own broader qualification. Locks protect
cooperating writers. No Windows, network-filesystem or universal power-loss guarantee
is made. See [evolution](../explanation/evolution.md) and
[archive format](archive-format.md) for historical/durability limitations.
