# Licensing and third-party material

## Owner decision pending

The implementation design proposes Apache-2.0 for project-authored code, schemas,
profiles and documentation, and CC0-1.0 for original synthetic fixtures. Existing `profiles/r4/0.1.0/package.json`, its agent-kit copy and
`definitions/lock.json` already declare Apache-2.0 for project-authored material;
`pyproject.toml` has no license field. The fixture README declares CC0. There is no root project license text yet. Those declarations
must be reconciled with the owner's explicit decision before public distribution;
do not infer a blanket license for the entire repository from one package field.

Before public launch, the owner must approve the license, confirm rights to all
contributed material and brand assets, add the exact license text, and align
Python package metadata and all distributed notices. Until that decision, do not
describe the repository as licensed open source. This guide grants no new rights.
User health records and exports never inherit the software license.

## Scope and retained notices

| Material | Source of terms / action |
| --- | --- |
| HL7 FHIR R4 definitions, schemas, docs and runtime archive | Keep exact upstream notices and CC0 text; inspect both retained subsets and the full archive |
| Original synthetic fixtures | Existing CC0 dedication in `tests/fixtures/README.md`; retain a standalone full text before distribution |
| Python runtime, optional and development dependencies | Inspect exact locked distribution metadata and retained license files, including transitives |
| Brand masters and exports | Retain `docs/brand/source/provenance.json`; owner verifies publication/reuse rights; define trademark scope |
| Future Java validator, OCR engines/models or terminology | Separate acquisition and license review; not covered by the project license |

[Definitions provenance](../../definitions/README.md) and
[upstream inventory](../../definitions/upstream-inventory.json) record exact
sources and hashes. FHIR uses CC0 with exceptions for trademarks and third-party
material. SNOMED CT, LOINC, CPT and other terminology can have separate terms;
FHIR support is not blanket redistribution permission. Preserve notices inside
HTML, JSON and archives; never normalize vendored bytes to add headers.

Before release, inventory actual wheel/sdist/archival contents, their sources,
versions, hashes and licenses. Include required license texts/attributions in
those artifacts, not only in this checkout. Do not bundle a third-party dataset,
validator or model until that inventory is reviewed. Generated inventories and
scanners support review but cannot establish ownership or compatibility alone.

Sources checked for this guide: [FHIR R4 licensing](https://hl7.org/fhir/R4/license.html)
and [GitHub licensing guidance](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/adding-a-license-to-a-repository).
