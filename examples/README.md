# Complete invented example

Everything here is invented, including Alex Example and report SYNTH-001. No
record describes a real person. Open [source.csv](source.csv),
[bundle.fhir.json](bundle.fhir.json) and [evidence.json](evidence.json).
CSV row numbers in evidence count data rows after the header; this file has one.
The source CSV is a fictional lab export, not a new canonical clinical format.

The explicit person ID is `11111111-1111-4111-8111-111111111111`. The Bundle
contains a Patient, an Observation, and a DocumentReference to `source.csv`.
References use Bundle-local UUID URNs. Evidence targets use `Type/id` to identify
the same resources. The attachment URL resolves relative to this example folder.
This portable collection uses base FHIR R4; it does not claim Helseark archive
profile conformance or constitute a CLI candidate/proposal.

## Source comparison and expected query

| Source: source.csv, data row 1 | FHIR field on Observation | Retained meaning |
| --- | --- | --- |
| test: `C-reactive protein` | `code.text` | Source label; no inferred terminology code |
| status: `final` | `status` | Lab status; not human acceptance |
| result: `<0,050 mg/L` | `valueQuantity` | JSON number `0.050`, comparator `<`, unit `mg/L` |
| effective_date: `2026-02` | `effectiveDateTime` | Month only; no invented day or timezone |
| uncertainty column, exact sentence | `note[0].text` | Below reporting limit; day and time absent |

A query for this person's supplied C-reactive protein records in February 2026
returns one source-reported final observation, **<0.050 mg/L**, dated **2026-02**,
with day/time unknown and no exact concentration. Cite `source.csv`, data row 1,
columns `result`, `effective_date`, `status`, `test`, and `uncertainty`, and the
Observation ID `22222222-2222-4222-8222-222222222222` in `bundle.fhir.json`.
This answers a retrieval question only; it gives no medical interpretation.

## Review before acceptance

Compare the person ID/name columns against Patient and both subject references.
Check the exact numeric token `0.050`, `<`, `mg/L`, source status, month precision
and uncertainty sentence. Every clinical leaf has a source citation in
`evidence.json`; generated IDs and document metadata are labeled bookkeeping.
Bundle type/fullUrl are packaging, not clinical facts. Source digests are already
filled in for this static example; reading it requires no hash tooling.

The draft remains **unreviewed**. A real reviewer must record their name, date,
exact files/revision, decision and unresolved concerns separately; no fictitious
approval receipt is supplied. Any edit requires fresh review. Reject identity
conflicts and unsupported facts. Keep accepted prior files and originals intact.

A correction to the extracted value would create a separate proposed version,
identify this prior Observation/file and field, quote the supporting source, and
wait for review. Do not change this example's correct `0.050` merely to demonstrate
an edit. Schema checks cannot confirm clinical truth or source authenticity.
