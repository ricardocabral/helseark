# Helseark

A local personal and family health archive toolkit, under development.

Canonical clinical records use FHIR R4, with retained source evidence, explicit human review, and immutable history. Normal archive operations are offline. No medical correctness or release readiness is claimed.

Task 1 implements offline vault initialization and explicit person creation.
See the [archive format and supported commands](docs/reference/archive-format.md)
for the file contract, Python interfaces and tested crash behavior.
Clinical import and full FHIR validation are not implemented yet.

[Prepare a PDF import](docs/how-to/import-report.md) or follow the
[synthetic first-intake lesson](docs/tutorials/first-archive.md). Task5 creates
untrusted drafts; Task6 review/publication remains unavailable.

For explicit deeper R4/profile checks, see [optional offline official validator](docs/how-to/run-offline-validator.md). Baseline use needs no Java; terminology remains not checked.
