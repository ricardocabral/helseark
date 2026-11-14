# Import structured data offline

Use `helseark --vault VAULT intake fhir-r4 export.json --person PERSON --mapping mapping.json --json`.
The command retains original bytes and returns a candidate directory, never accepted records.
Create the mapping yourself outside the untrusted export:

```json
{"patientReference":"Patient/source-id","localPersonId":"YOUR-LOCAL-UUID","assignmentReason":"I checked the original and assigned this export","provider":"https://provider.example/fhir"}
```

`patientReference` must name exactly one incoming Patient by Type/id or fullUrl.
No identity matching, source-prose configuration, EHR login or network retrieval occurs.
FHIR R4 4.0.1 JSON Bundles support the existing bounded Observation, DiagnosticReport,
Specimen, DocumentReference and Provenance profiles. Patient fields remain in the
original export with an explicit local assignment; they never overwrite local identity.
Clinical fields and statuses stay native FHIR. Native IDs/version metadata are retained
in source evidence and identifiers; candidate IDs are new UUIDs. Preparation assigns
immutable local revision IDs and rewrites closed references, including native version references.
Unresolved references, other patients, unsupported resources/fields/extensions, external
attachments and invalid clinical data block preparation. They cannot be waived by review.
Coverage and mapping are in `coverage.json`; its SHA-256 is bound to candidate metadata.
Edits to this explanatory sidecar do not authorize different candidate bytes.

Next run `helseark --vault VAULT candidate prepare CANDIDATE --person PERSON --json`.
Inspect with `candidate review PROPOSAL --person PERSON --json`. Read the originals,
all mapped fields, source coordinates, identity, inventory and limitations. Supply your
own explicit decision JSON through `candidate review PROPOSAL --person PERSON
--decision decision.json --json`, then `candidate commit PROPOSAL --person PERSON --json`.
See [review contract](../reference/review.md) for exact decisions and acknowledgments.
No adapter supplies a real user's acceptance decision. Synthetic tests use pre-authored
fixture human decisions only; these are not real clinical approval.
Query accepted facts with `observations --person PERSON --json` and resolve exact
revisions with `record --person PERSON --resource Type/UUID/_history/UUID --json`.
The [query guide](query-history.md) explains statuses and historical selection.

Parser evidence names the actual JSON parser and source JSON pointers. Local identity,
profile allocation and reference/identifier mapping are explicit transformations requiring
human inspection; validation is not a claim of clinical correctness or complete FHIR conformance.
Original source bytes and accepted revisions are immutable. Existing vaults retain their
kit and definition pins; installing a newer package never repins them automatically.
