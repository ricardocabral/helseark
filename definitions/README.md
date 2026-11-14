# Pinned upstream definitions: maintainer guide

This directory retains an exact-byte **subset** of official FHIR R4 4.0.1:
64 StructureDefinitions, original package metadata, the complete combined
Draft 6 JSON schema, 15 selected R4 HTML pages, and the CC0 legal text.
[upstream-inventory.json](upstream-inventory.json) records all 82 file pins,
18 source pins, archive members, provenance and original acquisition date.

The StructureDefinitions close `baseDefinition` and snapshot `element.type.code`
for Patient, Observation, DiagnosticReport, Specimen, DocumentReference,
Provenance and Bundle. This is not closure of `targetProfile` canonicals or
terminology bindings. Unchanged `package.json` does not make this a complete
installable core package. The selected HTML is not a complete offline website;
linked assets/pages may require networking when opened in a browser.

The broader requirement to distribute a complete pinned core package and full
archival specification remains open for later integration. So do distribution
packaging, digest-binding this inventory into the shared lock, runtime offline
resolution, clinical profile rules and optional Java/dependency/terminology
validation. This script verifies vendored materials; it does not establish
clinical conformance or extraction correctness.

## Verify and reproduce

From the checkout root, using Python 3.10+ and its standard library:

```sh
python3 -B scripts/vendor_definitions.py --verify
python3 -B -m unittest discover -s tests -p test_vendor_definitions.py -v
```

Omitting `--verify` also performs offline verification. An empty/incomplete tree
fails without fetching. The focused tests block socket events, use tiny synthetic
archives in temporary directories, exercise real urllib redirect processors and
verify the real committed installed inventory. They need no source-cache fixture,
network, or third-party test dependency.

Acquisition is an explicit maintainer operation:

```sh
python3 -B scripts/vendor_definitions.py --fetch --cache-dir /path/to/source-cache
python3 -B scripts/vendor_definitions.py --fetch --root /path/to/staging --cache-dir /path/to/source-cache
```

For staging, first copy the reviewed inventory to
`/path/to/staging/definitions/upstream-inventory.json`. Cache names are source
SHA-256 values. A complete verified cache reproduces the selection offline;
a missing source requires the pinned endpoint. Cache tampering fails closed.
Retain source blobs separately for reproducibility if official endpoints change.
Pins are locally acquired HTTPS trust pins, not upstream authenticated signatures.
Re-pinning requires independent source, license, selection and inventory review;
the script never learns new hashes or rewrites the shared lock.

Initial URLs remain restricted to the inventoried official R4 paths and exact
CC0 endpoint. Before dispatch, initial network requests and every redirect must
use HTTPS and an exact reviewed authority: `hl7.org` or `creativecommons.org`.
Relative redirects are resolved by urllib and checked under the same policy.
User information, explicit ports, alternate hosts and HTTP are refused. Redirect
paths may differ from the initial pinned path; response bytes must still match
the original source pin. Any new authority requires an explicit policy review.

## Publication and interruption recovery

All acquired sources, selected members, pins and semantic checks pass before any
artifact publication. Each cache blob or missing artifact is written to a unique
same-directory `.vendor-*.tmp` file, flushed and fsynced, then published with a
hard link that cannot replace an existing destination. Existing changed bytes
and symlinks are refused. Filesystems without hard-link support fail safely.
This protects individual file publication; the complete distribution is not one
atomic transaction, and this is not a power-loss durability guarantee or defense
against concurrent adversarial directory replacement.

After a killed process, destinations are absent or contain complete bytes.
Retry `--fetch` to fill missing artifacts, then run `--verify`. A killed process
may leave a partial or complete `.vendor-*.tmp` file in an output/cache directory.
Verification intentionally reports leftover output files as uninventoried.
Once no vendoring process is active, inspect the exact reported path, confirm it
is a regular task-owned temporary file from this run, and remove **only that
file** before re-verifying. Do not recursively clean directories or remove files
by broad wildcard. The interruption test reproduces write/before-link/after-link
termination and this exact temporary-file cleanup.

Older script versions could leave a partial file under its final artifact/cache
name. Such changed bytes remain refused, including on retry. Preserve evidence,
confirm the exact file against the reviewed inventory, then remove only that
known corrupt file in the staging tree or source cache and retry acquisition.
Do not use this as permission to delete changed installed files in a working
checkout; investigate or reproduce into a fresh staging tree first.

## Bounds and retained notices

The 16 MiB limit bounds each downloaded source blob; reads stop at its pinned
size plus one byte. The 8 MiB limit bounds each selected output file. Selected
archive sizes and hashes must match before publication. These are **not**
aggregate decompression, archive metadata, member-count or full tar-traversal
bounds. The exact reviewed source pins and official fixed archives are part of
the trust assumption; re-pinning arbitrary hostile archives changes it. Members
are read as bytes, never extracted to paths. Unselected paths/links cannot become
output paths; selected tar links are rejected, and selected ZIP entries marked
as links are published as ordinary files containing the entry bytes.

Keep all original notices and bytes, including CRLF and BOMs. Original metadata
declares CC0-1.0; see [R4 notices](docs/r4/license.html) and
[CC0 text](docs/r4/cc0-1.0.html). HL7/FHIR trademarks and referenced third-party
terminology rights remain subject to their upstream exceptions. No terminology
expansions or blanket rights to third-party terminology are supplied here.
