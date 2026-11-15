# Save your first health record

Use the Helseark skill to turn one lab PDF or personal note into a record you can
keep. You need a copy of this repository and an agent that can read and write
local files, such as Claude Code or Codex. No Helseark installation is required.

## 1. Ask the agent to use Helseark

Download the repository from [GitHub](https://github.com/ricardocabral/helseark)
using **Code → Download ZIP**, unzip it, and open that folder in your agent.
Paste:

```text
Use the Helseark skill at skills/helseark/SKILL.md to organize my lab report.
```

For a personal note, say “my personal note” instead. The file path lets the agent
read the skill directly; you do not need to install it or copy its instructions.
A cloud agent receives the content you share, even when your files are local.

## 2. Supply your document and confirm your profile

Give the agent the selected file, whose record it is, and a private folder outside
this repository, such as `~/Documents/my-health`. It will show you a proposed
profile with your supplied name and a stable person ID. Confirm it before saving.
For an existing folder, select your confirmed profile so the same ID is reused.

Your folder will contain:

```text
my-health/
  profile.fhir.json
  sources/
  drafts/
  records/
```

Confirm that the document belongs to that person. For a personal note without
identity details, the agent asks who wrote it and whom it describes, then retains
your attribution separately. Keep the original note unchanged.

The agent retains your source in `sources/` and saves three files in a fresh
`drafts/<import-name>/`: `bundle.fhir.json`, `evidence.md` and `review.md`.
It shows a readable summary, source citations and unresolved questions. If it
cannot read a PDF, supply a separate readable export or labeled transcription;
do not let it guess the contents.

## 3. Review and keep the record

Compare the draft with the source. Check the person, values, units, dates and
citations. Ask for corrections while it is still a draft; review again after
any change. If validation is requested, check that the agent reports your actual
draft's paths and results, rather than the supplied example's check.

If you approve the exact final files, explicitly tell the agent. It will retain
those files unchanged in a new `records/<import-name>/` with a separate acceptance
note recording your name, review date, person ID, exact files/version approved
and any remaining concerns. Sources and earlier accepted files stay unchanged.
These instructions rely on you and your agent to follow review and versioning.

For another import, ask the same skill to read the next selected document using
your existing profile. To ask a question or propose a correction, use the same
skill; see the [task guide](how-to.md) for the inputs.

For practice, use a separate folder for Alex Example and the explicit person ID
from the [invented example](../examples/README.md), with its `source.csv` as your
selected source. Confirm that this is a fictional exercise and keep it separate
from your real profile.
