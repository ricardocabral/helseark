# Why evidence and human review stay with the record

FHIR R4 4.0.1 holds the clinical facts. Sources, citations and review notes support
those facts. A second simplified clinical format could drift from the FHIR record.

## Precision preserves meaning

The [invented source](examples/source.csv) says `<0,050 mg/L`.
Its draft retains `0.050`, comparator `<` and unit `mg/L`.
Removing the comparator would turn a bound into a point measurement.
Adding a day to `2026-02` would invent precision. Citations make these choices inspectable.

A stable person ID and source identity cues make the subject assignment inspectable too.
A matching name or valid reference cannot establish identity.

## Structure cannot establish truth

A schema can check structure. It cannot prove source authenticity, correct identity,
accurate extraction or human approval. The lab's `final` status describes the source
result, not the review decision.

Review applies to exact draft files and their evidence. Changes need fresh review.
Corrections add a version and preserve the earlier record and decision.
A cited answer covers only the supplied records it successfully read.
Missing records cannot prove that a condition is absent.

## Plain files require user control

You control file protection, review and version organization. Prompts cannot enforce
these rules or restrict an agent's tools. Sharing files with a cloud agent discloses
them to that provider. See [privacy boundaries](../docs/explanation/privacy-and-agent-boundaries.md).

The [experimental CLI](../docs/optional-cli.md) adds a separate archive workflow.
Its contracts are optional. The portable example uses base FHIR R4 and is not a CLI candidate.
Use the [task guide](how-to.md) for actions and [schema references](schemas.md) for formats.
