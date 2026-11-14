# Helseark

A local personal and family health archive toolkit, under development.

Canonical clinical records use FHIR R4, with retained source evidence, explicit human review, and immutable history. Normal archive operations are offline. No medical correctness or release readiness is claimed.

Follow the [documentation index](docs/index.md) and
[synthetic first-archive lesson](docs/tutorials/first-archive.md).
Implemented boundaries include explicit person identity, retained PDF sources,
untrusted candidates, exact-byte human review and immutable publication,
longitudinal queries, offline backup/restore and recoverable person removal.
See [corrections](docs/how-to/correct-record.md) and
[family privacy/removal limits](docs/how-to/manage-family.md).

FHIR validation coverage and extraction quality remain limited to documented
checks and examined synthetic cases. Supplied candidates do not measure model
extraction accuracy. No HL7 endorsement or clinical certification is implied.
