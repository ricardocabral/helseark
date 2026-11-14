# Back up and restore offline

Use an installed compatible Helseark release. All paths below are explicit local
folders. Backups contain sensitive records; choose storage and encryption yourself.
No remote destination, telemetry or repository is configured.

```sh
helseark --vault ./family doctor --json
helseark --vault ./family backup create --out ../family-backup --json
helseark backup verify ../family-backup --json
helseark backup restore ../family-backup --into ../restored-family --json
helseark --vault ../restored-family doctor --json
```

The destination must be absent, including an empty directory or symlink. Backup
destinations must be outside the vault, including through ancestor symlinks.
Enumeration, canonical verification and copying hold the vault writer lock.
Concurrent compliant writers return ARCHIVE_BUSY. Restore validates the complete
folder before staging; the staged vault is verified again, synced and published
with an atomic no-replace rename. A destination created during restore is preserved.

Format 1 accepts regular folders only. ZIP and tar inputs, symlinks, special files,
unsafe inventory paths, duplicate paths, extra/missing files and digest failures
are rejected before extraction or publication. There is no archive extraction
feature. Retain the bundle unchanged if verification fails.

The backup retains vault identity, exact accepted histories, proposals, candidate
inputs, review/validation/evidence envelopes, original and extraction assets and
their receipts, pinned definitions, pinned agent kits and explanatory files.
Archived pins are copied unchanged. Work is excluded unless `--include-work` is
explicitly supplied; it may contain sensitive unaccepted records. Derived state
and `.runtime` are excluded. Deleting all work does not remove accepted review
verifiability. Unaccounted files and incomplete staging block backup pending
inspection; they are never silently deleted.

Inspect `export.json` with an ordinary JSON reader: `files` records relative
paths, SHA-256 and byte lengths for every other file. `vault/` is the recoverable
vault, including its README, offline definitions and format reference. Copying
only collection.json is not a backup. The manifest itself is not signed.

Doctor reports actual checkedChanges, checkedResources (immutable revisions),
checkedAssets (distinct inventoried blobs), issues and orphanPaths. Errors halt
dependent operations. Counts of zero never establish nonempty corpus coverage.
Each issue carries an affected relative path and recovery action. Preserve
corrupt history, missing-predecessor evidence, staging and orphan files; restore a
complete chain from a separately verified backup into another absent directory.
Never skip changes, repair hashes or repin definitions to hide damage.

A plain whole-folder copy is also possible while every writer is stopped. Verify
it and practice recovery before relying on it. Advisory locks protect cooperating
processes, not arbitrary filesystem writers. SHA-256 chains detect accidental
changes; a writer able to replace the entire history can recompute them. They
provide neither authenticity nor protection against rollback to an older complete
vault. The filesystem must support local POSIX locking, fsync and atomic directory
renames. No power-loss, network filesystem or Windows guarantee is claimed.
Atomic no-replace publication is implemented for macOS and Linux; other platforms
fail explicitly. Keep independent backups.

A restore drill should use at least two people and one amended clinical result.
Compare accepted bytes, source hashes and query facts after removing work,
derived and runtime state, in a fresh installed process with network denied.
Record nonzero integrity counts beside the result. An empty-vault check cannot
qualify clinical recovery.

See [person exports](export-records.md) for exchange snapshots and
[archive format](../reference/archive-format.md) for accepted authority.
