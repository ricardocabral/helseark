# Clinical model and offline validation

Applies to Helseark contracts/profiles **0.1.0**, archive format **1**, FHIR
**R4 4.0.1**. Clinical facts are native FHIR resources, never a parallel lab model.
Every import needs human review of the final prepared bytes. Validation does not
establish extraction accuracy, source identity, consent or medical correctness.

## Supported graph

Six [local profiles](../../profiles/r4/0.1.0/README.md) use canonical base
`https://github.com/ricardocabral/helseark/fhir`, with `|0.1.0` declarations:
Patient, Observation, DiagnosticReport, Specimen, DocumentReference, Provenance.
A candidate is a standard `Bundle` with `type=collection`. Bundle is a transport,
not a seventh clinical profile. Unsupported resources/elements stay in the
original retained source and block the structured candidate; no field is dropped.

The runtime checks actual upstream draft-06 JSON Schema, inherited cardinalities
and choices from genuine core snapshots, and the selected local differential
rules. It checks required statuses, direct subjects, exact profile declarations,
Observation value/absence and component exclusion, obs-3 and obs-7,
SimpleQuantity comparator restrictions, range ordering/units and nonzero ratio
denominators. Empty/null FHIR values, contained resources, ordinary extensions,
modifier extensions and implicitRules are unsupported. Primitive extension
substitutes are unsupported, including when the upstream schema permits them.
There is no general FHIRPath interpreter or claim of full FHIR conformance.

Source assets are bounded to 100 MiB before reading; candidate graphs to 10,000
resources and individual clinical strings to 1 MiB. Strict serialization bounds
nesting and numeric size. No truncation occurs.

The bounded top-level fields are:

| Resource | Clinical fields |
| --- | --- |
| Patient | identifier, active, name, telecom, gender, birthDate, deceasedBoolean/DateTime, address, maritalStatus, multipleBirthBoolean/Integer |
| Observation | identifier, status, category, code, subject, effectiveDateTime/Period/Instant, issued, performer, supported value choices, dataAbsentReason, interpretation, note, bodySite, method, specimen, referenceRange, hasMember, derivedFrom, component |
| DiagnosticReport | identifier, status, category, code, subject, effectiveDateTime/Period, issued, performer, resultsInterpreter, specimen, result, conclusion, conclusionCode, presentedForm |
| Specimen | identifier, accessionIdentifier, status, type, subject, receivedTime, parent, collection, processing, container, condition, note |
| DocumentReference | masterIdentifier, identifier, status, docStatus, type, category, subject, date, author, authenticator, custodian, relatesTo, description, securityLabel, content, context |
| Provenance | target, occurredPeriod/DateTime, recorded, policy, location, reason, activity, agent, entity |

Common bookkeeping fields are resourceType, UUID id, local meta, language and
narrative text. Candidate meta contains only profile; prepared meta also contains
versionId/lastUpdated. Source meta.security/tag/source semantics remain in the
retained original and are unsupported as generated local bookkeeping. Complex children must satisfy upstream structure/cardinality and the
implemented invariant subset; their presence is not a claim of checking every
FHIR invariant or terminology binding. References restrict this surface further:
unsupported Practitioner, Organization, Encounter and Device resources cannot be
resolved as structured records. A source issuer/actor can use an explicit local
identifier where its native Reference allows it. Subjects must be literal.
Supported Observation values are Quantity, CodeableConcept, string, boolean,
integer, Range, Ratio, time, dateTime and Period; SampledData is unsupported.

## Identity, references and versions

Every clinical operation explicitly selects a person UUID. Task 1 `person add`
retains its narrow, self-reported Patient constructor and exact metadata contract.
That accepted identity is resolvable without claiming full profile conformance;
new Patient resources submitted in candidates must declare the local profile. Patient.id equals that person;
every Observation, report, specimen and source document has its own explicit
Patient subject. A report does not supply an omitted child's subject. Provenance
has no subject: all its targets and source entities must resolve inside the
selected person's graph. Source entities must be DocumentReferences and actors
must have a literal reference or a local identifier with a value.

Candidate entries have `fullUrl=urn:uuid:<logical-id>`. New-resource links use
these URNs; existing context links use `Type/id/_history/revision`. Patient
identity uses `Patient/id`. Candidates cannot assign archive versionId or
lastUpdated. Preparation (Task 6) assigns revisions and rewrites known URNs;
prepared context-sensitive references, including Provenance targets/source
entities, must be revision pinned. Proposal validation builds a temporary lookup
of revision URNs without modifying retained resources. It is not the Task 10
full-validator derived context export. Remote, dangling, escaping, wrong-type,
cross-person and cross-FHIR-version links fail. Accepted references are resolved
at the exact candidate/proposal base, and the complete reachable local graph is
checked for scope. No remote reference is fetched.

`DocumentReference.content.attachment` requires title, contentType and exactly
`assets/sha256/<64-lowercase-hex>/blob`, interpreted from the person's archive
base. Inline data is unsupported. Hash/size checks read those retained bytes.
Optional Attachment.hash is base64 SHA-1; archive SHA-256 belongs in the inventory.

## Values, units, dates and unknowns

Use the exact decimal-preserving serializer. `0.050` retains its scale. A printed
`<0,050 mg/L` is a Quantity value `0.050`, comparator `<`, printed unit `mg/L`;
it is not an exact point measurement. No unit conversion or terminology mapping
runs. Preserve text-only codes, qualitative results, absence explanations,
ratios/ranges, component values, method-specific panel children and narratives.
ReferenceRange low/high use genuine SimpleQuantity constraints; preserve “less
than 5” as text when inclusive numeric bounds cannot express the source.

Partial dates remain year/month/day strings. Calendar dates are checked.
Instants and clock-valued dateTimes require seconds and explicit offsets; an
unknown offset is blocking in a FHIR timestamp and emits DATE_TIMEZONE_UNKNOWN
for review. Retain the original clock as evidence; reduce to a date only with
an explicit review issue. The runtime does not infer timezone or source meaning.
FHIR leap seconds are outside this bounded timestamp implementation and fail
explicitly. Status is clinical source status, distinct from archive approval.
Amended/corrected/cancelled/entered-in-error remain source assertions.

Source-supplied coding remains unchanged with CODING_UNVERIFIED; terminology is
not checked. No LOINC/UCUM code is invented. Contradictions and unresolved source
facts remain explicit issues, never silently reconciled. Error-severity issues
block; review-severity issues require acknowledgment in the later review workflow.

## Evidence checklist

[The evidence schema](../../schemas/0.1.0/evidence.schema.json) accepts source,
generated and explicit user-entry evidence. Legacy single-pointer user/generated
records remain readable for Task 1 genesis. Runtime imports use `target.reference`
and a nonempty `target.pointers` array of JSON Pointers relative to that resource.
Every scalar field in each produced resource needs evidence, except resourceType.
Prepared evidence targets the exact produced `Type/id/_history/version` revision.
This deliberately covers all clinical leaves, including:

- source patient identity cues and explicit subject assignment;
- code/label and every supplied coding, source status and absence explanation;
- values/comparators/units, effective/issued/collection dates and precision;
- ranges and applicability, specimen, method, body site and interpretation;
- components and panel children independently, report issuer/conclusions;
- provenance actors/source links and all other supplied clinical metadata.

Generated id/meta and the content-addressed attachment URL require generated
evidence with a nonempty rule ID. Generated evidence cannot cover clinical
facts. Explicit user-entry evidence is restricted to prepared Patient records;
source identity still requires human confirmation. A source entry binds
sourceSha256, sourceDocument, quote and locator. The source document must resolve
to a local DocumentReference containing the same asset digest. Declared source
hashes and retained source/extraction hashes are verified without fetching.

| Locator | Checked against retained bytes |
| --- | --- |
| json-pointer | Strict RFC 6901 pointer into strict JSON; quote occurs in pointed value |
| text-span | extractionSha256, half-open Unicode code-point start/end, bounds and quote |
| csv-cell | UTF-8 CSV, explicit one-character delimiter, 1-based data row and column name |
| pdf-page | extractionSha256 of JSON `{sourceSha256,pages:[{page,rotation,text}]}`, 1-based page, rotation and quote |

PDF boxes are optional `[left,top,right,bottom]`, ordered and bounded in `[0,1]`,
coordinateSpace `displayed-cropbox-top-left-normalized`, rotation 0/90/180/270.
The baseline checks the retained extraction artifact, not the correspondence
between that extraction and PDF rendering. It cannot prove page/row attribution.
A forged extraction remains a human review concern, not a machine proof.

Known `decimal-comma-v1` transformations check numeric value/scale and comparator
against the retained quote. Other transformation rules emit review issues rather
than claiming validation. Quote occurrence is text consistency only; it does not
prove a clinical field was extracted correctly, even for a clean candidate.

## Library and CLI

`load_definition_registry(vault)` verifies every lock inventory byte and returns
an offline resolver. Unknown/missing IDs fail MISSING_DEFINITION; changed bytes
fail DEFINITION_MISMATCH. `resolve(identifier)` returns a definition, not a network
request. The complete genuine core package archive is installed alongside the selected
extracted definitions; other core StructureDefinitions resolve lazily from its
verified members. No member is extracted to a source-controlled path at runtime.
The genuine upstream schema retains draft-06; local envelopes retain
2020-12. Unsupported dialects fail explicitly. Definition files are unmodified
upstream bytes; the extra genuine SimpleQuantity is pinned as a member of the
same acquired official core archive. The complete core is retained at `definitions/runtime-core/4.0.1/hl7.fhir.r4.core.tgz`;
SimpleQuantity resolves from its actual member. The earlier extracted subset and
its vendoring inventory remain unchanged and independently verifiable.

`validate_candidate(vault, Candidate)` reads candidate.json and its confined
bundlePath/evidencePath, matches the supplied immutable record to disk, checks
base/version pins, graph and evidence, and returns a ValidationReport.
`validate_proposal(vault, directory)` checks exact inventory/resource/evidence/
source bytes before review and binds checkedProposalSha256 to proposal.json.
Import proposals also carry the candidate
`unresolved` issue array (required by runtime when producing clinical records);
identity mismatch/unknown identity stays fatal even if a producer labels it a
review issue. It neither creates a review receipt nor publishes a change. The internal storage
primitive is not a supported arbitrary clinical import API; Task 6 must call
proposal validation and enforce digest-bound review before publishing imports.

```sh
helseark --vault /path/to/vault schema export --resource Observation --out ./agent-contracts
helseark --vault /path/to/vault validate candidate ./candidate --person UUID --json
helseark --vault /path/to/vault validate proposal ./prepared --person UUID --json
```

Schema export works without a vault using installed version pins, or with an
explicit vault using its exact retained pins. It includes the complete pinned
**runtime inventory**, including the unchanged complete core archive, licenses,
profiles, schemas, reference and a packet manifest. The selected extracted definitions and reference pages are a bounded subset;
the compressed core package is complete. The complete specification and separate
archival verifier remain in the archival deliverable. Retaining the full core
does not qualify an official validator or make terminology checks available.
The installed wheel and initialized vault contain actual pinned files; they do
not depend on checkout or acquisition-cache paths. The destination must be absent.

JSON output contains coverage and issues with pointers and resource references.
Exit 0 means baseline checks passed, 2 blocked input, 3 review issues, 4 stale
base, 5 integrity/I/O and 6 missing definitions/unsupported capabilities.
Terminology, full FHIR validation and extraction accuracy remain `not-checked`.
An earlier structural failure leaves later families `not-checked`, never passed.
No output declares an extraction or medical assertion correct.
