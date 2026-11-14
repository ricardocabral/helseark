# Independent versions and preserved meaning

Toolkit, archive layout, local contracts, clinical profiles, FHIR, serialization,
agent protocol and kit releases have different jobs. A newer Python package must
not reinterpret an accepted old revision under whichever definitions happen to be
installed. The vault pins the definition lock and kit manifest by digest and retains
their bytes; changes record the versions that explain their contents.

This documentation release gives newly initialized vaults a distinct kit inventory.
It does not update existing vaults. Backup/restore copies their historical releases
unchanged. Replacing a lock or editing vault.json to make a missing kit disappear
would destroy that continuity. Missing or incompatible artifacts fail explicitly,
without downloading replacements or choosing the latest installed kit.

There is no migration command here. Preserving an original verified archive is the
recovery route when a reader lacks its required contracts. Future migrations must
use explicit supported source/target pairs, preserve the source, validate the new
graph and inventory old/new mappings. FHIR R4→R5 is a semantic conversion and is
separate from a layout change. Neither losslessness nor reversibility follows from
successful JSON serialization. See [compatibility](../reference/compatibility.md).
