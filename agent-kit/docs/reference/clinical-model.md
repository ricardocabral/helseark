# Clinical model and offline validation

Applies to Helseark contract **0.1.0**, profile sets **0.1.0/0.2.0**, archive format **1**, FHIR
**R4 4.0.1**. Clinical facts are native FHIR resources, never a parallel lab model.
Every import needs human review of the final prepared bytes. Validation does not
establish extraction accuracy, source identity, consent or medical correctness.

## Supported graph

The frozen [profile set 0.1.0](../../profiles/r4/0.1.0/README.md) supports six types:
Patient, Observation, DiagnosticReport, Specimen, DocumentReference, Provenance.
The additive [0.2.0 package](../../profiles/r4/0.2.0/README.md) depends on that
unchanged package and adds MedicationStatement, MedicationRequest, Condition,
AllergyIntolerance, Immunization, Procedure, Encounter and FamilyMemberHistory,
plus Provenance 0.2.0 for the expanded target graph. Profile set 0.2.0 therefore
supports **14 clinical resource types**, with **15 versioned StructureDefinitions**
retained locally: six at 0.1.0 and nine at 0.2.0, including both Provenance versions.
All use canonical base `https://github.com/ricardocabral/helseark/fhir`.
The original six retain `|0.1.0` declarations; the eight added types require
`|0.2.0`. Provenance may declare `|0.2.0` in a 0.2.0 vault; its original `|0.1.0`
declaration remains supported with its original target constraints. A vault's
profile-set pin does not relabel every resource with that version.

A candidate is a standard `Bundle` with `type=collection`. Bundle is a transport,
not an additional clinical profile. Its bookkeeping allows only resourceType, type,
entry, id and optional meta.versionId/meta.lastUpdated. Entries contain only
fullUrl/resource. Security, source, profile/tag metadata and all nested primitive
metadata/extensions on the Bundle are unsupported. Transport revision labels
have no clinical meaning and do not replace resource evidence. Unsupported
incoming resources/elements remain in the original retained source and are itemized
with locations and reasons as not structured in the report and candidate unresolved
issues. A faithful supported subset may be drafted, with explicit coverage and
omissions; it must not claim complete mapping/import. Unsupported resources/elements
emitted inside the structured Bundle fail validation. Review-level issues or human
acknowledgment cannot waive errors, identity failures or required evidence.

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

The bounded top-level fields below apply to the six original types in both
profile sets and to the eight added types only in profile set 0.2.0:

| Resource | Clinical fields |
| --- | --- |
| Patient | identifier, active, name, telecom, gender, birthDate, deceasedBoolean/DateTime, address, maritalStatus, multipleBirthBoolean/Integer |
| Observation | identifier, status, category, code, subject, effectiveDateTime/Period/Instant, issued, performer, supported value choices, dataAbsentReason, interpretation, note, bodySite, method, specimen, referenceRange, hasMember, derivedFrom, component |
| DiagnosticReport | identifier, status, category, code, subject, effectiveDateTime/Period, issued, performer, resultsInterpreter, specimen, result, conclusion, conclusionCode, presentedForm |
| Specimen | identifier, accessionIdentifier, status, type, subject, receivedTime, parent, collection, processing, container, condition, note |
| DocumentReference | masterIdentifier, identifier, status, docStatus, type, category, subject, date, author, authenticator, custodian, relatesTo, description, securityLabel, content, context |
| Provenance | target, occurredPeriod/DateTime, recorded, policy, location, reason, activity, agent, entity |
| MedicationStatement | identifier, status, statusReason, category, medicationCodeableConcept, subject, context, effectiveDateTime, effectivePeriod, dateAsserted, informationSource, derivedFrom, reasonCode, reasonReference, note, dosage |
| MedicationRequest | identifier, status, statusReason, intent, category, priority, doNotPerform, reportedBoolean, medicationCodeableConcept, subject, encounter, supportingInformation, authoredOn, requester, reasonCode, reasonReference, instantiatesCanonical, instantiatesUri, basedOn, groupIdentifier, courseOfTherapyType, insurance, note, dosageInstruction, dispenseRequest, substitution, priorPrescription, detectedIssue, eventHistory |
| Condition | identifier, clinicalStatus, verificationStatus, category, severity, code, bodySite, subject, encounter, onsetDateTime, onsetAge, onsetPeriod, onsetRange, onsetString, abatementDateTime, abatementAge, abatementPeriod, abatementRange, abatementString, recordedDate, recorder, asserter, stage, evidence, note |
| AllergyIntolerance | identifier, clinicalStatus, verificationStatus, type, category, criticality, code, patient, encounter, onsetDateTime, onsetAge, onsetPeriod, onsetRange, onsetString, recordedDate, recorder, asserter, lastOccurrence, note, reaction |
| Immunization | identifier, status, statusReason, vaccineCode, patient, encounter, occurrenceDateTime, occurrenceString, recorded, primarySource, reportOrigin, location, manufacturer, lotNumber, expirationDate, site, route, doseQuantity, performer, note, reasonCode, reasonReference, isSubpotent, subpotentReason, education, programEligibility, fundingSource, reaction, protocolApplied |
| Procedure | identifier, instantiatesCanonical, instantiatesUri, basedOn, partOf, status, statusReason, category, code, subject, encounter, performedDateTime, performedPeriod, performedString, performedAge, performedRange, recorder, asserter, performer, location, reasonCode, reasonReference, bodySite, outcome, report, complication, complicationDetail, followUp, note, focalDevice, usedReference, usedCode |
| Encounter | identifier, status, statusHistory, class, classHistory, type, serviceType, priority, subject, episodeOfCare, basedOn, participant, appointment, period, length, reasonCode, reasonReference, diagnosis, account, hospitalization, location, serviceProvider, partOf |
| FamilyMemberHistory | identifier, instantiatesCanonical, instantiatesUri, status, dataAbsentReason, patient, date, name, relationship, sex, bornPeriod, bornDate, bornString, ageAge, ageRange, ageString, estimatedAge, deceasedBoolean, deceasedAge, deceasedRange, deceasedDate, deceasedString, reasonCode, reasonReference, note, condition |

Common bookkeeping fields are resourceType, UUID id, local meta, language and
narrative text. Candidate meta contains only profile; prepared meta also contains
versionId/lastUpdated. Source meta.security/tag/source semantics remain in the
retained original and are unsupported as generated local bookkeeping. Complex children must satisfy upstream structure/cardinality and the
implemented invariant subset; their presence is not a claim of checking every
FHIR invariant or terminology binding. References restrict this surface further:
unsupported Practitioner, Organization and Device resources cannot be resolved
as structured records. Encounter is supported in profile set 0.2.0; each native
Reference must still satisfy its allowed target types and local profile constraints.
A source issuer/actor can use an explicit local
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

[The evidence schema](../../schemas/0.1.1/evidence.schema.json) accepts source,
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

Derived text/PDF locators require `extraction` with `provenanceVersion="1"`.
Known provenance has `status="known"`, nonempty method/tool/version, an explicit
model object `{name,version}` (required for ocr/model/llm methods; null means not
applicable for other methods), and a preprocessing array. An empty array means
no preprocessing; each step names method/tool/version and exact parameters.
These fields describe the producer's declared process; checking them does not
attest that the engine was run. Direct original JSON/CSV evidence requires no
extraction engine. Missing/partial derived provenance fails the envelope. If the
process is unknown, use `{"provenanceVersion":"1","status":"unknown","reason":"..."}`;
it emits EXTRACTION_PROVENANCE_UNKNOWN for mandatory review. Historic vaults
retain their original schema pins; missing legacy provenance still requires
review. No accepted history or contract inventory is rewritten on open.

Known `decimal-comma-v1` transformations check numeric value and fixed-form scale
(including integers) against the retained quote. Target the complete Quantity
or all relevant value/comparator/unit pointers to check those leaves together.
A value-only pointer does not verify comparator/unit evidence elsewhere. Other transformation rules emit review issues rather than claiming validation. Quote occurrence is text consistency only; it does not
prove a clinical field was extracted correctly, even for a clean candidate.

## Library and CLI

`load_definition_registry(vault)` verifies every lock inventory byte and returns
an offline resolver. Unknown/missing IDs fail MISSING_DEFINITION; changed bytes
fail DEFINITION_MISMATCH. `resolve(identifier)` returns a definition, not a network
request. The complete genuine core package archive is installed alongside the
selected extracted definitions; all 655 core StructureDefinitions are indexed
by their actual canonical URL
and optional resource version from bounded verified members. A member without
version resolves unversioned only; package version 4.0.1 is separate acquisition
provenance in the definition lock and never fabricates a resource version.
Actual duplicate core identities or conflicting extracted/core definitions fail
DEFINITION_IDENTITY_CONFLICT. Registry completeness does not expand the supported
clinical graph: six types for profile set 0.1.0, or 14 for profile set 0.2.0.
The current local profile inventory contains 15 versioned StructureDefinitions,
including both Provenance versions; resolving a core definition alone does not
enable that resource type. No member is extracted to a source-controlled path
at runtime.
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
explicit vault (or HELSEARK_VAULT) using its exact retained pins. The
`archive.open_definitions(root)` opener checks config, version pins and the full
definition inventory without enumerating or opening people. Schema export uses
it; clinical commands keep `open_vault` and its full household history checks.
An unrelated corrupt patient cannot block definition export. Export includes the
complete pinned
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
Malformed source candidate JSON, including numeric/duplicate/depth limits,
exits 2. Retained proposal/resource/evidence corruption exits 5. Unsupported
candidate/proposal version pins exit 6 before generic envelope checks. Source
JSON keeps its independent 128-digit coefficient/exponent bounds; final fixed
resource and evidence bytes use the canonical reader, including expansions of
1e128 and 1.0e-128. Neither boundary narrows the approved source number domain.

The derived provenance contract is tightened before the 0.1.0 contract freeze;
producers must supply the new versioned object or explicitly request unknown
provenance review. Candidate/ValidationReport function signatures stay unchanged.
Task 3/4 contexts and templates should describe the new evidence object and
schema-export opener. Task 6 still owns full producer/prompt provenance,
reconciliation, generated Provenance, review receipts and clinical publication;
Task 10 owns official validator qualification.

Terminology, full FHIR validation and extraction accuracy remain `not-checked`.
An earlier structural failure leaves later families `not-checked`, never passed.
No output declares an extraction or medical assertion correct.

## Query projections and time selection

`observations(vault, person, ObservationFilter(...), at=Head(...))` reads only the
selected person's accepted files. Omit `at` for the current graph. Historical
queries use the graph at that exact Head, not today's children substituted into
old reports. `timeline` includes all current-at-snapshot resource statuses,
including cancelled and entered-in-error. It does not enumerate every superseded
revision; use an older Head or an exact `record` revision to inspect those bytes.
`DiagnosticReport.result` stays pinned. `REPORT_RESULT_REVISION_MISMATCH` marks
reports whose child revision differs from the snapshot's current result, on both
the report and current observation. There is no automatic cascade.

Each observation preserves its native `value[x]` subtree and `valueType`,
components, absent reason, interpretation, notes, ranges, method, specimen,
status and references. Decimal JSON retains scale; `<0.050` is a bound, not a
point measurement. Equal labels never establish comparability. No grouping,
aggregation, terminology inference or unit conversion occurs. Exact label means
`code.text`; code and system constraints must match the same `coding` item.
Cancelled/entered-in-error observations require `includeInvalidated=True` (CLI
`--include-invalidated`); other nonnumeric and absent results remain visible.

Bounds are inclusive valid `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, or offset timestamps.
Calendar bounds compare the source's displayed calendar without assigning a
zone. Timestamp bounds compare UTC instants; they cannot be mixed with calendar
bounds. A date-only value in an instant query remains `unknown` in relation to
that filter; no timezone is inferred. Partial dates and periods denote possible
intervals: `contained` if wholly inside, `overlap` if intersecting. Undated values
remain visible in `timeBucket=unknown` with `timeFilterRelation=unknown`.
`effective` remains the original FHIR value with `effectiveType` and precision;
comparison intervals are not emitted as fabricated timestamps. Stable resource
identity order is presentation order, not a total clinical chronology.

`sourceRefs` are exact accepted evidence bindings: vault-relative evidence path,
SHA-256, JSON entry pointer, and original source digest/document where present.
Resolve that entry under the selected person's accepted directory for its
original quote, locator, target pointers and extraction details. These bindings
also identify generated/user-entry evidence without fabricating a source digest.
They do not embed potentially broader source prose in a query row. Giving a model
raw evidence or a whole source is a separate disclosure decision. Agent contexts
continue to use the scoped evidence selector, fail closed on ambiguous projections,
and require the construction authority retained outside the editable packet.

Date-filtered query contexts use this same query module for every selected native
record (including pinned historical revisions). They preserve explicit reference
selection and include `QUERY_TIME_SELECTION` metadata issues with bounds,
precision, bucket and relation for each returned record. Unknown dates remain
selected. Continuations bind the person, task, source/reference selection, date
bounds, kit digest and Head. Counts and record/evidence budgets apply per page;
no filter failure falls back to an unfiltered or all-person scan.

## Structured R4 import

[Structured import](../how-to/import-structured-data.md) uses explicit incoming Patient and
provider mapping through candidates and the production review boundary. Source-native
identities never become local logical/revision IDs. Unsupported data remains in original
bytes and blocks silent loss; accepted history is never rewritten by an adapter.

Mapped numeric CSV rows use the same FHIR Observation profile and review boundary.
Every row stays distinct, status is explicitly unknown, coding is source text or a
locally declared source namespace, and evidence links to the exact original CSV cell.
Unknown or ambiguous time/identity/mapping never authorizes acceptance.


Structured R4 import inventories unsupported content throughout the export envelope
and all entries, including nested meta/link/search extensions, primitive companions,
modifiers and escaped unknown fields. Each has a blocking source pointer; original
byte retention alone is not a supported disposition. Exact source-local host issuance
binds mapped candidates and coverage independently of their editable IDs or paths.

### History profile compatibility and query

Profile set 0.2.0 adds source-assertion history families. The original six
profiles remain byte-identical at version 0.1.0. Provenance 0.2.0 widens the
native target and revision-entity boundaries to include the added families; the original Provenance
0.1.0 remains supported. New vaults pin profile set
0.2.0 and kit 0.1.15; existing 0.1.0 vaults continue using their retained locks,
profiles and kits. They are readable without migration. New history resources
require a 0.2.0 vault and its pinned history definitions; do not edit vault pins
or repin accepted history to upgrade. No persisted clinical meaning is rewritten. Source entities still require selected-person
DocumentReference revisions. Other entities must resolve to supported resources;
accepted references retain exact revisions and cannot cross people. Re-extraction
links the prior exact revision without changing its bytes.
Kit 0.1.15 includes the corrected current Provenance definitions. Earlier
0.2.0 kits also retain their exact definitions; installing new toolkit bytes does
not repair or repin those vaults. Migration identity copies preserve source profile/kit pins; they do not upgrade earlier 0.2.0 definitions.
The archive contract and FHIR release stay 0.1.0 and R4 4.0.1 respectively.

`helseark --vault VAULT history --person PERSON --kind MedicationStatement --json`
returns native assertions and their native Provenance at one head. Repeat `--kind`
for multiple supported families; `--at-head HEAD.json` selects an exact snapshot.
The Python API is `query.history(vault, person, kinds, at=None)`. It returns
FHIR resources, without adding non-FHIR fields. `timeline` includes the complete
native `resource` alongside exact revision, source evidence references and retained
validation issues. This preserves qualifiers without deriving an active diagnosis
or a medication list. Timeline order is identity order, not clinical chronology.
Recording, assertion and event dates remain separate native fields. Partial,
textual, age-based and absent event dates are not converted into invented dates.

### MedicationStatement (profile 0.2.0)

Source assertions use `subject` for the selected Patient. Supported native fields: `identifier status statusReason category medicationCodeableConcept subject context effectiveDateTime effectivePeriod dateAsserted informationSource derivedFrom reasonCode reasonReference note dosage`. Timeline uses ('effectiveDateTime', 'effectivePeriod'), with unknown time retained. Every scalar needs source evidence; acceptance requires human review. Native values and qualifiers survive export/restore without inference.

### MedicationRequest (profile 0.2.0)

Source assertions use `subject` for the selected Patient. Supported native fields: `identifier status statusReason intent category priority doNotPerform reportedBoolean medicationCodeableConcept subject encounter supportingInformation authoredOn requester reasonCode reasonReference instantiatesCanonical instantiatesUri basedOn groupIdentifier courseOfTherapyType insurance note dosageInstruction dispenseRequest substitution priorPrescription detectedIssue eventHistory`. Timeline uses ('authoredOn',), with unknown time retained. Every scalar needs source evidence; acceptance requires human review. Native values and qualifiers survive export/restore without inference.

### Condition (profile 0.2.0)

Source assertions use `subject` for the selected Patient. Supported native fields: `identifier clinicalStatus verificationStatus category severity code bodySite subject encounter onsetDateTime onsetAge onsetPeriod onsetRange onsetString abatementDateTime abatementAge abatementPeriod abatementRange abatementString recordedDate recorder asserter stage evidence note`. Timeline uses ('onsetDateTime', 'onsetPeriod', 'onsetAge', 'onsetRange', 'onsetString'), with unknown time retained. Every scalar needs source evidence; acceptance requires human review. Native values and qualifiers survive export/restore without inference.

Keep Condition verificationStatus (unconfirmed/provisional/differential, refuted,
confirmed) separate from clinicalStatus. Retain onset and recordedDate independently.
Refuted assertions remain visible; there is no inferred active-diagnosis summary.
Contradictory entered-in-error/clinical status and abatement/active status block acceptance.

### AllergyIntolerance (profile 0.2.0)

Source assertions use `patient` for the selected Patient. Supported native fields: `identifier clinicalStatus verificationStatus type category criticality code patient encounter onsetDateTime onsetAge onsetPeriod onsetRange onsetString recordedDate recorder asserter lastOccurrence note reaction`. Timeline uses ('onsetDateTime', 'onsetPeriod', 'onsetAge', 'onsetRange', 'onsetString'), with unknown time retained. Every scalar needs source evidence; acceptance requires human review. Native values and qualifiers survive export/restore without inference.

An explicit no-known-allergies source statement is a nonempty AllergyIntolerance.code.text with its verification/clinical qualifiers and evidence. No records is unknown, not a negative assertion. Preserve suspected versus confirmed/refuted status, reactions and criticality without deriving clinical risk.

### Immunization (profile 0.2.0)

Source assertions use `patient` for the selected Patient. Supported native fields: `identifier status statusReason vaccineCode patient encounter occurrenceDateTime occurrenceString recorded primarySource reportOrigin location manufacturer lotNumber expirationDate site route doseQuantity performer note reasonCode reasonReference isSubpotent subpotentReason education programEligibility fundingSource reaction protocolApplied`. Timeline uses ('occurrenceDateTime', 'occurrenceString'), with unknown time retained. Every scalar needs source evidence; acceptance requires human review. Native values and qualifiers survive export/restore without inference.

Preserve occurrenceDateTime precision or occurrenceString for unknown dates. Keep unknown doseNumberString/series as stated; never calculate dates or series from age. A not-done resource is not an administered vaccine.

### Procedure (profile 0.2.0)

Source assertions use `subject` for the selected Patient. Supported native fields: `identifier instantiatesCanonical instantiatesUri basedOn partOf status statusReason category code subject encounter performedDateTime performedPeriod performedString performedAge performedRange recorder asserter performer location reasonCode reasonReference bodySite outcome report complication complicationDetail followUp note focalDevice usedReference usedCode`. Timeline uses ('performedDateTime', 'performedPeriod', 'performedString', 'performedAge', 'performedRange'), with unknown time retained. Every scalar needs source evidence; acceptance requires human review. Native values and qualifiers survive export/restore without inference.

Preserve performed choices, source status/reason, body site and outcome. Not-done/stopped does not prove completion, and a missing performed time stays unknown.

### Encounter (profile 0.2.0)

Source assertions use `subject` for the selected Patient. Supported native fields: `identifier status statusHistory class classHistory type serviceType priority subject episodeOfCare basedOn participant appointment period length reasonCode reasonReference diagnosis account hospitalization location serviceProvider partOf`. Timeline uses ('period',), with unknown time retained. Every scalar needs source evidence; acceptance requires human review. Native values and qualifiers survive export/restore without inference.

Preserve class, status/statusHistory and period. Cancelled/planned encounters are not proof of a completed visit. Do not use an encounter period as an observation measurement time.

### FamilyMemberHistory (profile 0.2.0)

Source assertions use `patient` for the selected Patient. Supported native fields: `identifier instantiatesCanonical instantiatesUri status dataAbsentReason patient date name relationship sex bornPeriod bornDate bornString ageAge ageRange ageString estimatedAge deceasedBoolean deceasedAge deceasedRange deceasedDate deceasedString reasonCode reasonReference note condition`. Timeline uses ('date',), with unknown time retained. Every scalar needs source evidence; acceptance requires human review. Native values and qualifiers survive export/restore without inference.

The patient is the selected person; relationship and condition describe a relative. Never emit the relative assertion as the selected person's Condition, or resolve another person's vault from relationship/name text. Preserve age/born/deceased choices and unknown family history without inventing dates.
