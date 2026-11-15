<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/brand/svg/helseark-horizontal-reverse.svg">
  <img src="docs/brand/svg/helseark-horizontal-color.svg" alt="Helseark logo" width="480" height="120">
</picture>

Helseark provides instructions and schemas for turning lab PDFs and personal
notes into health records you can keep, query and correct. Ask an agent you
choose to organize the files; review its work before accepting a record.
Your original documents, structured records and citations stay in files you control.

## Start with one document

Download this repository using **Code → Download ZIP**, unzip it, and open the
folder in Claude Code, Codex or another coding agent that can read and write
local files. No Helseark installation is required.

Paste this prompt:

```text
Help me organize a health document using Helseark.
Read instructions.md and prompts/extract.md. Use the FHIR R4 schema at
definitions/fhir-r4-json-schema/fhir.schema.json.

Ask me which person the record is for, which PDF or note to read, and where
outside this repository to create a private health folder. If that folder
already exists, stop and ask me where to continue.

Create sources/, drafts/ and records/. Show me a minimal FHIR Patient profile
with the name I supply and a generated stable local ID. After I confirm it,
save profile.fhir.json. Confirm the selected source belongs to this person;
follow the personal-note attribution rules when needed.

Retain an unchanged copy of the selected source in sources/. Save the draft
Bundle, field citations and review note as bundle.fhir.json, evidence.md and
review.md in a new drafts/first-import/ folder. Keep source references valid
if I later copy the reviewed import to records/first-import/.

Show me a readable summary with source citations and anything uncertain or
unreadable. Report whether the actual draft was schema-checked. Wait for my
explicit review before accepting anything; never overwrite existing files.
```

Compare the draft with its source. Check the person, values, units, dates and
citations. If you approve, tell the agent to retain the exact reviewed files in
`records/first-import/` with a separate note recording your name, review date,
person ID and exact files/version approved. Preserve sources and accepted files;
corrections create a new version.

For a guided walkthrough, follow [Save your first health record](docs/tutorial.md).
Use only documents you authorize the agent and its provider to read. A cloud
agent receives what you share. See [privacy boundaries](docs/explanation/privacy-and-agent-boundaries.md).

## Instructions and reference

- [Agent instructions](instructions.md).
- Task prompts: [extract](prompts/extract.md), [query](prompts/query.md), [correct](prompts/correct.md).
- [Task guide](docs/how-to.md) and [complete invented example](examples/README.md).
- [Schemas and validation](docs/schemas.md): clinical records use FHIR R4, an open health-data standard.
- [Evidence and human review](docs/explanation/evidence-and-review.md).

Helseark provides no medical advice. Schema validity cannot establish extraction
accuracy or clinical truth. Review and file protection remain your responsibility.
The [experimental CLI](docs/optional-cli.md) is optional; see [current scope](SCOPE.md).

[Help](SUPPORT.md) · [Contribute](CONTRIBUTING.md) · [Security](SECURITY.md) ·
[MIT License](LICENSE) · [Third-party terms](docs/maintainers/licensing.md)
