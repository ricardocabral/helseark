# Save your first health record

Give Claude Code, Codex or another coding agent a lab PDF or personal note. Have
it organize the information in a private folder using Helseark's schema. You do
not need to learn FHIR or install Helseark to start.

You need a copy of this repository and an agent that can read and write local
files. Download the repository from [GitHub](https://github.com/ricardocabral/helseark)
using **Code → Download ZIP**, unzip it, and open that folder in your agent.
The prompts below use paths relative to that copy.

Use only files you authorize the agent and its provider to read. A cloud agent
receives the content you share, even when the files are on your computer.

## 1. Create your profile and folder

Paste this into your agent:

```text
Help me start a personal health folder with Helseark.

Read instructions.md and use the FHIR R4 schema at
definitions/fhir-r4-json-schema/fhir.schema.json.

Create ~/Documents/my-health outside this repository. If that path already
exists, stop and ask me for a new folder rather than changing existing files.
Create sources/, drafts/ and records/ inside it.

Ask me what name to use for my profile. Generate a stable local person ID,
clearly labeled as generated, and show me a minimal FHIR Patient with that ID
and the name I supply. After I confirm it, save it as profile.fhir.json.
Do not invent demographics or clinical facts. Do not read any health files yet.
```

Your folder should now contain:

```text
my-health/
  profile.fhir.json
  sources/
  drafts/
  records/
```

The profile identifies whose records these are. Keep that ID for future imports.
Use a separate folder and ID for each person. These folders do not enforce access
permissions; you control who and which tools can read them.

## 2. Add one source

Copy one lab report into `my-health/sources/lab-report.pdf`. Keep the original
unchanged.

Paste this prompt, replacing `lab-report.pdf` if you chose a different filename:

```text
Follow instructions.md and prompts/extract.md.
Use definitions/fhir-r4-json-schema/fhir.schema.json as the clinical schema.

My health folder is ~/Documents/my-health. Use profile.fhir.json and read only
sources/lab-report.pdf as the source. Confirm with me that its identity cues
establish it belongs to this profile; stop if identity remains unresolved or
conflicting. For a personal note, follow the user-attribution instructions.

Save the draft Bundle, field citations and review note in drafts/first-import/
as bundle.fhir.json, evidence.md and review.md. Do not overwrite existing files.
Use the confirmed Patient ID. Make source paths work from this folder and from
records/first-import/, where I may later copy the reviewed files.

Show me a readable summary to check against the source. State what could not be
read or extracted and whether a schema check actually ran. Wait for my review;
do not change my profile, source or accepted records.
```

You should get three draft files and a summary. If the agent cannot read the PDF
or a scanned page, have it stop and report that. Supply a readable text export or
transcription as a separate source, retaining the PDF and labeling the
transcription; do not let it fill gaps from guesses.

For a personal note, put the note in `sources/` and change the filename in the
prompt. If it has no identity details, tell the agent who wrote it and whom it
describes. Have it retain your confirmation separately in `sources/` with the
note's filename and profile ID, and cite both sources. Keep the original note
unchanged. Its contents remain user-reported statements, with their wording and
date uncertainty; do not turn them into confirmed diagnoses. Unsupported details
can remain in the source with an explanation in `review.md`.

## 3. Review and keep the record

Open the source beside the agent's summary and citations. Check that it is the
right person and that every fact matches, especially values, units, dates and
anything marked uncertain. Ask for corrections while the files are still drafts.
Every change needs another review. The [invented example](../examples/README.md)
shows what to check. If you ask for [schema validation](schemas.md#optional-structural-validation),
have the agent check your actual draft Bundle and each resource, reporting the
file paths and result. The published command checks only the supplied example.
Structural validation cannot prove that an extraction is correct.

If you approve, explicitly tell the agent to copy the exact reviewed files from
`drafts/first-import/` to a new `records/first-import/`, without overwriting
anything. Have it add a separate acceptance note with your name, the actual
review date, person ID, exact files/version approved and any remaining concerns.
Keep those files and the source unchanged. Helseark relies on you and
your agent to follow this process; it does not enforce acceptance or revisions.

You now have your first reviewed record with its source and citations. For the
next import, choose a new name instead of `first-import`. To ask a question about
your saved records or correct an accepted record, use the [task guide](how-to.md).

To practice without real data, use a separate folder for the invented Alex
Example and the person ID shown in the [example](../examples/README.md). Use its
`source.csv` in place of `lab-report.pdf` and explicitly confirm this is a
fictional exercise. Keep these practice records separate from your own profile.
