# Archival definitions bundle

This maintenance tool delivers the complete published **HL7® FHIR® R4 4.0.1**
core package and downloadable specification as a standalone ZIP. It supplements
the reviewed bounded definitions in the repository. It does not change the
runtime registry, shared definition lock, wheel contents or validation coverage.

## Build and verify

Python 3.12+ and its standard library are sufficient; no project install,
Java, server or network is required with a populated cache. From the repository:

```sh
# Explicit maintainer acquisition; only missing pinned blobs may be downloaded.
python3 scripts/build_archival_bundle.py --fetch
# Default build is cache-only; a missing or corrupt input fails explicitly.
python3 scripts/build_archival_bundle.py \
  --cache-dir dist/archival-cache --output dist/archival-copy.zip
python3 scripts/build_archival_bundle.py \
  --verify dist/helseark-fhir-r4-4.0.1-archival.zip
shasum -a 256 dist/helseark-fhir-r4-4.0.1-archival.zip dist/archival-copy.zip
```

Every output path must be new. Existing outputs and corrupt cached blobs are
never overwritten or repaired. Source archives are cached as `<sha256>` without
an extension. A failed acquisition is discarded; publication uses a temporary
file and an atomic hard link on the same local filesystem. Concurrent builders
must use different output paths. Cache inputs must remain unchanged during a
build; this is a trusted local maintainer workspace, not a multi-writer service.

`definitions/archival-sources.json` independently pins each exact source URL,
byte size, SHA-256, acquisition date, license provenance and archive membership
summary. It does not modify `definitions/lock.json`. Acquisitions only use the
reviewed HTTPS authorities `hl7.org` and `creativecommons.org`; redirects are
checked before dispatch. There are no retries against alternate mirrors or
moving package registries. Pins must be reviewed and updated explicitly if an
official download changes. Recorded HTTP Last-Modified is server metadata, not
proof of the original release date or a cryptographic publisher signature.

## Contents and completeness

| Bundle path | Meaning |
| --- | --- |
| `sources/<sha256>` | Entire original downloads, byte for byte |
| `definitions/archival-sources.json` | Reviewed source pins and provenance |
| `inventories/{core,specification,schema}.json` | Every original archive member, including directories, with size/type and file SHA-256 |
| `licenses/hl7-license.html` | Exact versioned HL7 license page |
| `licenses/specification-license.html` | Exact license page inside the whole specification ZIP |
| `licenses/core-package.json` | Exact core package identity/version/license declaration |
| `licenses/cc0.html` | Exact CC0 1.0 legal text |
| `manifest.json` | Size/SHA-256 of every other bundle file |
| `README.md`, `docs/reference/archival-bundle.md`, `scripts/build_archival_bundle.py` | Offline instructions and the standalone builder/verifier |

The source pins also retain the official downloads page and combined JSON Schema
ZIP. Source `filename` fields identify how to name cached blobs for conventional
archive tools. The source archives are deliberately nested without extraction:
the 35,698-member specification is not reduced to selected resource pages. Its
`index.html` is the upstream entry point; most files are under `site\\` in the
original ZIP. The specification download excludes separate downloads according
to HL7, so the core and combined schema downloads accompany it explicitly.

The complete core has 4,742 members (4,739 files, three directories), including the
package metadata, indexes and all definitions/terminologies HL7 put in that
package. The specification has 35,698 files. These counts describe these pinned
bytes, rather than every dependency that a FHIR implementation might need.

Membership hashes are SHA-256 over UTF-8 JSON: sorted object keys, two-space
indentation, ASCII escaping, final LF; records sorted by their **original** path.
A file record contains `path`, `type: "file"`, `size`, `sha256`; a directory record
has `type: "directory"`, size zero and no digest. Member SHA-256 covers the whole
uncompressed file. Source SHA-256 covers the entire original compressed archive,
including metadata not represented in member inventories. Both checks are needed.
The verifier checks outer membership and hashes, source hashes, recomputes every
inner member hash/summary, compares full inventories and retained license bytes.
Version 1 requires exactly six source roles: `core` (tar.gz), `specification`
(ZIP), `schema` (ZIP), and raw `downloads`, `hl7-license`, `cc0` pages. Every
archive must contain nonempty regular-file content; the core package identity,
R4 version and CC0 license are checked on both build and verify. Empty pins or
omitted core/specification sources cannot describe a complete bundle. Exact
source bytes and complete inventories must still match independently reviewed
pins; structural checks do not authenticate a publisher or prove that arbitrary
replacement pins contain the genuine full release.

The verifier also enforces the versioned structure independently of the
self-declared manifest: README, standalone builder, this reference, embedded
pins, all six blobs, all three inventories and four notices. The required notices
are `licenses/core-package.json` from `core:package/package.json`,
`licenses/specification-license.html` from `specification:site\license.html`,
and the exact raw pages in `licenses/hl7-license.html` and `licenses/cc0.html`.
Support files must be nonempty and fit the metadata limit. Removing support or
notices and rewriting the inventory does not make an acceptable archive.

The manifest omits itself to avoid a circular digest. Obtain the outer ZIP digest
from the independently retained release record; a manifest alone does not prove
authenticity against a malicious replacement.

Upstream ZIP member names use backslashes. Inventories preserve them exactly;
safety checks interpret both slash forms as separators. No upstream path is ever
extracted by the builder/verifier. Absolute paths, traversal, drive/ADS syntax,
noncanonical components, duplicate/case-colliding paths, file/directory
collisions, links, sparse files, devices and encrypted ZIP members are rejected.
Source size is bounded to 512 MiB; each expanded member to 256 MiB; total expanded
size to 2 GiB per archive; membership to 100,000; metadata to 32 MiB. Decompressed tar envelopes
(including padding and extended headers) are additionally bounded to 2 GiB plus
100,000 KiB before parsing. Inputs are
streamed and all member payloads checked, never silently truncated to fit limits.
Before Python constructs a `ZipFile` (which eagerly allocates its entire central
directory), preflight caps the compressed file at 512 MiB, directory at 32 MiB,
count at 100,000, each expanded member at 256 MiB and total expansion at 2 GiB.
A bounded end-record read and streamed central-record scan check the actual count,
record bounds and declared sizes rather than trusting only the end-record count.
This applies to upstream ZIPs and the outer bundle. Single-disk classic ZIP
directories are supported; ZIP64 end records/locators, sentinel counts/offsets/
sizes and ZIP64 central extra fields fail explicitly before eager parsing. None
of the actual pinned sources or generated outer bundle requires these directory
extensions. ZIP64 local size headers used by the deterministic writer are allowed;
they do not control directory allocation. Future inputs needing ZIP64 directories
require an explicitly reviewed bounded implementation, not truncated fallbacks.

These conservative bounds accommodate the full pinned specification (about
1.8 GB expanded); future releases exceeding them need explicit review.

## Retain and reproduce offline

Retain the outer ZIP and its independently recorded SHA-256 beside the matching
wheel/release notes. Unzip the **outer bundle** into a fresh directory with a
trusted ZIP tool, then verify it using the included script and original ZIP.
The nested official archives remain intact. To reconstruct the outer ZIP from
its own retained inputs, from the extracted bundle directory:

```sh
python3 scripts/build_archival_bundle.py --cache-dir sources \
  --output /path/to/new/reproduced.zip
python3 scripts/build_archival_bundle.py --verify /path/to/new/reproduced.zip
shasum -a 256 /path/to/original-bundle.zip /path/to/new/reproduced.zip
```

The builder uses only bundled files and source blobs in this mode. It creates
sorted ZIP entries with fixed DOS timestamps, modes and stored compression; no
current time, filesystem ownership, temporary path or compression-library output
enters the ZIP. Identical pins, script, reference documentation and source blobs
produce identical bytes. Changing this documentation or script changes the
bundle checksum, intentionally. No network is attempted without `--fetch`.

Exception cleanup and no-overwrite publication are covered by small interrupted
copy/download and competing-publisher tests. Hard-link atomic publication does
not establish power-loss durability: there is no fsync protocol or crash recovery
qualification. Keep cache/source files unchanged during build and verification;
these maintenance tools do not defend against concurrent hostile local mutation.
Before release automation, measure peak resident memory and temporary-disk use
for the actual pinned build and verify on the release platform. Count temporary
tar envelopes as well as staged source copies/output; limits are acceptance caps,
not a promise of small peak RAM (tar extended headers can also allocate memory).
Retain the command, platform, input hashes and observed sample/window with release
evidence. Measurements in one environment do not qualify other filesystems or
establish a universal upper bound.

To browse the upstream specification, copy its source blob to `fhir-spec.zip`
and use a trusted ZIP tool in a fresh directory that understands Windows ZIP
separators; open `index.html`. Some upstream features, remote links or browser
restrictions can require internet or fail locally. Preservation of every
published byte is verified; fully functioning offline web navigation is not
claimed. There is no embedded web server. Read the retained HTML license pages
and inventories directly without unpacking the entire website.

## License and dependency boundaries

The core's `package/package.json` declares `CC0-1.0`. The R4 license page grants
CC0 for the specification materials in `fhir-spec.zip`, while retaining HL7/FHIR
trademark rules and explicitly warning about third-party intellectual property.
Both that page and the archive's own license page are retained verbatim with
CC0's legal text. HL7, FHIR and the FHIR flame design are registered trademarks
of Health Level Seven International; their use does not constitute endorsement.

CC0 does not grant independent rights to SNOMED CT, DICOM, LOINC, ICD or CPT.
Their references/content shipped by HL7 stay intact with the upstream terms.
No extra terminology distributions, expansion packages, Java validator JAR,
Java runtime, IG packages or transitive validator dependencies are added here.
This bundle is complete for the named core/specification source archives; it
is not a self-contained general terminology validation environment. Separate
licensing and offline qualification are required before adding such dependencies.
The upstream content retains its own licenses. Helseark's own code/docs use
the [MIT License](../../LICENSE); this bundle does not grant a new license to
third-party material. Retained upstream notices remain authoritative for those materials.

Sources reviewed on 2026-11-14: [official R4 downloads](https://hl7.org/fhir/R4/downloads.html),
[R4 license and legal terms](https://hl7.org/fhir/R4/license.html),
[CC0 1.0 legal text](https://creativecommons.org/publicdomain/zero/1.0/legalcode.en).
Exact downloaded page bytes and hashes are retained in the source manifest/cache.

## Task 2 integration still required

A subsequent Task 2 packaging change can verify the `core` source hash and full
member inventory, then safely stage **every** regular file under `package/` as
`definitions/hl7.fhir.r4.core/4.0.1/package/`, copying bytes unchanged. Do not
reconstruct a core package from the bounded resource closure. Likewise stage
the entire combined schema under its unchanged upstream draft-06 dialect. The
archival manifest supplies source/member hashes for the runtime definition lock;
the shared lock must be deliberately updated by that task. The vault must retain
the exact definitions/contracts used by its records and record their digests.

The wheel may carry full core/schema plus relevant reference pages while the
large complete specification ZIP accompanies it as a separate version-matched
release artifact. That release pipeline must build/verify both artifacts, record
the bundle filename/size/SHA-256 in release metadata, deliver it beside the wheel,
and test an installed wheel plus retained definitions with networking denied.
No release publication is implemented here. Current package configuration still
ships its existing contents; this delivery does not claim otherwise.

Runtime init/import/validation/query/recovery must load only already installed
or vault-retained definitions. Missing or mismatched artifacts must fail with
an actionable offline error, never call this maintenance downloader. Registry
integration, vault copies, schema export, profiles and validator coverage remain
Task 2 work. Optional Java validation requires separately pinned licensed
binaries/dependencies and tested network denial/coverage reporting. Merely
retaining full core/specification bytes does not establish FHIR conformance,
terminology checking, clinical correctness or extraction accuracy.
