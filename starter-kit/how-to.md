# Extract, query and correct records

Use these tasks manually or with an agent. No Helseark runtime is required.
For practice, use the [first-record lesson](tutorial.md).

## Prepare the task

1. Read the [agent instructions](instructions.md). They define identity, evidence,
   precision and history rules for every task.
2. Select one person by stable local ID. Check the source's identity cues.
   Stop if identity is missing or conflicting.
3. Keep sources and accepted files unchanged, outside this repository.
   Use separate files for drafts and review notes.
4. Supply the instructions, chosen template and inputs below.
   Share only authorized files with an agent. Read [privacy boundaries](../docs/explanation/privacy-and-agent-boundaries.md) before sharing.

## Extract a source

1. Copy the [extraction template](templates/extract.md).
2. Supply the person's ID, identity cues, source files and [FHIR R4 schema](../definitions/fhir-r4-json-schema/fhir.schema.json).
3. Save the returned Bundle, field citations and unresolved questions as drafts.
   See the [complete example](examples/README.md) for the expected format.
4. [Review the draft](#review-a-draft). The [schema check](schemas.md#optional-structural-validation) is optional and cannot replace review.

## Retrieve a cited answer

1. Copy the [query template](templates/query.md).
2. Supply the person's ID, question, date range, record files/revisions and source citations.
   Mark draft records as unreviewed.
3. Check the answer against its cited records and sources.
   Check which files it searched and which facts remain unknown or conflicting.

A query must leave records unchanged. A failed read cannot support an absence claim.

## Propose a correction

1. Copy the [correction template](templates/correct.md).
2. Supply the person's ID, exact prior file/revision, field, reason and supporting evidence.
   Label user statements as user statements.
3. Save the corrected resource separately with its citations and field-level before/after list.
   Identify the prior version and affected references. Do not update related resources automatically.
4. [Review the new draft](#review-a-draft). Preserve the prior source, accepted record, evidence and review.

## Review a draft

Compare each fact and citation with its source. Check person assignment, value,
comparator, unit, status, date precision and uncertainty. Inspect raw JSON numbers:
`0.050` must retain its scale. Omit unsupported facts and record the gap.

In a separate note, record reviewer, date, person ID, exact files/revision,
decision and unresolved concerns. Keep the reviewed bytes. Accept only after
explicit human approval. Any changed draft needs fresh review.

For corrections, retain the previous accepted version and record which version
supersedes it. The kit does not enforce review, store revisions or select versions automatically.
