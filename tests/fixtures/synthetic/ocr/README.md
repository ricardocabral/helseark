# Synthetic OCR corpus

Original CC0-1.0 fixtures; no real records. `generate.py` renders hand-authored
text through local ImageMagick 7.1.2-35 and macOS Courier New, then embeds raw grayscale
pixels in PDFs with a small independent PDF writer. The scan rows have no text layer. `mixed-text-image.pdf` additionally has a
vector text title, so OCR must cover both visible kinds of content.
Rerendering across font/rasterizer builds can change bytes; committed bytes are
qualification inputs. Hand-authored facts and approximate displayed-page row
regions are in `tests/fixtures/expected/ocr-facts.json`.

The rotated scan needs explicit clockwise 270 correction. The mixed scan has
two patient labels. Noise is seeded. Decimal-confusion intentionally prints
letter O, not zero. Missing-glyph occludes part of 1.20: recovering its intended
number is impossible from those pixels. Table rules cross/spill into text.
Qualification reports each fact/location error; passing safety tests does not
mean all facts were correctly recognized. Every page remains unresolved.

`complete-scan.pdf` is the committed Task5 `task5-complete.pdf` rasterized with
Poppler pdftoppm 26.11.0 (`-singlefile -r 150 -gray`) and embedded by the same
small PDF writer before its hybrid-font resource was added. Its source contains
no text layer. Its clinical oracle is the independently hand-authored Task5
bundle/evidence and `tests/fixtures/expected/intake-facts.json`; the test explicitly
rebinds source hash and actual OCR provenance, never synthesizes engine output.
It exercises exact 0.050, human review, re-extraction and full derivative recovery.
The eight-case facts/location report is separate from that reviewed-flow fixture.
