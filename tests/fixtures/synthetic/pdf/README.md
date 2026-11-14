# PDF qualification fixtures

All identities, values and text are invented, original CC0 synthetic data.
No real health records, downloaded reports, OCR model or LLM were used.
The five `../lab-*.pdf` fixtures and five PDFs in this directory were authored
by `create_fixtures.py`. Run it explicitly only in a maintainer fixture environment
with ReportLab 4.4.9, Pillow 13.0.0, pypdf 7.0.0 (Python 3.15.2 used locally).
These authoring dependencies are not installed by the product or its pdf extra.
ReportLab uses built-in Helvetica; the scan's font is Pillow's default raster
font. Expected facts in `../../expected/pdf-facts.json` were separately specified
from intended visible content, not derived from an extractor.

- `lab-text.pdf`: two pages, literal comparator/decimal comma/trailing zeros,
  source range, a source clock with no timezone and final status.
- `lab-scan.pdf`: a visible synthetic report drawn only into image pixels;
  no text layer. It must produce no text and OCR_REQUIRED.
- `lab-injection.pdf`: visible hostile instruction and shell substitution text,
  which must remain inert. The adapter does not run a shell or external agent.
- `lab-two-people.pdf`: two explicit invented patient labels and different values;
  both retained without matching, reconciling or assigning a person.
- `lab-rotated.pdf`: MediaBox 600x800, shifted CropBox `[100,200,500,440]`,
  clockwise /Rotate=90. CropBox is 400x240 points before rotation, displayed as
  240x400 points. All three lines are inside the CropBox. No word boxes claimed.
- `corrupt.pdf`: invalid xref/trailer.
- `encrypted.pdf`: original lab text encrypted with RC4-128 and a synthetic-only
  password. This intentionally exercises rejection, not cryptographic guidance.
  Encryption identifiers can vary on regeneration; retained bytes are pinned below.
- `page-limit.pdf`: two blank pages for the one-page limit test.
- `expansion-limit.pdf`: about 21 KiB compressed file with a 20 MiB whitespace
  content stream; must fail the 16 MiB stream budget, not be mistaken for a scan.
- `failed-page.pdf`: valid first text page, second /Contents replaced with an
  invalid numeric object. No successful partial extraction may survive.

On 2026-11-14, Poppler **26.11.0** independently rendered all six pages of the
five positive PDFs with `pdftoppm -png` (60 dpi, except rotated at 72 dpi with
`-cropbox`). PNGs were visually inspected: legible, complete source lines, raster
scan visible, no clipping/overlap. `pdfinfo -box` independently reported the
rotated CropBox and /Rotate=90; its rendered PNG was 240x400 pixels. Poppler is
only a qualification tool, not a runtime dependency. Local Fontconfig printed
cache-directory warnings under the filesystem sandbox; rendering succeeded.

Negative fixtures are intentionally malformed or constrained inputs. Tests use
the actual pinned parser, not generated parser responses. A test also combines
real text/scan/text pages to ensure empty middle pages remain present. Budget
tests lower the controller's allowed wall time, memory or result size while
launching the real child; they verify failure, child reaping and cleanup.

## Retained byte inventory

Hashes below describe the checked-in corpus, not a promise of byte-identical
regeneration of encrypted files across authoring environments.

| Path (under synthetic/) | Bytes | SHA-256 |
| --- | ---: | --- |
| lab-injection.pdf | 1465 | 2df346d7932553a4ed3a7a33804002904db175e2596978fee9f36c7e14af8cfc |
| lab-rotated.pdf | 1024 | 16bbf2dc91cb3f683febba2c7624db034a367c36d310ab92043c9c4560ff0594 |
| lab-scan.pdf | 13045 | f9ef79ab7fde6da9eb1336355aae65da4e10bc853f76950a05b141b9f7df6f8b |
| lab-text.pdf | 1975 | 09b6d736d5b3c102b30497f929742ad86a052c84c29aefa17266318fc3ee6df0 |
| lab-two-people.pdf | 1461 | fdb29f7821a89cad875ee04871429dc9342cdf072319aff1f316a661b2b999ce |
| pdf/corrupt.pdf | 32 | f7ab8c910d83932391deb5d6f72c58ccf7a8d4fc79557b913711717c9398091a |
| pdf/encrypted.pdf | 1941 | 8978f12a5890c1dd26180fb73c4db327330bcd1d8a4b2ff603c2db3937c987b5 |
| pdf/expansion-limit.pdf | 20937 | 53c0496ccb501b19164fdc3fca1d8547d97ddecf42a99946d68bbcb5184032ae |
| pdf/failed-page.pdf | 1603 | 13989622475d0188d5f4904aa2cc9e2f988a3b990534e51c5ae87f96cfcda0a3 |
| pdf/page-limit.pdf | 551 | 7ee34a0b08ffde2a7abf803579db2a37a8dfc3622be7842053ba800358e019ef |

The maintained `tests/fixtures/expected/pdf-pages.json` contains the independent
2026-11-14 review's complete transcription of the six rendered positive pages
(five documents). It extends the selected quote expectations without deriving
expected text from the adapter at test time. Resource and exact-boundary tests
generate bounded synthetic PDFs at runtime; no health data is used.
