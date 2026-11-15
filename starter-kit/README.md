# Personal health data starter kit

Use plain instructions, three copyable prompts, and existing FHIR R4 schemas to
organize one person's records. Read and use this kit in a text editor; no CLI,
installation, generated vault, prompt renderer, or protocol setup is required.
This is record organization, not medical advice.

## Quickstart

1. Read the [agent instructions](instructions.md). Choose one person explicitly
   and keep their source files outside this public repository. Use only invented
   data in contributions. Share private data with an external agent only after
   deciding what that provider may receive; local files are not encryption.
2. Try the [complete invented example](examples/README.md): open its source CSV,
   FHIR JSON, and evidence side by side. All files are supplied, with no generation
   step. The example is a draft, not a reviewed real record.
3. Copy the [extraction prompt](templates/extract.md) into your chosen agent or
   use it as a manual checklist. Supply the person and source files as requested
   in its opening sentence. It produces FHIR JSON plus readable field citations.
4. Compare every proposed fact and citation against the source. Record your name,
   review date, exact files/revision reviewed, decision, and unresolved concerns in
   a separate review note. Accept only after explicit human approval; keep the
   source and earlier accepted files unchanged. A changed draft needs fresh review.
5. Use the [query prompt](templates/query.md) for cited retrieval, or the
   [correction prompt](templates/correct.md) to propose a separate corrected copy.
   Neither prompt authorizes edits to accepted history.

## Files to keep or copy

Keeping the repository checkout is simplest. For a smaller portable copy, retain
these paths with their relative layout (no entire dependency tree is needed):

- `starter-kit/` — all instructions, templates, and the complete example.
- `definitions/fhir-r4-json-schema/fhir.schema.json` — the single upstream schema.
- `schemas/0.1.0/evidence.schema.json` — optional machine-readable citation schema.
- `LICENSE`, `definitions/README.md`, `definitions/docs/r4/license.html`, and
  `definitions/docs/r4/cc0-1.0.html` — terms and upstream attribution.

The schema reference links also point to optional repository context. To follow
those offline in a reduced copy, additionally retain `profiles/r4/0.1.0/`,
`docs/reference/clinical-model.md`, `docs/explanation/privacy-and-agent-boundaries.md`,
`SECURITY.md`, and `SCOPE.md`. Their further links may require the full checkout.
The full core archive, CLI, `agent-kit/`, and Python dependencies are unnecessary
for reading or manually using the prompts. See [schema references](schemas.md)
for the optional structural check and its limits.

The evidence JSON example reuses an existing envelope with a precomputed source
digest. Ordinary use can keep readable citations instead; no hash calculation,
pin management, or archive protocol is a prerequisite. FHIR remains the clinical
representation in either case. See the repository [scope](../SCOPE.md).
