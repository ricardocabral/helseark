---
name: import-records
description: Draft evidence-linked candidates from an explicitly selected report or structured export; stop before acceptance.
---

# import-records

Read [common archive instructions](../../AGENTS.md) first. Task ID: `import`.

Select the extraction prompt for report text or the mapping prompt for structured input according to the trusted descriptor. Require retained source receipts, confirmed person assignment and exact asset/extraction metadata. Apply the clinical model evidence checklist to every produced scalar. Keep unsupported source sections itemized. If a complete candidate can be drafted, use the three candidate routes and report route in the common instructions. Human review follows future toolkit preparation; never create prepared revisions or receipts. Without retained assets, source locators, identity confirmation or runtime-supplied candidate metadata, emit only a blocked report.

Contracts: [clinical model](../../../docs/reference/clinical-model.md#identity-references-and-versions), [evidence checklist](../../../docs/reference/clinical-model.md#evidence-checklist), [archive identity/revisions](../../../docs/reference/archive-format.md#identity-and-revisions). For candidate production use [`candidate.schema.json`](../../../schemas/0.1.0/candidate.schema.json) and [`evidence.schema.json`](../../../schemas/0.1.0/evidence.schema.json); never substitute a parallel clinical format.

Prompt routes: [`extract-report`](../../prompts/extract-report.md), [`map-structured-export`](../../prompts/map-structured-export.md).

For report extraction require `pdf-intake`; structured mapping instead requires the proposed `structured-import` capability. Common capability dependencies: `schema-export`, `baseline-validation`, `agent-context`, `reviewed-publication`. At base `1b91620`, only `schema-export` and `baseline-validation` exist; dependencies outside that set are unavailable. This skill is draft-only until those dependencies are implemented and evaluated. Existing validation can check an already supplied candidate, but does not provide intake, preparation or publication.
