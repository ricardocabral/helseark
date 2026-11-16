# Source and mapping evidence — unreviewed

Source: [laboratory.csv](../../sources/laboratory.csv), CSV data rows 1–3
(physical lines 2–4, after the header). Exact cell quotes and SHA256 are retained
in [evidence.json](evidence.json). Both sources and results are invented.

Patient `44444444-4444-4444-8444-444444444444`, name `Sam Synthetic`, is explicit
in each row's `person_id` and `person_name`. These cells support the profile,
Bundle Patient and every subject reference. DocumentReference
`88888888-8888-4888-8888-888888888888` retains the CSV attachment. UUIDs and
attachment metadata are generated bookkeeping, not clinical source facts.

| Source locations | Target Observation suffix | Source facts retained |
| --- | --- | --- |
| Row 1: test, result, unit, status, date | 555555555555 | `Colesterol LDL calculado`; `103,00` → JSON number `103.00`; `mg/dL`; `final`; `2026-03-01` |
| Row 2: test, result, unit, status, date | 666666666666 | `Calculated LDL cholesterol`; `103.00`; `mg/dL`; `final`; `2026-04-01` |
| Row 3: test, result, unit, status, date | 777777777777 | `LDL`; `105,0` → JSON number `105.0`; `mg/dL`; `final`; `2026-05` |
| Rows 1–2: specimen, method | First two Observations | `Serum/plasma` → specimen.display; `Calculated` → method.text |
| Row 3: empty specimen, method | Third Observation | No specimen or method added; note explains unresolved coding |

Decimal comma replacement changes only punctuation. No unit conversion,
rounding, day or timezone inference occurs. Lab `final` is a source result status,
not a review decision.

No source row supplies any standard coding. The proposed native FHIR LOINC and
UCUM additions are **agent assignments**, attributed separately in
[mapping-evidence.json](mapping-evidence.json), with cell quotes for all six
LOINC axes. [Proposal 1](mapping-proposal-1.json) and
[proposal 2](mapping-proposal-2.json) retain context and citations, including
literal original units. No reusable mapping is approved. Exact source labels
remain intact alongside the proposed standard coding.

The [primary LOINC reference](https://loinc.org/13457-7/) supplies the canonical
long common name and axes; see [catalog provenance and limitations](../../README.md#catalog-provenance-and-limits).
The choice of `2.83` is illustrative and needs release-specific verification in
real use. A translation search result alone is insufficient evidence for coding.
