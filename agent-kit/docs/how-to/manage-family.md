# Manage a family archive

Every command selects a person UUID. Equal names remain separate identities.
Keep separate vaults when OS access permissions must differ. A vault owner can
read all people; this CLI is not a household access control system.

## Recoverable person removal

Inspect and preserve a verified [backup](backup-and-restore.md) first. Choose an
absent quarantine directory on the **same filesystem**, outside the active vault.

```sh
helseark --vault family erase plan --person PERSON --quarantine /same-disk/removed-person \
  --out person-removal.json --json
helseark --vault family erase apply person-removal.json --approve EXACT_PLAN_DIGEST --json
helseark --vault family erase restore /same-disk/removed-person --approve EXACT_PLAN_DIGEST --json
```

Read the complete plan before supplying its digest. It binds the vault identity,
all person heads, exact byte inventory, person-owned working/runtime/derived paths,
quarantine destination and known external destinations. Changed heads or scope
require a new plan and explicit approval. Unclassified person-linked work blocks
removal for manual isolation; shared data is never guessed safe to delete.
The roster is derived from active person directories and needs no database update.

In migrated vaults, inspect `retainedLocalMetadata` before approval. Each entry
identifies a shared migration receipt by vault-relative path, SHA-256 and size,
with the selected person's UUID and historical source head. Open those exact
receipts to inspect the retained accepted/source/work paths and hashes. These
household receipts remain in the active vault byte for byte, including metadata
about the removed person; deleting them would also remove another person's
migration history. Their inventory is bound to the removal digest. Added or
changed receipts require a new plan and approval, including when resuming apply.
If this residue is unacceptable, stop before apply and arrange explicit manual
disposition of shared history; this command does not silently remove it.

The result repeats `retainedLocalMetadata` and lists its active file locations
in `remainingKnownCopies`, alongside quarantine, known external copies and limits.
The quarantine journal and result also retain removal metadata. Restoring uses
the approved journal and recovers the selected bytes without rewriting receipts.

The operation moves the selected person's directory and identified disposable
copies to quarantine under the writer lock. It never rewrites accepted clinical
history or another person's files. `plan.json` is synced before moving anything.
After a failure, preserve both directories: rerun the identical approved apply
to resume, or restore with the same digest. Changed bytes, collisions and a changed
roster/head block recovery for inspection. Quarantine must remain at its planned
path. Cross-device copy/delete is intentionally unsupported.

Quarantine is recoverable removal from active use, **not secure deletion**.
The plan lists tool-recorded successful exports/backups and external packet paths
when known. Pre-existing/unknown copies, external agent logs, manually copied files,
snapshots, SSD remnants and shared exports can remain. This tool neither scans
all disks nor guarantees their erasure. There is no automatic purge command.
Individual-record hard erasure and automatic person merge are unsupported.

## Namespace failures and recovery limits

Apply and restore hold no-follow directory authorities for source and destination
ancestors and verify selected object identity and byte inventory before each
native no-replace rename. A changed ancestor or replacement selected object
observed before that move is rejected. Competing destinations are preserved.
Destination subdirectories and the initial synced plan journal are created through
held directory descriptors, rather than traversing a substituted symlink.

An error is **not proof that nothing moved**. Earlier moves, a process death, or
an ancestor renamed during the native syscall can leave approved bytes in a
partially completed operation. Descriptor-relative rename cannot redirect those
bytes through a replacement parent symlink, but the original held parent may now
have a different filesystem name. Preserve the active tree, planned quarantine,
`plan.json`, and any renamed original ancestors. Inspect their actual locations
and hashes before explicitly restoring the original namespace and retrying the
same plan. The tool never deletes or quarantines a competing/unrelated object to
make recovery succeed.

Use local OS permissions and cooperating writers. POSIX no-replace rename has no
atomic “move only if the source inode still equals this value” condition. A
noncooperating same-owner process can still replace the final source name between
the last identity check and the syscall, modify opened files, or rename a held
ancestor itself. An arbitrary vault/host owner can also rewrite plans/history.
The held descriptors, pre-move checks and quarantine journal correct ancestor
redirection and observed replacement failures; they do not provide owner-proof
security or a universal power-loss guarantee. Stop such writers before recovery.
