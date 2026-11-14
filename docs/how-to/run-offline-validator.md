# Run the optional offline official validator

Baseline archive checks work without Java. To request deeper validation, install
a separate Java 17 runtime and the exact official validator 7.0.5 JAR. Neither
is included in the wheel, and no runtime operation downloads either one.
A requested full check without configuration blocks with `VALIDATOR_UNAVAILABLE`
(CLI exit 6). Baseline success still requires human review.

## Prepare public software, separately from records

From a reviewed source checkout, on a network-enabled maintainer machine:

```sh
python scripts/acquire_validator.py /absolute/new/validator-7.0.5
```

This is explicit acquisition of public software, never health data. It obtains
the official release JAR and nine exact packages from their pinned primary
URLs. It bounds sizes and verifies every SHA-256 against
`definitions/validator-lock.json`; changed bytes fail. Package hashes other than
the release JAR were measured from official registry downloads; they are byte
pins, not independently signed registry attestations. Keep the generated notices
with the JAR. `definitions/validator-notices.json` records the inspected embedded
notice members; the shaded executable contains several third-party licenses,
not just the upstream project's Apache-2.0 license. See [NOTICE](../../NOTICE).
No licensed terminology distribution is installed. Java is separately acquired;
retain the vendor's legal materials. Qualification used Temurin 17.0.21+9.

Move this directory to the offline machine. `packages/` must contain exactly the
nine TGZs in the lock, with no extra files or links. An unrelated empty cache
cannot substitute for it. Each run verifies the archives, bounds their extraction
and seeds a new temporary home; global Java/package caches are not used.

Use the six profiles from the selected vault's pinned definitions, for example
`VAULT/definitions/profiles/r4/0.1.0`. Their exact hashes must match that vault's
lock. An old vault is never repinned automatically. Old reports with no
`officialRun` remain readable; creating an enriched report requires the current
validation contract. Preserve old archives and use their compatible reader when
that contract is absent.

## Configure and request a full check

Save this host-controlled configuration outside agent-writable output. Paths must
be absolute. `executablePath` means the official JAR, not a shell command.

```json
{
  "executablePath": "/absolute/validator-7.0.5/validator_cli.jar",
  "executableSha256": "9dfe9f305b0f9389eceade2a4a1c9a2740d7b0e614066fdf07a78b571c76d92f",
  "version": "7.0.5",
  "packageDirectory": "/absolute/validator-7.0.5/packages",
  "profileDirectory": "/absolute/vault/definitions/profiles/r4/0.1.0",
  "timeoutSeconds": 120,
  "requireTerminology": false,
  "javaPath": "/absolute/jre/bin/java"
}
```

```sh
helseark --vault /absolute/vault validate proposal /absolute/proposal \
  --person PERSON_UUID --official-config /absolute/validator.json --json
```

This writes the enriched `validation.json` before human review; obtain a new
review receipt afterward. It refuses an already accepted or reviewed proposal.
A baseline-only `validate proposal` remains read-only. The library equivalent is
`validate_with_official_tool(proposal, config, vault=vault)`; it returns a
`ValidationReport` without writing resources or a review receipt. Explicit vault
context is required to verify source/person scope and snapshot closure.

The adapter uses Task 8's shared `fhir_collection` boundary, including proposed
revisions, pinned historical children and versionless Patient references. Only
Reference strings in the derived Bundle change. Original resources and source
assets remain untouched. The report binds the original proposal SHA-256, derived
Bundle hash, reversible revision/fullUrl mapping, package/profile pins, Java
launcher hash, exact effective flags, outcome hash, elapsed time and issue counts.
Reports and review receipts remain noncircular: proposal → validation → review.
Elapsed timing is retained, not regenerated during review/commit.

## Network confinement and coverage

macOS uses `sandbox-exec` with `(deny network*)`. Linux uses `unshare --net`;
the host must permit creating that network namespace (the CI drill runs under
sudo). No fallback to an unconfined subprocess exists. Unsupported confinement,
missing Java/packages, changed hashes, timeout, launch failure and malformed or
inconsistent OperationOutcome all block. An arbitrary remote resource reference
is rejected by baseline/closure checks before execution. Java receives neither
source assets nor remote fetch authority.

The exact CLI uses `-version 4.0.1`, local `-ig`, `-tx n/a`, isolated `-txCache`,
`-no-http-access`, and `-disable-default-resource-fetcher`. Those flags alone are
not the network guarantee: OS policy prevents package auto-download too. The tool
may attempt latest-package metadata requests that are denied and then fall back
to the exact local cache. Do not describe this as zero attempted requests.

`full-fhir` reports passed/failed with resource/error/warning counts for the
pinned R4 definitions, six supported profiles and their executable invariants.
Terminology always reports `not-checked`: local packages and `-tx n/a` do not
establish licensed or complete terminology validation. `requireTerminology: true`
therefore fails coverage with `TERMINOLOGY_UNAVAILABLE`, blocking acceptance.
Neither result establishes clinical correctness, extraction accuracy or general
FHIR conformance outside the tested surface. Review original sources and every
warning before accepting.

A preflight minimal Patient passed with 0 errors / 1 narrative warning. A Patient
contact containing only gender passed upstream JSON Schema but failed actual
FHIRPath `pat-1` with 1 error / 1 warning. Its first 55-second run timed out;
the explicitly configured 120-second retry finished. Preserve that failure:
startup load varies, and a deadline change must be visible in configuration.
See the real synthetic corpus qualification in CI for the supported profile
surface. Process-error fakes make no conformance claim.

Sources: [official R4 validation scope and limits](https://hl7.org/fhir/R4/validation.html),
[qualified validator release](https://github.com/hapifhir/org.hl7.fhir.core/releases/tag/7.0.5),
[pinned loader source](https://github.com/hapifhir/org.hl7.fhir.core/blob/7.0.5/org.hl7.fhir.validation/src/main/java/org/hl7/fhir/validation/service/ValidationService.java).
