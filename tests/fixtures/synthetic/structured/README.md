# Synthetic structured import fixtures

All people, providers, metrics and values are invented. r4.json is a three-resource
R4 collection with a native amended Observation 1.200 mg/L and report pinned to native
version 7. metrics.csv has a UTF-8 BOM, semicolon delimiter, decimal commas, two distinct
rows asserting <0.0500 mg/L and an inert formula-like label asserting 1.200 mg/L.
Tests supply explicit fixture human decisions solely to exercise the real production
prepare/review/commit/query boundary; these are not clinical approval or model evaluation.
