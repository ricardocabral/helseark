# One invented health folder

This is the plain-file layout produced by the [Helseark skill](../skills/helseark/SKILL.md).
Alex Example, report SYNTH-001 and every result are invented. These files remain
**unreviewed**; no real identity confirmation or approval is claimed.

```text
examples/
  profile.fhir.json
  sources/source.csv
  drafts/first-import/
    bundle.fhir.json
    evidence.md
    review.md
    evidence.json          # optional machine-readable citations
  records/README.md        # no accepted import or acceptance note
```

Open the [profile](profile.fhir.json), [retained source](sources/source.csv),
[draft Bundle](drafts/first-import/bundle.fhir.json),
[readable citations](drafts/first-import/evidence.md) and
[review note](drafts/first-import/review.md). The optional
[evidence envelope](drafts/first-import/evidence.json) supports the existing
schema checks; normal skill use can retain only readable citations.

The person ID is `11111111-1111-4111-8111-111111111111`. Patient, Observation and
DocumentReference use Bundle-local UUID URNs. The profile matches the Bundle's
Patient. The CSV is a fictional lab export, not a second clinical data format.
This Bundle uses base FHIR R4 and makes no experimental archive-profile claim.

## Compare the draft with its source

CSV data row 1 is physical row 2, after the header.

| Source column | Observation field | Retained meaning |
| --- | --- | --- |
| test: `C-reactive protein` | `code.text` | Source label; no inferred code |
| status: `final` | `status` | Lab status; not human acceptance |
| result: `<0,050 mg/L` | `valueQuantity` | JSON number `0.050`, comparator `<`, unit `mg/L` |
| effective_date: `2026-02` | `effectiveDateTime` | Month only; no day or timezone added |
| uncertainty column | `note[0].text` | Below reporting limit; day and time absent |

A question about Alex's supplied C-reactive protein result in February 2026
returns **<0.050 mg/L**, dated **2026-02**, with no exact concentration or known
day/time. Cite the CSV's `test`, `result`, `status`, `effective_date` and
`uncertainty` columns and Observation `22222222-2222-4222-8222-222222222222` in
the draft Bundle. This is retrieval, not medical interpretation.

## Review and source paths

Check the source's person ID/name against the profile, Patient and both subject
references. Check values, comparator, units, status, date precision and uncertainty
against the readable citations. Generated IDs and file metadata are bookkeeping.

The DocumentReference attachment URL is `../../sources/source.csv`. From
`drafts/first-import/` it resolves to the retained source. If a real reviewer
approves the exact final files and they are copied unchanged to
`records/first-import/`, the same URL still resolves to that source.
The focused tests exercise this copy in a temporary directory and verify the
bytes and links; they never assert human acceptance.

No accepted directory or approval note is supplied here. In real use, record the
actual reviewer, date, person ID, exact approved files/version and remaining
concerns separately. Any draft change needs fresh review. Corrections create a
new version and retain the source, prior record, evidence and decision.
Schema validity cannot establish clinical truth or source authenticity.
