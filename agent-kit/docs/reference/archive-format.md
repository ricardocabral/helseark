# Archive format 1 (Task 1)

This reference describes the implemented storage boundary. Offline baseline
clinical validation, evidence contracts and pinned agent discovery/context/rendering
are implemented; intake and reviewed import publication remain later tasks.
Person creation accepts a narrow self-reported identity only.
Validation is not a claim of medical correctness or full FHIR conformance.

## Commands

Python 3.12 or later and a POSIX environment are required.

```sh
uv sync --frozen
uv run helseark init /tmp/demo-health --json
uv run helseark --vault /tmp/demo-health person add --name 'Alex Example' --json
```

The init destination must not exist. Person options are `--name` (required),
`--birth-date` (optional real calendar year, year-month or date), `--note`
(optional self-reported identity note), and `--json`. A note stays in evidence;
it does not become a clinical assertion. Names are never identifiers.
Duplicate names produce separate people. No patient matching occurs.

`--vault PATH` is a global option before `person`; alternatively
`HELSEARK_VAULT` selects an explicit path. No parent-directory search occurs.
Machine successes use UTF-8 JSON on stdout; errors use safe JSON on stderr.
Human success output is the new vault path or person UUID. Input errors do not
echo supplied names, notes or birth dates.

| Exit | Meaning |
| --- | --- |
| 0 | Success |
| 2 | Invalid command/input, invalid person or existing destination |
| 3 | Review binding mismatch (reserved for the reviewed-import entry point) |
| 4 | `ARCHIVE_BUSY` or `STALE_BASE` |
| 5 | Integrity, unsupported path or I/O failure |
| 6 | Unsupported version |

## Files and pins

```text
vault.json
README.md
definitions/lock.json
definitions/schemas/0.1.0/*.schema.json
people/<person UUID>/accepted/<8-digit sequence>-<transaction UUID>/
    change.json
    proposal.json
    evidence.json
    validation.json
    review.json
    resources/Patient-<person UUID>.json
.runtime/writer.lock
.runtime/staging/<opaque UUID>/
```

`vault.json` contains no names. It pins archive format `1`, contract/profile
`0.1.0`, FHIR `4.0.1`, serializer `helseark-json-1`, the actual SHA-256 of the
copied definitions lock, and an independent vault UUID. Profile version pins the
supported baseline profiles, not full FHIR/terminology conformance. New vaults pin
the bundled agent-kit version and actual manifest digest. Historical vaults with
paired null kit pins remain readable; agent context requires a retained compatible
kit and never substitutes the latest installed release.
No absent artifact is assigned an invented digest or advertised as supported.

The six [local schemas](../../schemas/0.1.0/) use JSON Schema 2020-12 and
reject unknown envelope fields, including nested ones. Schema IDs are local
URNs. The [definitions lock](../../definitions/lock.json) inventories the exact
repository-authored schema bytes with their sizes and real SHA-256 values.
It makes no claim to contain upstream FHIR artifacts. Init copies and checks
these contracts offline; an installed wheel carries the same inventory.
Envelope validation has no remote references. Task 2 extends this inventory
with pinned official FHIR definitions, licenses and acquisition provenance.

Accepted JSON, copied definitions, vault identity and explanatory README are
the durable archive. Reading needs no database, roster, installed source
checkout, mutable HEAD, or runtime directory. The CLI needs its installed Python
dependencies. Ordinary JSON readers can inspect the files without that runtime.
A writer recreates missing runtime directories. Readers perform no repair.

An empty `accepted/` may remain for an unpublished person after process death;
its head is `None` and it has no accepted Patient. A missing accepted directory,
malformed change, sequence gap, checksum mismatch or symlink fails closed.
Opening a vault verifies all visible person histories; scoped reads verify
the selected person's entire visible chain, even for an older snapshot.

## Identity and revisions

IDs are lowercase UUID strings, and production preparation generates UUIDv4.
A Patient's logical ID equals its person-directory ID. Resource identity is
`(personId, resourceType, id)`. Each revision has its own UUID and UTC
`meta.lastUpdated`. An independently injectable clock and UUID factory support
deterministic tests; production always uses current UTC and fresh UUIDv4.

A resource inventory entry contains `type`, `id`, `versionId`, `sha256`,
`path` and nullable `supersedesVersionId`. An update must supersede the current
revision of exactly that logical resource; revisions cannot be reused within
the person's history. The relative path is exactly
`resources/<type>-<id>.json`. Current reads choose the last accepted revision.
Version-pinned reads retain their meaning after later changes.

Each person's graph and history are separate. A resource lookup never searches
another person. Full clinical subject/reference closure is Task 2's validation
responsibility; the internal publisher is not a clinical-import API.

## Retained proposal and review binding

Person creation makes the same retained envelopes as a normal change:

- `evidence.json` records explicit self-reported fields with `kind=user-entry`
  and generated IDs/meta with the `person-add-1` rule. The current evidence
  schema supports these identity entries; source locators belong to Task 2.
- `proposal.json` binds person, transaction, kind, candidate-input digest,
  base digest, version pins, resource/asset inventories and evidence digest.
- `validation.json` binds the proposal digest and records check coverage.
  The narrow Patient constructor passes; full FHIR and terminology are
  explicitly `not-checked`.
- `review.json` binds proposal bytes, validation bytes, person and base digest.
  The explicit `person add` action records a local-user decision about the
  entered identity. Its label does not authenticate a human identity.
- `change.json` binds all four envelope hashes, the prepared proposal hash,
  inventories, transaction, sequence, person, version pins and parent hash.
  It does not hash itself. Its digest becomes the next change's parent.

Changed resource, evidence, proposal or validation bytes invalidate the retained
bindings. Readers check both change inventory and proposal inventory. Failed
validation checks cannot be accepted. Import-specific issue acknowledgement,
source matching, clinical admissibility and interactive human review are
additional Task 2/6 responsibilities; there is no arbitrary-write CLI.

Assets, when supplied by later preparation, are person-local at
`assets/sha256/<digest>/blob`. Their entries contain SHA-256, byte size, media
type and path. The publisher verifies already-retained asset bytes; asset
intake and durable installation are not Task 1 APIs.

## Publication, recovery and durability

One vault-wide, nonblocking POSIX `flock` protects writes. A competing writer
receives `ARCHIVE_BUSY`. Locks release on process death; age never authorizes
stealing a lock. Never unlink or recreate the lock file while a writer is live.

Preparation occurs before publication. Under the lock the publisher rechecks
the exact `Head`, copies a symlink-free prepared tree into same-vault staging,
verifies the copied bytes, checks revision succession, generates the change,
flushes files and directories, and renames the entire directory into accepted
history. Directory rename is the commit point. An existing destination stops
publication. An I/O failure near that point requires reopening to determine
whether the complete change committed.

Readers ignore staging, scan consecutive accepted directory names and verify
the parent chain. A crash before rename leaves the previous accepted head and
unpublished staging. A crash after rename exposes the complete new change.
No accepted file is updated in place. Directory entries are flushed after
rename. Cross-filesystem rename fails rather than copying into accepted.

Orphan staging and empty unpublished person directories are retained. They
are not accepted facts and are never automatically promoted or deleted.
There is no `doctor` or automatic orphan-cleanup command yet. With all writers
stopped, an operator can preserve a full folder copy, inspect the retained JSON,
and move orphan staging aside. An offline copy of the whole vault while no
writer is active retains its interpretation and history. Backup/restore
verification tools are later work.

Test qualification: macOS 15 / Darwin 24.6.0, ARM64, local APFS, Python 3.12.8.
Real child processes terminate via `os._exit(91)` immediately before and after
rename, both for genesis and for a second revision. The internal environment
hook `_HELSEARK_TEST_CRASH_AT=before-rename|after-rename` exists only for these
tests and never skips a check. A separate child process holds the real OS lock.

These tests establish process-crash behavior on that filesystem, not
hardware power-loss guarantees. Flushes use `fsync`, without a macOS
`F_FULLFSYNC` hardware guarantee. Linux and Windows are unqualified. Network
filesystems, cloud-synchronized folders, concurrent Git merges and external
writers are unsupported; filesystem suitability is an operator responsibility,
not automatically classified by the toolkit. The advisory lock cannot control
external editors. Hashes detect accidental edits, but are not signatures.
A coherently rewritten archive or removal of the complete chain suffix cannot
be detected without an external trusted head/backup.

## Serialization: helseark-json-1

`encode_json(value) -> bytes`, `decode_json(data: bytes) -> JsonValue`, and
`hash_bytes(data: bytes) -> Sha256` live in `helseark.serialization`.

Bytes are strict UTF-8 without BOM, with LF, a final newline, two-space
indentation, sorted object keys, unchanged array order and string content.
Strings are not Unicode-normalized. Duplicate object keys, non-finite numbers,
binary floats, lone surrogates, malformed UTF-8 and nesting above 64 containers
are rejected. JSON decimal/exponent tokens become `Decimal`; integer tokens
become `int`. Fixed-form decimal rendering never rounds and preserves
fractional trailing zeros: `1.20` remains `1.20`.

The source reader `decode_json` applies the original independent limits:
token at most 1,024 characters, coefficient at most 128 digits (excluding
leading zeroes; all-zero coefficients count as one), absolute **explicit**
exponent at most 128, and fixed output at most 512 characters including sign
and decimal point, excluding final LF. It checks these before Decimal
construction or fixed expansion. There is no additional effective-exponent
limit. In particular `1e128`, `0e128` and `0.1e-128` are accepted.

Source limits are not closed under fixed rendering: `1e128` produces a
129-digit integer. Use `decode_canonical_json` for retained bytes produced by
`encode_json`, including all archive stored/prepared JSON readers. This is
an explicit bounded representation boundary, never a trusted/unbounded bypass:

- Numeric tokens must use fixed notation and fit in 512 characters.
- Fractional tokens have at most 128 coefficient digits after leading zeroes.
  Fractional scale can reach 510 unsigned or 509 signed, including zero.
- Integer tokens may have at most 256 digits excluding sign, but removing
  **at most 128 trailing zeroes** must leave at most 128 coefficient digits.
  An arbitrary 129-digit integer is therefore still rejected.
- Duplicate-key, Unicode, float, non-finite and depth restrictions are shared.
  This reader checks numeric representation, not exact whitespace/key order;
  hashes continue to bind the actual retained bytes.

These are exactly the fixed values/scales obtainable from permitted source
numbers. For an integer, the removed zeroes give a source coefficient and an
explicit exponent no greater than 128. Every permitted fractional fixed
token is itself an allowed source: its coefficient fits, explicit exponent
is zero, and token length is at most 512. Conversely, source expansion can
append at most 128 integer zeroes and cannot enlarge a fractional coefficient.
This proves representation closure.

`encode_json` accepts this canonical value domain for Python ints/Decimals,
including values whose *particular* scientific spelling would exceed source
limits. Source spelling limits belong to `decode_json`; encoding Python
values does not validate an unavailable original token. The contract is
`decode_canonical_json(encode_json(decode_json(source)))`: exact value and
fractional scale, with byte-stable re-encoding, independent of Decimal context.
Positive integer exponent spelling and integer negative zero are normalized;
fractional negative zero and trailing zeroes survive. Nothing is rounded or
truncated. Giant nonzero exponents are size-checked before expansion; zero with
nonnegative scale emits `0` directly without exponent expansion.

This restores originally permitted source inputs within `helseark-json-1`;
existing emitted fixed bytes remain readable. Integer Decimal negative zero
now emits `0` so its reread is byte-stable; the older `-0` remains readable.
No accepted bytes or original plan/design documents are rewritten. Callers
that previously used `decode_json` for encoder output must use the canonical
reader. Clinical source-token preservation remains later-task work.

SHA-256 identifies exact bytes; reformatting accepted JSON changes its digest.
This is a project serializer, not a claim of standards-based canonical JSON.

## Python API and Task 2 interface

Records and `ArchiveError(code, safeMessage, details)` are in
`helseark.contracts`. Default error messages omit private content; optional
details identify affected relative paths. JSON clinical resources stay trees,
with no duplicate local clinical model.

| Function in `helseark.archive` | Behavior |
| --- | --- |
| `init_vault(root: Path, config: VaultConfig \| None = None) -> Vault` | Creates an absent destination atomically with bundled contracts; default config pins their actual digest. |
| `open_vault(root: Path) -> Vault` | Verifies supported versions, definition bytes and accepted chains; no writes. |
| `add_person(vault, details: PersonDraft, *, clock=None, uuid_factory=None) -> PersonId` | Validates the narrow identity, prepares evidence/review, publishes genesis. |
| `head(vault, person) -> Head \| None` | Returns sequence, transactionId and changeSha256; None only for an empty accepted history. |
| `resolve(vault, person, ref: ResourceRef, at: Head \| None = None) -> FHIRResource` | Resolves a logical or pinned revision inside that person's verified snapshot. |
| `iter_current(vault, person, at: Head \| None = None) -> Iterator[FHIRResource]` | Yields latest revisions at the selected head in type/ID order. |

`ResourceRef(resourceType, id, versionId=None)` validates its type token and UUIDs.
`PersonDraft(displayName, birthDate=None, note=None)` has no mandatory birth date
or government identifier. `at=None` means current, not an empty snapshot.
An explicit Head must exactly match this person's history or `UNKNOWN_HEAD`
is raised. Missing person/resource raises `PERSON_NOT_FOUND` /
`RESOURCE_NOT_FOUND`. Neither lookup selects a different person.

The internal `_publish_change(vault, person, payloadDirectory, expectedBase)`
returns a Head after locking and verifying the prepared directory. That
directory contains exactly proposal/evidence/validation/review JSON and the
inventoried resource files; it must not supply `change.json`. Genesis uses
`expectedBase=None`; later publication requires the exact current Head.
It is an internal primitive for Task 6, not permission to accept arbitrary
FHIR. Stage material is retained on validation/publication failure for
inspection. Task 2 can use the verified file-scan readers immediately and
extend the provisional 0.1.0 envelopes before freezing them. Any schema change
must update the definitions lock's real inventory and its vault pin.

## Storage review qualifications

Vault roots may have symlink ancestors (for example macOS `/tmp` points to
`/private/tmp`). A symlink at the root itself is rejected, as are symlinks
beneath it. Both ancestor aliases address the same vault and writer lock.
This is a static-path policy for cooperating processes. Path checks followed
by pathname opens do **not** protect against hostile concurrent filesystem
mutation. Such writers remain unsupported; descriptor-relative traversal would
be needed before claiming that protection.

Stored malformed JSON, including duplicate keys and genesis files, is an
integrity failure (exit 5). Malformed external JSON remains `INVALID_JSON`;
invalid command/person input exits 2. Unsupported envelope contract or version
pins are checked before supported-schema constants and exit 6, including
genesis. No unknown version is interpreted as the current version.

Errors include safe `details.path` locations relative to the vault. Known
opaque file paths identify JSON/schema/resource/asset failures; inventory
failures identify the affected directory when no single expected file explains
the error. Unexpected names are omitted in favor of the nearest safe directory.
Absolute root paths and record values are never needed in these diagnostics.

For distribution qualification, build with the declared `setuptools==80.9.0`,
then rebuild the sdist outside the checkout. Install its wheel and locked runtime
dependencies into a fresh virtual environment. Copy
the repository maintainer script `tests/qualify_installed.py` outside the
checkout and run it with that environment's Python, passing a fresh work path
and the checkout path. It checks the installed module and bundled definitions,
the installer-generated console entry point, a copied vault without runtime
state, pinned resolution, and zero socket attempts under a verified blocking
audit hook. This qualifies runtime offline operation after dependencies are
installed; it does not promise installation on an empty offline machine.
