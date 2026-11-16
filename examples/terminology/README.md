# Invented bilingual terminology draft

Sam Synthetic and every laboratory result are invented. All files are **unreviewed
drafts**. There is no accepted record, approved mapping rule or human approval.
This example supplements the unchanged [first import](../README.md), whose
source-only C-reactive protein label remains uncoded.

Read the [source CSV](sources/laboratory.csv), [profile](profile.fhir.json),
[native FHIR Bundle](drafts/bilingual-ldl/bundle.fhir.json),
[citations](drafts/bilingual-ldl/evidence.md), [mapping decisions](drafts/bilingual-ldl/mapping-evidence.json)
and [review note](drafts/bilingual-ldl/review.md). Mapping proposals and evidence
record coding decisions; they are not a separate editable clinical store.

| CSV data row (physical line) | Source label | Draft result | Coding decision |
| --- | --- | --- | --- |
| 1 (2) | Colesterol LDL calculado | 103.00 mg/dL, 2026-03-01 | Proposed LOINC 13457-7 |
| 2 (3) | Calculated LDL cholesterol | 103.00 mg/dL, 2026-04-01 | Same proposed LOINC 13457-7 |
| 3 (4) | LDL | 105.0 mg/dL, 2026-05 | Unresolved; specimen and method absent |

The two supported rows explicitly supply LDL cholesterol, mass concentration,
point-in-time sampling, quantitative scale, serum/plasma and calculation. Their
Portuguese/English labels remain in `Observation.code.text`; agent-assigned
standard codes appear in native `code.coding`, separately attributed in mapping
evidence. Original decimal scale, units, dates and source context remain intact.
A code-only selection for this LOINC includes the first two rows and excludes the
ambiguous third row. This grouping supplies no interpretation or medical advice.

## Catalog provenance and limits

The [primary LOINC concept page](https://loinc.org/13457-7/) was read on
2026-11-16. It verifies code 13457-7, its long common name and six axes. The
example selects package version `2.83`; the current public concept page does not
authenticate the contents of that release. Real use must verify the locally
retained official release before assigning its version.

The [mini-catalog](mini-catalog/) is a **synthetic test fixture, not an official
LOINC or UCUM distribution**. Its one-row catalog uses a real code/name/axes;
its Portuguese label is an invented search alias. The tiny UCUM XML supports
only the example's syntax and claims no standard coverage. Tests assemble it
into a local ZIP and exercise offline installation/checking. Do not install this
fixture as a clinical terminology package. No official release files are bundled.

LOINC code and name excerpts are copyright Regenstrief Institute, Inc. and the
LOINC Committee; all rights reserved. See the [LOINC license](https://loinc.org/license/).
The standard-derived row is not covered by the project's MIT grant.

## Run the example checks

From the repository root, after the documented schema dependency setup:

```sh
uv run --no-sync python -m unittest discover -s tests -p test_terminology_examples.py -v
```

The test reads the retained CSV, Bundle, proposals and citations; validates the
Bundle and every resource against the pinned FHIR R4 schema; preserves decimal
scale with `Decimal`; and checks helper proposals against the synthetic local
package. It exercises VLDL, ratio-property, urine-specimen and direct-method
conflicts. These checks do not establish clinical correctness or human review.

The DocumentReference attachment URL `../../sources/laboratory.csv` resolves
from either `drafts/bilingual-ldl/` or a future `records/bilingual-ldl/`. Tests
copy bytes to temporary directories only; this does not accept the draft.
