# Review required — invented draft

Person: Alex Example, ID `11111111-1111-4111-8111-111111111111`.
This profile illustrates an identity from the invented source. A real workflow
requires the user's explicit profile and source-assignment confirmation.
No reviewer, decision or acceptance date is supplied.

Read coverage: one CSV data row from `../../sources/source.csv`. The source has
no unreadable fields. It supplies one C-reactive protein result, source status
`final`, value `<0,050 mg/L` and effective month `2026-02`.

Normalization: decimal comma to point, preserving raw numeric token `0.050`,
comparator `<` and unit `mg/L`. No day, time, timezone, clinical code, reference
range or diagnosis was supplied or invented. The source's uncertainty sentence
is retained verbatim in the Observation and its citations.

The automated example checks validate this Bundle, its resources, profile and
optional evidence envelope against the pinned schemas, and check source-path
relocation without asserting approval. The documented command in
[schemas.md](../../../docs/schemas.md) checks these exact example files.
Structure does not establish extraction accuracy, source authenticity or approval.

Human review remains unresolved. Compare every cited field with the source,
including the person, comparator, unit, date precision, source status and
uncertainty. Any edited draft needs fresh review. Retain the original source.
`records/` contains no accepted import, and no acceptance note is fabricated.
