# Readable citations — invented, unreviewed draft

Source: [source.csv](../../sources/source.csv), data row 1 (physical row 2, after the header).
Targets below refer to [bundle.fhir.json](bundle.fhir.json). The profile and all IDs
are illustrative; no real identity confirmation or human acceptance is asserted.

| Target resource and fields | Source column | Exact source quote |
| --- | --- | --- |
| `Patient/11111111-1111-4111-8111-111111111111` `/identifier/0/value` | `person_id` | `11111111-1111-4111-8111-111111111111` |
| `Patient/11111111-1111-4111-8111-111111111111` `/name/0/text` | `person_name` | `Alex Example` |
| `Observation/22222222-2222-4222-8222-222222222222` `/subject/reference` | `person_id` | `11111111-1111-4111-8111-111111111111` |
| `Observation/22222222-2222-4222-8222-222222222222` `/status` | `status` | `final` |
| `Observation/22222222-2222-4222-8222-222222222222` `/code/text` | `test` | `C-reactive protein` |
| `Observation/22222222-2222-4222-8222-222222222222` `/effectiveDateTime` | `effective_date` | `2026-02` |
| `Observation/22222222-2222-4222-8222-222222222222` `/valueQuantity/value`, `/valueQuantity/comparator`, `/valueQuantity/unit` | `result` | `<0,050 mg/L` |
| `Observation/22222222-2222-4222-8222-222222222222` `/note/0/text` | `uncertainty` | `Day and time not supplied; result is below the reporting limit, not an exact concentration.` |
| `DocumentReference/33333333-3333-4333-8333-333333333333` `/subject/reference` | `person_id` | `11111111-1111-4111-8111-111111111111` |
| `DocumentReference/33333333-3333-4333-8333-333333333333` `/description` | `report_id` | `SYNTH-001` |

The decimal comma in `<0,050 mg/L` becomes the JSON number `0.050`; the bound
`<` and original unit `mg/L` remain. `2026-02` remains month precision.
The result is below the reporting limit, not an exact concentration.

## Generated bookkeeping

Resource IDs, UUID URNs, Bundle type and file metadata are assigned for this
invented example. `DocumentReference.status = current` describes the source
reference, not human acceptance. Its attachment URL `../../sources/source.csv`
resolves from both `drafts/first-import/` and a future `records/first-import/`.
The description prefixes the source report ID with “Invented report”.

[evidence.json](evidence.json) is an optional machine-readable version of these
citations, retained for schema checks. Readable citations do not require hashes.
