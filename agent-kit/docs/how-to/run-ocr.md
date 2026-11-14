# Retain a local OCR extraction for review

Use this when a PDF scan has no usable text, or when its text layer misses image
content. OCR is an optional local capability. It produces evidence, never accepted
clinical records. Read the original beside every proposed value and table row.

Install `helseark[ocr]` from an already prepared local wheel/dependency directory,
using `pip install --no-index --find-links LOCAL_WHEELS 'helseark[ocr]'`.
The extra uses the same pinned pypdf 7.0.0 as PDF intake. The base package does
not require native OCR tools. Normal commands never install or download anything.

Separately provision Tesseract **5.5.4**, Poppler `pdftoppm` **26.11.0** and the
`tessdata_fast` **4.1.0 English** model. This runner currently requires macOS
and `/usr/bin/sandbox-exec`; Linux and Windows return `OCR_UNSUPPORTED`.
Verify your binaries and their local shared-library dependencies before use.
The runner requires exact operator-supplied binary SHA-256 values and refuses
a different version or model. A SHA-256 entered by an operator is an explicit
local trust decision, not a publisher signature. No alternate engines/services
or model discovery are attempted.

Create a private configuration file with absolute paths, for example:

```json
{
  "outputDirectory": "/private/tmp/avery-ocr-1",
  "engine": "/opt/homebrew/bin/tesseract",
  "engineSha256": "0f17eed03730d18d694f90e4ad36ea9e2f6ba8009bab044770359b65514ca163",
  "renderer": "/opt/homebrew/bin/pdftoppm",
  "rendererSha256": "8654e0d21c42fbf010edd9b87c8fbad910c961adf47fb00fe59d02d39e2aba22",
  "model": "/opt/homebrew/share/tessdata/eng.traineddata",
  "rotation": 0
}
```

The binary hashes above identify the qualified macOS arm64 installation, not all
builds of those releases. Compute yours with `shasum -a 256 PATH`; qualify another
build on the synthetic corpus before relying on it. Model SHA-256 is fixed to
`7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`,
verified against [upstream 4.1.0 eng.traineddata](https://github.com/tesseract-ocr/tessdata_fast/blob/4.1.0/eng.traineddata).

Run with an explicitly selected person and fresh private output directories:

```sh
helseark --vault /absolute/family-vault intake add /absolute/scan.pdf \
  --person PERSON_UUID --packet /private/tmp/avery-packet-1 \
  --agent-output /private/tmp/avery-candidate-1 --confirm-person \
  --ocr-config /absolute/ocr-config.json --json
```

Capture the returned host context digest outside agent-editable files. Follow
`PACKET/ENTRY.md` and the existing [import procedure](import-report.md). The packet
includes real OCR text, engine/model/preprocessing provenance, word boxes and
`OCR_VISUAL_REVIEW`. Every page has a full-page unresolved region, including blank
pages and high-confidence output. Do not drop that issue from candidate unresolved;
a human must acknowledge the remaining limitations through normal review.
Multiple recognized explicit patient labels block drafting/acceptance. Cue matching
can miss names, so confirmed person selection still requires visual inspection.

`rotation` is an explicit clockwise correction, one of 0/90/180/270, applied after
the PDF's own displayed rotation. Orientation/deskew is never guessed. A sideways
scan may need 270; inspect the corrected derivative and boxes. Changing rotation
requires a new `outputDirectory`. Each different artifact hash is a separate
extraction version. Identical reruns reuse content-addressed bytes. The previous
PDF-text extraction and every accepted revision remain intact. A changed candidate
for an accepted source requires `candidate prepare --reextract` and explicit
reconciliation when anchors change. Missing facts never delete accepted facts.

If an optional tool/model/platform is unavailable, expect exit 6. Corrupt or
encrypted PDFs, excessive pages/pixels/text, native failures and timeouts return
safe errors while keeping the intake original. An existing destination is never
replaced. Failed OCR does not silently fall back to another extractor or service.
For large documents, this runner rejects over 20 pages rather than slicing them.

## Evidence format and qualified limits

`extract_ocr(SourceReceipt, OcrConfig) -> ExtractionArtifact` lives in
`helseark.adapters.ocr`. The fresh output contains `original.pdf`, `pages.json`
(`helseark-ocr-pages-1`) and hashed render/corrected-image/TSV blobs. Intake copies
all derivatives into the selected person's content-addressed assets and stores an
immutable receipt beside the OCR artifact. Evidence selects that exact extraction
hash, not a mutable "latest" pointer. Reviewed proposals include every derivative
and receipt in their existing hash closure; backup/restore preserves those bytes.

Poppler renders the displayed CropBox to 8-bit grayscale PGM with `-r 150
-scale-to 4000 -cropbox`; the longest side is 4000 pixels (20 million pixel cap).
The explicit integer quarter-turn is lossless pixel permutation. Tesseract uses
only local `eng`, LSTM OEM 1, PSM 6, one OpenMP thread, and TSV output. There is
no auto-crop, resampling beyond Poppler, numeric correction or custom dictionary.
Engine-internal preprocessing is determined by its pinned native installation.
Shared libraries/fonts/OS can affect rendered bytes; hashes expose that difference.

TSV integer boxes are divided by corrected width/height, then inverse-rotated into
`displayed-cropbox-top-left-normalized` coordinates. For corrected `[l,t,r,b]`,
clockwise 90 maps to `[t,1-r,b,1-l]`; 180 to `[1-r,1-b,1-l,1-t]`; 270 to
`[1-b,l,1-t,r]`. The PDF's original rotation remains `pageRotationApplied` in
candidate evidence. Word offsets are half-open Unicode code-point offsets into
retained page text. No normalized clinical numeric value is emitted by OCR;
`1.20`, decimal commas, comparator characters and even misrecognized letters stay
exactly as recognized. Confidence is an engine score, not a probability.

Native commands run under a macOS network-denial profile, cleared environment,
30-second wall/20-second CPU limits, 512 MiB monitored RSS and 64 MiB/file output
limit. Derivatives total at most 128 MiB; pages JSON at most 64 MiB and page text
at most 1 MiB. These limits can reject valid complex documents. No aggregate
multi-process or power-loss guarantee is claimed. Native dependencies are trusted
local executables; this is not a general hostile-code sandbox.

The eight-case CC0 corpus includes plain/rotated/noisy scans, mixed text/image,
mixed person labels, decimal confusion, missing glyphs and table spill, with
hand-authored facts and row regions. Real engine output includes decimal errors,
letter-to-digit substitutions, unreadable occlusion and table corruption. Passing
behavioral tests is not an accuracy guarantee. Run `pytest tests/test_ocr.py -q -s`
on the qualified native installation to see each case's recognized text, missing
fact and location mismatch; full suites remain coordinator/remote-CI work.

Official documentation consulted 2026-11-14:
[Tesseract CLI](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html),
[image quality/table limits](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html).
The installed Poppler 26.11.0 `pdftoppm(1)` manual specifies CropBox, scale, page
selection and grayscale options. Tesseract and tessdata_fast are Apache-2.0;
the qualified Homebrew Poppler 26.11.0 build has license expression
`GPL-2.0-only OR GPL-3.0-only`. Its installed `.brew/poppler.rb` declares
`any_of: ["GPL-2.0-only", "GPL-3.0-only"]`; the Poppler entries in
`sbom.spdx.json` record that expression as `licenseConcluded` (`licenseDeclared`
is `NOASSERTION`). `README-XPDF` explicitly excludes unspecified later GPL
versions. Leptonica is BSD-2-Clause.

Native tools/models and their notices remain separately provisioned, not
redistributed in the Helseark wheel. When distributing them, preserve all
upstream notices and dependency licenses, including Poppler's `COPYING` (GPL v2),
`COPYING3` (GPL v3), `README-XPDF` and applicable component documentation/notices.
The engine/model Apache-2.0 notices do not cover the renderer or its dependencies.
