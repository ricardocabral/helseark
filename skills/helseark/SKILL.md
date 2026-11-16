---
name: helseark
description: Use when organizing personal health documents with Helseark, creating a person profile, importing a lab PDF or personal note, querying saved records, or proposing a correction.
---

# Helseark

Organize one person's health records in plain files using FHIR R4. This skill
uses the repository's instructions and schemas; it requires no Helseark CLI.

Resolve links relative to this file, not the current working directory. Keep
the repository with the skill. If a referenced file is missing, report it;
do not silently install tools, fetch definitions or substitute the experimental
agent-kit. The [bundled vocabulary](../../vocabulary/README.md) works offline
without an account. Optional full-catalog acquisition is a separate explicit
operation described in the [terminology guide](../../docs/terminology.md).

Read [agent instructions](../../instructions.md) for every task. Use the pinned
[FHIR R4 schema](../../definitions/fhir-r4-json-schema/fhir.schema.json).
Read only the task reference needed below. The [invented example](../../examples/README.md)
illustrates the output, not a source of facts for a real person's record.

## Select the person and task

Ask only for missing inputs: the task, one person, selected source/record files,
and a private health folder outside this repository. Explain before reading
health data that a cloud agent receives what the user shares. Read no other
person's files. Honor confirmations already supplied for this task.

For a requested new profile or first import, create `sources/`, `drafts/` and
`records/` in a new folder without overwriting anything. Prepare a minimal FHIR
Patient with the user's supplied name and stable local ID, or a generated ID
clearly labeled as generated. Show the profile
and obtain confirmation before saving `profile.fhir.json`. Invent no demographics.
For an existing folder, use only the selected confirmed profile and retain its ID;
stop on a missing, ambiguous or conflicting profile rather than replacing it.
Queries and corrections require an existing confirmed profile; a query creates
or changes no files.

## Import a document

Follow the [extraction instructions](../../prompts/extract.md).
Confirm source identity separately from profile creation; use the retained
user-attribution procedure for personal notes without identifiers. An attribution
cannot override conflicting identity evidence.

Retain the authorized source unchanged in `sources/`, with no filename collision.
Create a fresh `drafts/<import-name>/` with `bundle.fhir.json`, `evidence.md` and
`review.md`. Reuse the confirmed Patient ID. Source attachment paths must resolve
from the draft folder and remain valid after copying to `records/<import-name>/`.
Never overwrite an earlier import or mutate the profile to match a document.

Show a readable summary and field citations. Itemize unreadable pages, unsupported
facts, normalizations and unresolved questions. Stop on unreadable input instead
of guessing; request a separately retained readable export or labeled transcription.
Record whether the actual draft Bundle and each resource were schema-checked,
with input paths and result, or why checks could not run. The command in
[schema references](../../docs/schemas.md) checks only the invented example.

## Propose terminology mappings

Use the [terminology guide](../../docs/terminology.md) and
[local helper](scripts/terminology.py). Without `--package`, search/check use the
shipped pinned LOINC subset, English/PT-BR Janusmed aliases and UCUM definitions.
Search labels automatically across these terms and useful language variants;
do not ask the user to identify the language first. Retain the original spelling.
Search language cannot establish specimen, clinical equivalence or numeric/date
locale. At setup or when broader coverage would help, offer once: use the bundled
vocabulary, import an existing official ZIP, or download full LOINC after account
creation. Honor a supplied preference and retain it in private setup/review notes;
declining is supported and must not trigger repeated prompts for unmatched labels.
For a download, follow the separate local-terminal credential procedure; never
request passwords in chat. Do not fetch during extraction. If definitions are
unavailable or context is insufficient, continue with source text and record gaps.

You may propose a new mapping in the draft. Cite the source support for every
relevant LOINC axis and UCUM assignment. Abstain when context is missing,
conflicting or ambiguous, even if search returns one candidate. Keep source codes
distinct from proposed codes in the evidence. Preserve source `code.text`, unit,
value, comparator and date; add supported native FHIR coding only. Retain the
proposal, catalog pins, alternatives and helper check result beside the draft.
The check verifies membership and declared context, not clinical equivalence.
Reuse a reviewed mapping only within its explicit approved conditions, with
citations for this source and review of the new draft. No accepted file changes.
An alias match is discovery only. You may propose new aliases or conditional
mappings beside the private draft; adding them to the shared vocabulary requires
separate review, provenance and redistribution rights. Never invent approval
metadata or silently promote a patient's draft into repository terminology.

## Query or correct records

- **Query:** follow [query instructions](../../prompts/query.md). Ask for the
  question, date range if relevant, selected record versions and citations.
  Identify draft records as unreviewed. Answer with citations and read coverage;
  leave all files unchanged.
- **Correct:** follow [correction instructions](../../prompts/correct.md). Require
  the exact prior version, target field, reason and evidence. Save a separate
  draft with before/after details in a fresh correction folder. Preserve the
  prior record, evidence and decision; do not update related records automatically.

## Human review

Leave imports and corrections as drafts until explicit human approval of the
exact final files, including any mapping proposal and its evidence. Validation,
a source's `final` status and an agent's summary are not approval. Every changed draft needs fresh review.

Only after that approval, copy the reviewed files unchanged to a fresh directory
under `records/`. Keep source paths valid. Record the actual reviewer, date,
person ID, exact approved files/version and remaining concerns in a separate
acceptance note; never invent a decision or reviewer. For a correction identify
the superseded version and retain it. See the [review checklist](../../docs/how-to.md#review-a-draft).

The user controls file protection and review; these instructions do not enforce
access control or revisions. Provide no diagnosis or treatment advice.
