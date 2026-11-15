# Licensing and third-party material

Project-authored code, schemas, profiles and documentation use the
[MIT License](../../LICENSE).
Helseark's Python metadata and local FHIR profile package declare MIT.
Vendored HL7 FHIR material retains its upstream CC0 terms and third-party exceptions.
The license does not grant trademark rights or
license users' health records and exports.

## Exceptions and retained notices

| Material | Terms / required handling |
| --- | --- |
| Original synthetic clinical fixtures | Existing CC0 dedication in [fixtures README](../../tests/fixtures/README.md) |
| Retained pre-renderer protocol fixture | Original [Apache-2.0 text](../../tests/fixtures/synthetic/agent-workflows/historical-protocol1/LICENSE), notices and exact historical bytes remain; see its [provenance](../../tests/fixtures/synthetic/agent-workflows/historical-protocol1/README.md) |
| HL7 FHIR R4 definitions, schemas, docs and runtime archive | Preserve exact upstream notices and retained CC0 text, including third-party exceptions |
| Python runtime, optional and development dependencies | Inspect exact locked distribution metadata and their own license files, including transitives |
| Brand assets | Retain required notices; verify publication/reuse rights and trademark scope |
| Future Java validator, OCR engines/models or terminology | Separate acquisition and license review; not covered by the project license |

The Apache text is scoped to that historical fixture. It is not a second project
license and is not listed as a Python distribution license.

Retain existing archives and historical fixtures with their original bytes,
provenance and notices.

[Definitions guidance](../../definitions/README.md) and
[upstream inventory](../../definitions/upstream-inventory.json) record exact sources
and hashes. FHIR uses CC0 with trademark and third-party exceptions. SNOMED CT,
LOINC, CPT and other terminology can have separate terms; FHIR support is not
blanket redistribution permission. Never normalize vendored bytes to add headers.

Before release, inventory actual wheel/sdist/archival contents, sources, versions,
hashes and licenses. Include required texts/attributions in each artifact, not
only this checkout. The root MIT license is included in Python distributions, archival bundles and
new vaults (as `definitions/LICENSE`).
Review any additional terminology, validator or model before bundling it. Scanners
support review but cannot establish ownership or compatibility alone.

See the [release guide](releasing.md) and [FHIR R4 licensing](https://hl7.org/fhir/R4/license.html).
