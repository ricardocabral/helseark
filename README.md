# Helseark

A local personal and family health archive toolkit, under development.

Canonical clinical records use FHIR R4, with retained source evidence, explicit human review, and immutable history. Normal archive operations are offline. No medical correctness or release readiness is claimed.

Task 1 implements offline vault initialization and explicit person creation.
See the [archive format and supported commands](docs/reference/archive-format.md)
for the file contract, Python interfaces and tested crash behavior.
Clinical import and full FHIR validation are not implemented yet.
