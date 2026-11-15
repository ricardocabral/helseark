# Personal health data starter kit

Organize one person's records with instructions, three prompts and FHIR R4 schemas.
Use a text editor or an agent. No installation is required. This kit provides no medical advice.

## Choose what you need

| Need | Start here |
| --- | --- |
| Learn the workflow | [Read your first cited record](tutorial.md): follow a fictional source, draft and cited answer without running anything |
| Complete a task | [Extract, query and correct records](how-to.md): prepare inputs, use a template and review the result |
| Look up rules and formats | [Agent instructions](instructions.md), [schemas and validation limits](schemas.md), and [annotated example](examples/README.md) |
| Understand the decisions | [Evidence, precision and human review](explanation.md) |

## Copy a task prompt

- [Extract records](templates/extract.md) — propose a FHIR Bundle with source citations.
- [Query records](templates/query.md) — retrieve a cited answer from supplied records.
- [Propose a correction](templates/correct.md) — draft a separate version with before/after evidence.

Supply [the instructions](instructions.md) with each template. The [task guide](how-to.md)
lists inputs and review steps. Keep real records outside this repository.
Read [privacy boundaries](../docs/explanation/privacy-and-agent-boundaries.md) before sharing them.

## Files to keep or copy

For a portable copy, keep these paths with their relative layout:

- `starter-kit/` — all instructions, templates, and the complete example.
- `definitions/fhir-r4-json-schema/fhir.schema.json` — the single upstream schema.
- `schemas/0.1.0/evidence.schema.json` — optional machine-readable citation schema.
- `LICENSE`, `definitions/README.md`, `definitions/docs/r4/license.html`, and
  `definitions/docs/r4/cc0-1.0.html` — terms and upstream attribution.

Some links open optional repository context. To read that context offline, also keep `profiles/r4/0.1.0/`,
`docs/reference/clinical-model.md`, `docs/explanation/privacy-and-agent-boundaries.md`,
`SECURITY.md`, and `SCOPE.md`. Further links may require the full checkout.
The CLI, `agent-kit/` and Python dependencies are unnecessary for manual use.

The evidence example includes a source digest. You can use readable citations instead.
FHIR remains the clinical format. See [schema references](schemas.md) for the optional
structural check and [current scope](../SCOPE.md) for delivery limits.
