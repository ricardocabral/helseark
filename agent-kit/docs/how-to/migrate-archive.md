# Migrate into a separate vault

Applies to toolkit 0.1.2, archive 1, contract/profile 0.1.0, FHIR R4 4.0.1,
serializer `helseark-json-1`, kit 0.1.16. See [compatibility](../reference/compatibility.md).
Migration changes storage layout, never clinical meaning or human review decisions.

1. Stop other writers. Create a verified backup outside the source:

   ```sh
   helseark --vault /data/original backup create --include-work --out /data/backup --json
   helseark backup verify /data/backup --json
   ```

2. Generate a plan in a file outside the source and destination. Inspect the exact
   versions, source heads, counts, required definitions, byte mappings, losses and
   blocked records. A successful v1-to-v1 plan is an identity copy. There is no
   production contract upgrade in this release.

   ```sh
   helseark --vault /data/original migrate plan --to-contract 0.1.0 --json > /data/plan.json
   ```

   An unknown target returns a blocked report and exit 6. `--to-fhir 5.0.0`
   returns a distinct `fhir-release` report and exit 6; no FHIR conversion applies.
   A selected-person agent context can assist assessment but cannot authorize or
   certify this whole-vault operation.

3. A human must review the plan. Copy its `planSha256` into the explicit review
   argument. The destination path must be absent, including an empty directory.
   This attests a local decision, not an authenticated reviewer identity.

   ```sh
   helseark --vault /data/original migrate apply --plan /data/plan.json --reviewed-plan-sha256 REVIEWED_DIGEST --into /data/migrated --json
   helseark --vault /data/migrated doctor --json
   ```

   Apply recomputes the plan from current bytes; changing any retained file or
   head requires a new plan and human review. It checks the complete graph under
   its retained definitions and compares every destination byte with the plan.
   Evidence pointers, sources, IDs, Decimal tokens, status and correction/review
   history are preserved. No import is accepted or reviewed on your behalf.

4. Compare queries for each person and inspect the returned mapping inventory
   (`migrations/PLAN_SHA256.json`). It is separate migration provenance, outside
   accepted history. Preserve the original vault and backup as rollback.

These shared receipts contain person UUIDs, historical heads and file paths/hashes
for the household. They survive later [person removal](manage-family.md), which
requires explicit approval of their retained local metadata inventory. They are
included in whole-vault backups and omitted from person exports.

## Interrupted operations

A process death leaves `.helseark-migrate-TOKEN/` beside the destination. It is
unpublished and contains an owner record, verified snapshots and possibly partial
Task8 export/restore staging. No automatic deletion occurs, even after success.
Keep that directory private: it contains copies of your archive.

Repeat the exact reviewed apply command with `--resume` to explicitly choose
resume. Ownership, source, plan digest, retained staging and output bytes are
checked again. Complete verified snapshots/restores are reused; partial Task8
staging is preserved and the boundary retries into fresh internal staging.
Unknown, corrupt or unsafe staging blocks; preserve it and recover from your
verified backup. Manual quarantine/discard is an explicit user choice outside
this command. Do not use another operation's staging or overwrite a destination.
If the destination already exists after a crash, run `doctor` and inspect its
mapping inventory; apply refuses to replace it.

## Test-only machinery demonstration

`--test-only-legacy` opts into `helseark-test-only-layout-0`, a synthetic wrapper
with the exact marker in `tests/fixtures/synthetic/migrations/` and a verified
whole-vault Task8 backup in `snapshot/`. Migration removes the `snapshot/vault/`
path prefix. It does not convert FHIR or rewrite accepted envelopes. Ordinary
vault open rejects the wrapper. This fixture is not a supported public release,
not a historical format claim and not evidence for future semantic conversions.

All operations use installed local files and fail on missing definitions; they
never download converters, packages, schemas, terminology or source attachments.
For recovery, use [backup and restore](backup-and-restore.md).
