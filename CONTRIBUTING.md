# Contributing to Helseark

Read [AGENTS.md](AGENTS.md), the [documentation](docs/index.md) and the versioned
contracts before changing archive behavior. Use an isolated branch/worktree and
preserve concurrent work. Keep clinical payloads in native FHIR R4 resources,
exact decimal tokens, explicit patient scope and immutable accepted history.
Every clinical import/correction requires explicit human review of final bytes.

Run focused behavioral tests locally; CI owns the full macOS/Linux matrix.
Add failure/recovery and patient-isolation cases for changes to write boundaries.
Never commit a real health record or internal task reports. All clinical fixtures
must be invented and declared in `tests/fixture-manifest.json`, with SHA-256,
size, provenance and license. Run `python3 scripts/check_fixture_manifest.py`.
Keep per-case expected facts and check coverage separate from supplied candidate
construction. Predetermined candidates do not establish model extraction accuracy.

Toolkit code/documentation is Apache-2.0; original invented fixture data is CC0-1.0.
Preserve upstream notices, namespaces and old released pins. Do not imply HL7
endorsement. New behavior must update its public docs and agent task routes.
Independent review and integrated remote CI are required before integration;
only the authorized coordinator merges or pushes main.
