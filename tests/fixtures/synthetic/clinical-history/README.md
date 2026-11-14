# Synthetic clinical history assertions

Original CC0 synthetic fixtures, never real health data. Each JSON file contains
native FHIR R4 source assertions for one family (17 assertions, eight families).
PERSON is replaced only by the explicitly selected synthetic test patient UUID.
IDs and immutable revision metadata are assigned through normal preparation.
Decimals intentionally retain scale: 1.250, 2.500, 0.500 and 45.00.

These are source fixtures, not accepted records or evidence of model accuracy.
The behavioral tests bind each scalar to exact retained JSON source locations,
validate, require synthetic human review, publish, query, export and restore.
Reported use/prescription/adherence, suspected/refuted/confirmed conditions,
explicit negative allergy assertions, uncertain occurrence/series, not-done
procedures, cancelled encounters and unknown relative history remain distinct.

The [independent oracle](oracle/README.md) adds eight manually specified source
assertions and separately authored expected facts through the public acceptance
workflow. It complements these generated-source storage roundtrips.
