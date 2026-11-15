# PDF text extraction adapter

This independent Task5 slice implements only
`helseark.adapters.pdf.extract_pdf(source: Path, outputDirectory: Path,
limits: IntakeLimits) -> ExtractionArtifact`. It does not create clinical
resources, choose a person, build an import packet, accept a candidate, or
implement an intake command. All source content is untrusted data.

## Installation and call

Explicit maintainer/user installation, with network access if necessary:

```sh
uv sync --locked --extra pdf --group dev
uv run --no-sync pytest tests/test_pdf_adapter.py tests/test_validation.py -q
```

Normal library calls never install anything or access the network. The optional
extra pins **pypdf 7.0.0**. Missing or different installed versions raise
`ArchiveError(code="PDF_DEPENDENCY_UNSUPPORTED", details={"exitCode": 6})`.
The child also verifies the imported module version. No arbitrary plugin,
executable, OCR engine, model or password can be supplied through the API or PDF.

```python
from pathlib import Path
from helseark.adapters.pdf import extract_pdf
from helseark.contracts import IntakeLimits

result = extract_pdf(Path("lab-text.pdf"), Path("new-extraction"), IntakeLimits())
# result.pagesPath, result.pagesSha256, result.pageCount, result.issues
```

The source must be a regular file. The output directory must be new, with an
existing parent. Both paths may be absolute or relative; `..`, symlink sources,
and symlink ancestors are rejected. Directory traversal uses held descriptors
and `O_NOFOLLOW`. Existing destinations are never overwritten. Output directory
permissions are 0700; files are 0600. The local directory tree must not be
concurrently renamed or modified by another writer during extraction. This is
a local single-writer API, not a filesystem access-control sandbox.

Success leaves `original.pdf` (an exact byte copy) and `pages.json`. The source
is opened read-only, hashed during bounded retention and checked for changes.
Extraction uses a randomly named private `.pdf-<uuid>` sibling (0700), with
0600 files, beneath the held parent directory descriptor. The final name stays
absent during retention, parsing and artifact construction. After all files are
closed and the receipt is prepared, the complete directory is published with
Darwin `renameatx_np(RENAME_EXCL)` or Linux `renameat2(RENAME_NOREPLACE)`.
These operations atomically fail if the destination exists, including an empty
directory or a destination created during parsing. There is no replacing-rename
fallback; unavailable exclusive publication fails unsupported. This change is
local to extraction and does not alter accepted-archive publication policy.

Ordinary errors and child termination remove the adapter's staging files and
leave an absent final destination absent; preexisting destinations stay intact.
Filesystem errors can prevent staging cleanup and are typed I/O failures.
A hard kill of the extraction parent can leave a private staging sibling; inspect
and discard abandoned staging explicitly. A kill after publication may leave a
complete final directory without returning a receipt. These are visibility and
no-overwrite guarantees on qualified local filesystems, **not power-loss durability**:
there is no fsync/recovery protocol or claim of survival after power loss.

## Retained artifact version 1

`pages.json` is UTF-8 JSON with sorted keys, compact separators, literal Unicode
and one trailing LF. `pagesSha256` hashes its exact bytes. This is an extraction
artifact serialization, not the clinical `helseark-json-1` serializer.

```json
{
  "artifactVersion": "helseark-pdf-pages-1",
  "sourceSha256": "<SHA-256 of original.pdf>",
  "extraction": {
    "provenanceVersion": "1", "status": "known",
    "method": "pdf-text", "tool": "pypdf", "version": "7.0.0",
    "model": null, "preprocessing": []
  },
  "pages": [{"page": 1, "rotation": 0, "text": "Literal source text\n"}]
}
```

Pages are consecutive and **1-based**, including empty pages. `rotation` is the
inherited PDF page rotation, restricted to 0/90/180/270 degrees clockwise.
`text` is pypdf plain extraction, without decimal conversion, clinical parsing,
normalization, clipping, reordering by the adapter or model interpretation.
The empty preprocessing array declares that no source preprocessing occurred;
parser resource controls are not a source transformation. Model is explicitly
null. The receipt's immutable `issues` tuple includes `PDF_TEXT_REVIEW` for every
successful document. Each empty/whitespace-only page adds `OCR_REQUIRED` with a
zero-based JSON pointer into the retained pages array. Scans yield empty text,
not invented results. OCR is a [separate optional integration](../how-to/run-ocr.md). Blank pages are also
flagged conservatively; absence of this issue does not prove completeness.

No bounding boxes are emitted. Any future boxes must follow
`displayed-cropbox-top-left-normalized`: `[left,top,right,bottom]` in `[0,1]`
after rotation of the displayed CropBox. This adapter does not supply reliable
word/row geometry or pixel-to-text attribution. It records rotation but does
not geometrically rotate or crop content streams; text outside the CropBox may
be extracted. It does not extract annotation appearances, handwriting or pixels,
or guarantee reading order, complete fonts, OCR-layer correctness, clinical row
attribution, or visual completeness on a page that also has extractable text.
Always inspect the original document before human approval.

### Task2 evidence integration

Retain both original PDF and **exact** pages.json bytes in the selected person's
content-addressed assets. Create the DocumentReference against the original
source hash. Copy `extraction` verbatim into each derived evidence entry and use:

```json
{
  "kind": "pdf-page", "extractionSha256": "<pagesSha256>",
  "page": 1, "pageRotationApplied": 90,
  "coordinateSpace": "displayed-cropbox-top-left-normalized"
}
```

Use the page's actual rotation, matching the retained page record, and an exact
nonempty quote. Omit `bbox`. The existing Task2 validator reads
`sourceSha256` and `pages[page-1].{page,rotation,text}`; the added artifact version
and provenance fields are compatible. Tests exercise that actual validator,
including wrong-rotation and wrong-quote failures. The validator's consistency
check cannot prove that an extraction faithfully represents the rendered PDF.
Its current PDF locator checks do not attest parser identity or enforce the
adapter's `artifactVersion` / embedded extraction provenance against every
claimed evidence entry. Version 1 describes these producer bytes; it is not a
cryptographic producer attestation. Future artifact-version/provenance enforcement
needs an explicit, separately reviewed validator contract change.

## Limits and safe failures

`IntakeLimits` and `ExtractionArtifact` are frozen dataclasses in contracts.py.
All IntakeLimits values must be positive integers (booleans are rejected).

| Limit | Default | Adapter behavior |
| --- | ---: | --- |
| sourceBytes | 104857600 | Check source size, then count copied bytes; SOURCE_TOO_LARGE |
| pdfPages | 500 | Reject complete document above limit; PAGE_LIMIT |
| candidateResources | 10000 | Reserved for later candidate intake; no resources produced here |
| jsonDepth | 64 | Reserved for later untrusted candidate JSON, not PDF object depth |
| textFieldBytes | 1048576 | UTF-8 byte limit per page; TEXT_FIELD_LIMIT |

A fixed local Python child runs with `-I`, an empty environment and `/` as its
working directory. Input/output are opened descriptors, not executable source
content. Its stdout/stderr are discarded so parser diagnostics cannot disclose
source text. Parsing is strict; pypdf warnings, failed pages and unreadable
content fail the whole extraction. Encrypted files return `PDF_ENCRYPTED`
without accepting a password, even when an empty password might decrypt them.
Malformed/unreadable documents return `PDF_INVALID`. Safe errors contain fixed
messages, never source text, parser exception details or supplied paths.

Independent fixed budgets bound parser work beyond page count:

- 16 MiB declared/decoded individual streams and aggregate page content;
  upstream Flate/LZW/RunLength and array-stream limits are tightened. Per-stream
  decoding work is limited to 64 MiB. Other upstream parser limits stay enabled.
  Decompression/work-limit failures return `PDF_STREAM_LIMIT`.
- 64 MiB child JSON result and final retained artifact; oversized output fails.
- 10 CPU seconds, 15 seconds wall time, no core dumps. Child failure/signal or
  process budget violation returns `PDF_RESOURCE_LIMIT`; it is killed/reaped
  before cleanup. There are no retries with relaxed limits or clinical truncation.
- 512 MiB **child** process memory budget. Linux sets a hard address-space limit and also
  monitors RSS through `/proc`. macOS cannot enforce RLIMIT_AS/RLIMIT_DATA here:
  the parent samples kernel RSS through `proc_pid_rusage` every 20 ms, kills an
  over-budget child, and the child rejects an over-budget peak RSS before writing
  success. This is **not a hard instantaneous allocation ceiling on macOS**;
  transient allocations between samples can exceed the budget. Use an OS/container
  memory boundary when a hard ceiling is required. The parent reads at most the
  fixed result size before JSON decoding. The parent has no independent memory,
  CPU or wall-time cap: JSON load/encode creates multiple representations, and
  copying/local I/O falls outside the child's 15-second clock. The 512 MiB child
  budget does not cover the parent or bound aggregate concurrent host use.

Resource accounting unavailable or a platform other than Linux/macOS fails
`PDF_PLATFORM_UNSUPPORTED` with exitCode 6. The original adapter at
`3ec9a1a2f66667da21f939ac30dcac0b1321b5f4` passed 468 tests on each supported OS
in [the coordinator's remote matrix](https://github.com/ricardocabral/helseark/actions/runs/43625667311).
The exclusive-publication correction still requires a fresh coordinator-run
Linux/macOS matrix; local evidence for it covers macOS/APFS only. The child disables pypdf's external
JBIG2 decoder and rejects subprocess/exec/network audit events. Text extraction
does not request image decoding, follow PDF actions, execute JavaScript or
interpret instructions. This is defense in depth, not a sandbox against a
compromised Python interpreter or dependency. An external agent reading the
text still needs separate filesystem/tool restrictions.

## Dependency qualification, read 2026-11-14

Official sources were read at implementation time, without Firecrawl:
[versioned reader API](https://pypdf.readthedocs.io/en/7.0.0/modules/PdfReader.html),
[page API](https://pypdf.readthedocs.io/en/7.0.0/modules/PageObject.html),
[upstream extraction guidance](https://pypdf.readthedocs.io/en/7.0.0/user/extract-text.html),
[release](https://github.com/py-pdf/pypdf/releases/tag/7.0.0),
[PyPI metadata](https://pypi.org/pypi/pypdf/7.0.0/json),
[versioned BSD-3-Clause license](https://github.com/py-pdf/pypdf/blob/7.0.0/LICENSE),
and [upstream advisories](https://github.com/py-pdf/pypdf/security/advisories).

7.0.0 was uploaded 2026-11-06 12:10 UTC, before the lock's seven-day cutoff.
7.0.1 (November 10) and 7.1.0 (November 13, latest when read) are inside that
cutoff and were not selected. The project keeps `exclude-newer = "7 days"`;
normal dependency installation is separate from offline extraction.

The pin is **not vulnerability-free**:
[GHSA-fhff-j4m8-439h](https://github.com/py-pdf/pypdf/security/advisories/GHSA-fhff-j4m8-439h)
affects versions below 7.0.1 when loading certain images and is fixed in 7.0.1.
This adapter avoids image retrieval/decoding and retains process resource controls.
The official advisories API returned 78 published entries with
`per_page=100` at 2026-11-14 18:04:57 UTC (a complete single page at that time).
The other entries declared fixes at or below 7.0.0. This observation does not establish that all vulnerabilities
are known or absent. Requalify an explicit newer pin after the cutoff, rather
than automatically upgrading or claiming that bounds fix upstream defects.

| Official distribution | Size | SHA-256 |
| --- | ---: | --- |
| pypdf-7.0.0-py3-none-any.whl | 413949 | 112a2c7cbabefd8dfe498f7a13977e575e762d58cdb0d832acb8886922602c6f |
| pypdf-7.0.0.tar.gz | 7201622 | 061aa78dec270854c912dde80c6bc060486fa955399d643da27ea30afeb6571b |

The exact wheel was downloaded and its size/SHA-256 checked against official
PyPI metadata. Its 1605-byte license matched the versioned upstream LICENSE
byte for byte, SHA-256
`a97ac230e5f33ef10a5367a850eb01f91f1a0b064e34742c7794d2294557f524`.
uv.lock retains exact distribution URLs/digests. The wheel includes the upstream
BSD-3-Clause notice; preserve it when redistributing the optional dependency.
The fixture author's ReportLab/Pillow dependencies are not runtime dependencies.

## Qualification corpus and remaining Task5 work

The five named PDFs and five negative PDFs are original CC0 synthetic fixtures;
`tests/fixtures/synthetic/pdf/README.md` records authoring/rendering provenance.
Independent facts live in `tests/fixtures/expected/pdf-facts.json`. No real health
data was used. The scan contains only raster pixels; the injection is inert text;
the mixed report retains both explicit names without inferring person identity.

Historical adapter-only snapshot (the current integrated intake is documented in
[intake](intake.md) and [review](review.md)):

The adapter intentionally makes no mixed-person classification. At that snapshot, intake
must implement identity cue assessment and block ordinary acceptance on
`MULTIPLE_PERSON_CUES`; preserving text here does not satisfy that requirement.
Intake must consume actual adapter output/issues, retain hash-bound assets,
implement add_source/build_packet/read_candidate, connect the real Task3 context
and renderer plus Task4 kit/prompts, add CLI routing and test the human review
handoff. Full Task5 remains incomplete until that integration is verified.

CI retains the full Linux/macOS suite with `--extra pdf`, preceded by an exact
installed/imported pypdf 7.0.0 assertion so dependency absence cannot silently
skip qualification. A separate fresh base-only matrix checks actual dependency
absence, imports the adapter and requires the typed unsupported invocation;
it never uninstalls or hides a shared environment's dependency.
No production merge or push is part of this slice. Independent review follows.

### Maintained boundary and resource probes

`tests/test_pdf_adapter.py` includes real-child SIGSTOP visibility, completion,
termination/reaping, default 15-second timeout, collision at publication (including
empty directories), original bytes/permissions and private-error checks. Maintained
synthetic boundaries cover 500/501 pages, 1,048,576/1,048,577 UTF-8 text bytes
(using multibyte characters), 16,777,216/16,777,217 decoded stream bytes,
exact source limits and 100 MiB/100 MiB+1 sparse invalid inputs. There is no
clinical slicing. `tests/fixtures/expected/pdf-pages.json` retains the independent
reviewer's full six-page rendered transcription for all five positive fixtures.
The reduced output-envelope test accepts exact measured artifact size and rejects
one byte less using the actual parser and serialization, without a resource bomb.

Run `python tests/qualify_pdf_resources.py` with the extra to measure three
fresh extraction parents (1, 4 and 8 pages, each exactly 1 MiB ASCII text).
The harness creates compressed fixtures outside measured processes and reports
parent `getrusage(RUSAGE_SELF)` baseline/peak RSS, CPU, wall time, source and final
artifact sizes; the worker remains real. On macOS 15.7.3 arm64/APFS, Python 3.12.8,
pypdf 7.0.0, the 2026-11-14 checkout probe measured:

| Text bytes | Artifact bytes | Parent baseline peak RSS | Parent peak RSS |
| ---: | ---: | ---: | ---: |
| 1048576 | 1048886 | 23953408 | 28672000 |
| 4194304 | 4194716 | 23232512 | 50184192 |
| 8388608 | 8389156 | 23216128 | 61915136 |

These are three observations, not worst-case bounds or portable thresholds.
They do not qualify 64 MiB JSON saturation, 512 MiB exhaustion, 10-second CPU
exhaustion, arbitrary PDF accuracy, Linux parent RSS or aggregate concurrency.
The cap check and small measurements qualify only the bounded fixtures described;
the installed-wheel rerun and exact correction SHA are recorded in the internal
handoff. No parent cap is inferred from the child's budget.
