<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/brand/svg/helseark-horizontal-reverse.svg">
  <img src="docs/brand/svg/helseark-horizontal-color.svg" alt="Helseark logo" width="480" height="120">
</picture>

Helseark provides an agent skill and schemas for turning lab PDFs and personal
notes into health records you can keep, query and correct. Ask an agent you
choose to organize the files; review its work before accepting a record.
Your original documents, structured records and citations stay in files you control.

## Start with one document

Download this repository using **Code → Download ZIP**, unzip it, and open the
folder in Claude Code, Codex or another coding agent that can read and write
local files. No Helseark installation is required.

Paste this prompt:

```text
Use the Helseark skill at skills/helseark/SKILL.md to organize my lab report.
```

The [skill](skills/helseark/SKILL.md) asks for your document, person and private
folder, creates or reuses your profile, and saves a draft with source citations.
Compare it with the original before explicitly approving it. You can also ask the
skill to organize a personal note, query records or propose a correction.

The file path tells the agent where to read the skill; no skill installation or
automatic discovery is assumed. Keep the repository's schemas and supporting files
with it. You do not need to copy the workflow into each conversation.

For a guided walkthrough, follow [Save your first health record](docs/tutorial.md).
Use only documents you authorize the agent and its provider to read. A cloud
agent receives what you share. See [privacy boundaries](docs/explanation/privacy-and-agent-boundaries.md).

## Instructions and reference

- [Helseark skill](skills/helseark/SKILL.md) and its [shared agent instructions](instructions.md).
- [Task guide](docs/how-to.md) and [complete invented example](examples/README.md).
- [Schemas and validation](docs/schemas.md): clinical records use FHIR R4, an open health-data standard.
- [Evidence and human review](docs/explanation/evidence-and-review.md).

Helseark provides no medical advice. Schema validity cannot establish extraction
accuracy or clinical truth. Review and file protection remain your responsibility.
The [experimental CLI](docs/optional-cli.md) is optional; see [current scope](SCOPE.md).

[Help](SUPPORT.md) · [Contribute](CONTRIBUTING.md) · [Security](SECURITY.md) ·
[MIT License](LICENSE) · [Third-party terms](docs/maintainers/licensing.md)
