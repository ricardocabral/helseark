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
