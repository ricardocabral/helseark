# Helseark FHIR R4 profiles 0.1.0

These six constrained StructureDefinitions describe the supported clinical
surface of the offline archive. They derive from the genuine retained HL7 FHIR
R4 **4.0.1** definitions, without modifying upstream bytes. Native clinical
fields remain authoritative. Structural checks do not establish extraction
accuracy or medical correctness; every import still requires human review.

## Identity and compatibility freeze

The project-controlled canonical base is
`https://github.com/ricardocabral/helseark/fhir`. Repository ownership supplies a
stable namespace without asserting ownership of an unrelated domain. It is an
identifier base: neither the base nor individual canonical URLs promise a live
FHIR server or HTTP endpoint. Normal operations resolve them from a pinned
local registry, with no network fallback. Moving repository hosting must not
silently change existing profile identities.

Each canonical is `<base>/StructureDefinition/helseark-<slug>`, and each resource
must include the **versioned** canonical `...|0.1.0` in `meta.profile`. Slugs are
`patient`, `observation`, `diagnostic-report`, `specimen`, `document-reference`,
and `provenance`. The package ID is `helseark.fhir.r4`, version `0.1.0`, with
exact dependency `hl7.fhir.r4.core: 4.0.1`. No example.org canonical is shipped.

Treat these identities, differential constraints and release bytes as the
0.1.0 compatibility freeze after independent review and lock integration.
Changes to accepted meaning or rejection rules require an explicit compatibility
decision and a new profile version, even before 1.0. Do not rewrite archived
resources or relabel them as a newer profile. Existing archives retain their
exact definitions and hashes; incompatible changes require explicit migration.
This directory is the source layout; wheel inclusion, lock digests and assembly
of an installable FHIR package are separate integration work.

## Constraints and preserved fields

All profiles require a logical `id`, `meta` and the exact profile declaration.
They prohibit `implicitRules`, contained resources and root modifier extensions;
a FHIRPath invariant also prohibits modifier extensions at nested depths.
Unsupported ordinary extensions require a runtime unsupported-content issue and
retention of the original export; absence of a prohibition in the differential
is not a declaration that every extension or referenced resource is supported.

| Profile | Added constraints | Native information retained |
| --- | --- | --- |
| Patient | Common identity/interpretation constraints | Name, optional birth-date precision, source identifiers and other native demographics; no required DOB or government ID |
| Observation | Explicit Patient subject and literal reference; specimen targets Specimen; hasMember targets Observation; derivedFrom targets Observation/DocumentReference; value choices exclude SampledData; component value/absence exclusion | Quantity/comparator, CodeableConcept/string, boolean/integer, Range/Ratio, time/dateTime/Period, components, panel children, method, ranges and applicability, interpretation, notes and effective times |
| DiagnosticReport | Explicit Patient subject; literal result/specimen references target the corresponding local profiles | Inherited status/code, conclusions, report effective time, issuer, optional issued instant and original report content |
| Specimen | Explicit Patient subject; parent references target local Specimens | Source type, collection, processing, received time and optional source status |
| DocumentReference | Explicit Patient subject; each content attachment requires media type, title and URL; inline data excluded; URL prefix/suffix invariant | Document status/docStatus, authors, dates and other source metadata |
| Provenance | Literal targets and entity references restricted to the six profiles; at least one source entity; source resolves to DocumentReference; agent.who requires reference or identifier | Inherited recorded time and agent, activity, source/revision roles, generation/correction context |

FHIR statuses and required terminology bindings are inherited from upstream;
archive acceptance never substitutes for a clinical status. Specimen.status is
optional upstream and remains optional when not supplied. Do not force an
Observation value on a panel, a cancelled result or an honest unknown. Inherited
`obs-6` excludes value plus absent reason; inherited `obs-7` also remains in force.
No local terminology, LOINC, UCUM mappings or broad value-set bundle is added.
Source-issued coding can be retained without claiming terminology verification.
Text-only `code`, qualitative results, unstructured microbiology/pathology and
unknown explanations remain representable. Preserve native fields rather than
copying them into an alternate clinical model or silently dropping them.
Unsupported waveform/sequence/imaging content stays in retained sources with an
explicit unsupported-content issue; references outside the supported graph are
not a backdoor to additional structured resource support.

## Runtime integration contract (Task 2)

The runtime registry must resolve all six canonical IDs, their `|0.1.0` forms,
upstream base IDs and supported datatype/profile dependencies **locally**. Unknown
or missing IDs fail explicitly. Differential files are not JSON Schemas: load
and enforce their supported constraints explicitly, or use a qualified official
validator; do not pass a differential to jsonschema or infer conformance from
`meta.profile` alone. No generated snapshot is claimed here.

The baseline upstream schema uses **draft-06**, not 2020-12. The following checks
are obligations beyond that schema (some are expressible in FHIRPath but still
need execution):

- Enforce inherited cardinality, required primitive presence, primitive extension
  rules, value choice exclusivity, `obs-6`, `obs-7`, component absence exclusion,
  SimpleQuantity restrictions on range bounds, profile membership, targetProfile
  and all supported profile invariants. Upstream schema allows missing statuses,
  simultaneous choices and Quantity comparators in SimpleQuantity positions.
- Check UUID identities, supported types/fields, one FHIR baseline and exact
  version pins. Validate every subject directly against the selected person;
  children never inherit a report's patient. Patient.id equals personId.
  Provenance has no subject: every target and source must belong to that person.
- Resolve the entire graph from the candidate mapping and selected person's
  immutable inventory. Patient identity references are `Patient/<id>`;
  context-sensitive result/specimen/source links and Provenance targets use
  `Type/<id>/_history/<revisionId>` after preparation. A produced Patient revision
  in Provenance.target is revision-pinned too. Candidates may use new-resource
  `urn:uuid:<id>` references; preparation rewrites only known mappings, assigns
  archive revision metadata, and never fills in a missing subject. Reject remote,
  escaping, dangling, cross-person, wrong-type and cross-version references.
  A full-validator context Bundle needs the reversible revision-URN closure
  described in the design; do not validate isolated resources by fetching links.
- Require exact source-document revisions for Provenance.entity role=source;
  role=revision links replaced revisions on corrections. Resolve agent references
  within the supported graph or use an explicit local identifier; a label alone
  is not authenticated identity and must not impersonate a clinician.
- Validate attachment URLs as exactly `assets/sha256/<64 lowercase hex>/blob`
  against the person archive base, not the JSON directory. The profile's
  prefix/suffix FHIRPath check alone is deliberately insufficient for safety.
  Check confinement, retained bytes, inventory SHA-256, size and media type.
  `Attachment.hash`, if supplied, is base64 **SHA-1**, never SHA-256 hex.
- Use decimal-preserving decoding/serialization and numeric resource bounds;
  preserve trailing scale, source tokens and comparators without unit conversion.
  JSON Schema cannot prove decimal fidelity. Preserve partial dates; never infer
  a timezone. Missing-offset clock text needs an explicit issue and review of
  any reduced-precision representation. Enforce instant/dateTime semantics.
- Require evidence for source patient identity cues, code/label, status,
  value/absence, dates, units, ranges/applicability, specimen, method,
  interpretation, issuer and conclusions when present (including components and
  panel children). IDs, archive meta and other generated bookkeeping use generated
  evidence with a rule ID. Resolve pointers/quotes and locators to retained bytes;
  validate hashes, page/box bounds or extraction offsets. The clinical profile
  cannot establish source row correctness, source-person assignment or consent.
- Block unsupported modifiers/implicit rules, itemize unsupported ordinary
  extensions/content, enforce status/correction and duplicate rules, immutable
  history, safe paths and review of the exact prepared bytes. Report terminology
  and unexecuted FHIRPath/full-validator checks as `not-checked`, never passed.

These are integration requirements, not runtime code delivered in this task.

## Sources and qualification

Syntax and constraint choices were checked against retained official R4 sources
on 2026-11-14:

- [Profiling: cardinality, differential vs snapshot](https://hl7.org/fhir/R4/profiling.html), retained at `definitions/docs/r4/profiling.html`.
- [FHIR JSON primitives and decimals](https://hl7.org/fhir/R4/json.html), retained at `definitions/docs/r4/json.html`.
- [Validation coverage and limitations](https://hl7.org/fhir/R4/validation.html), retained at `definitions/docs/r4/validation.html`.
- [Observation definitions](https://hl7.org/fhir/R4/observation-definitions.html), [datatypes](https://hl7.org/fhir/R4/datatypes.html), [references](https://hl7.org/fhir/R4/references.html), [DocumentReference](https://hl7.org/fhir/R4/documentreference.html) and [Provenance](https://hl7.org/fhir/R4/provenance.html), each retained under `definitions/docs/r4/`.

`definitions/upstream-inventory.json` pins the unchanged official bytes. The
six `StructureDefinition-<Type>.json` files under
`definitions/hl7.fhir.r4.core/4.0.1/package/` supply genuine base snapshots and
inherited constraints. The retained subset is not the complete core package:
notably SimpleQuantity and broader target/terminology closure are not retained.
Task 10 must qualify complete pinned dependencies, snapshot generation,
FHIRPath evaluation (including resolve), official-validator profile/example
validation and offline execution. **Full official-validator qualification has
not been performed.** The package status `active` declares the proposed frozen
local contract; it is not validator certification or release approval.

Run only the focused artifact checks:

```sh
uv run --locked pytest tests/test_profiles.py -q
```

They use the actual upstream Draft6Validator, test concrete malformed resources,
check differential path/type/cardinality compatibility against real base
metadata, and expose schema blind spots. They do not implement a fake profile
validator or establish semantic FHIR conformance. Independent review, runtime
integration, lock/package integration and Task 10 remain release gates.
