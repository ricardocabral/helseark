# Correct a record

Select the person and current `Observation/UUID` or `DiagnosticReport/UUID` explicitly.
Never edit accepted files. Start a draft:

```sh
helseark --vault family correct --person PERSON --resource Observation/ID \
  --reason 'transcription: checked the original decimal' --json
```

The returned `path` contains editable bundle/evidence files pinned to the current
head. Update the fact and its evidence, preserving the original source wording.
Prepare, inspect, supply an explicit human decision, and commit through
[the reviewed publication workflow](../reference/review.md). Changes after review
invalidate it. Local correction emits native FHIR Provenance with exact replaced
revision references. A transcription fix leaves the source's clinical status
unchanged. Use `entered-in-error: explanation` and explicitly set the selected
record's status to `entered-in-error` to retract an erroneous assertion;
`cancellation: explanation` requires `cancelled`. These statuses are excluded
from default observation trends; historical revisions remain readable.

For a laboratory-issued amendment, retain the **new** report through intake,
author its untrusted candidate with `amended`/`corrected` source status and new
source evidence, and explicitly identify the corresponding old logical record:

```sh
helseark --vault family candidate prepare NEW_CANDIDATE --person PERSON \
  --source NEW_SOURCE_SHA256 --amendment-target Observation/ID \
  --amendment-reason 'Human matched this laboratory amendment to the old result' --json
```

This narrow mapping requires exactly one candidate resource of the target type.
Other new resources retain distinct IDs. Broader report/result reconciliation
requires separately reviewed drafts; no automatic patient or fact matching occurs.
A local transcription draft cannot invent lab amendment status. Cancellation of
a report does not cancel its children. Review every result's disposition explicitly.
A report pinned to an older child revision stays pinned; current queries warn
`REPORT_RESULT_REVISION_MISMATCH`. Revise a parent explicitly when appropriate.

Validation/evidence coverage is not proof of medical or extraction correctness.
