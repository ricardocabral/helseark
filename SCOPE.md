# Current scope

The core deliverable is [Helseark](README.md): an agent skill, shared instructions,
extraction/query/correction task references,
existing FHIR R4/schema references, and a complete invented source with a cited
FHIR example. Use requires no CLI installation or generated vault. Preserve exact
precision, explicit person identity, source evidence and mandatory human review.
Schema validity does not establish clinical truth. No medical advice is provided.

| Area | Status |
| --- | --- |
| Agent skill, instructions, three task references, schemas and invented example | Core |
| Existing Python library/CLI and legacy agent-kit | Preserved, optional experimental work; separate setup and limitations |
| Confinement infrastructure and sandbox launchers | Deferred |
| Bespoke evaluation platform and provider evaluations | Deferred |
| 32-trial qualification gate | Deferred; not a prerequisite for using the instructions and schemas |
| Official Java validator integration/qualification | Deferred |
| Migration implementation or expansion | Deferred |
| Adapter and OCR expansion | Deferred |
| Reports and transactional engine expansion | Deferred |

Default CI checks the agent instructions’ documented schema command and the
invented example’s identity, precision and citations. The experimental CLI suite
is available only through the manual “Experimental CLI (manual)” workflow;
schema and example checks do not qualify the optional runtime or its distributions.

Existing files, branches and historical evidence remain intact. Prior application
roadmaps are historical context, not acceptance criteria for this delivery. Future
work on deferred areas requires explicit scope authorization. This cut makes no
claim of broad final qualification, clinical correctness or release readiness.
