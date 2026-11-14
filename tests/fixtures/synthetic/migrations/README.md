# Test-only migration layout

`legacy-test-only.json` is NOT a supported public release or a clinical schema.
Tests place a verified Task8 backup at `snapshot/` beside this exact marker.
The only layout transformation removes `snapshot/vault/` from retained file paths.
FHIR, envelopes, IDs, evidence pointers, definitions and hashes are unchanged.
The CLI requires `--test-only-legacy`; ordinary open rejects this container.
No invented production contract 0.2.0 or legacy clinical meaning is introduced.
