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
URLs. The R4 core archive comes from the [published R4 download](https://hl7.org/fhir/R4/hl7.fhir.r4.core.tgz)
that supplied its exact byte and digest pin; the other eight packages come from
the official package registry. It bounds sizes and verifies every SHA-256 against
`definitions/validator-lock.json`; changed bytes fail. Package hashes were measured
from those official downloads; they are byte pins, not independently signed
package attestations. Keep the generated notices
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
assets remain untouched. New Patient genesis records declare the supported
Patient profile. Older accepted Patients that lack that declaration are never
rewritten by this adapter and can fail target-profile conformance; keep the
failed report and use a separately reviewed revision/migration workflow. The report binds the original proposal SHA-256, derived
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
A later full API qualification also exhausted 120 seconds under machine load;
its explicitly configured retry and CI use 240 seconds. The example above stays
at 120 seconds so operators choose and record the bound rather than receiving a
silent default increase. Machine issue locations are mapped to original revision
references and JSON Pointers where the official path syntax is unambiguous.
See the real synthetic corpus qualification in CI for the supported profile
surface. Process-error fakes make no conformance claim.

Sources: [official R4 validation scope and limits](https://hl7.org/fhir/R4/validation.html),
[qualified validator release](https://github.com/hapifhir/org.hl7.fhir.core/releases/tag/7.0.5),
[pinned loader source](https://github.com/hapifhir/org.hl7.fhir.core/blob/7.0.5/org.hl7.fhir.validation/src/main/java/org/hl7/fhir/validation/service/ValidationService.java).

## Execution authority and compatibility

The corrected reader records a fresh host execution request outside editable
proposals as soon as the explicit request identifies its original pending
proposal. This happens before configuration loading, baseline checks or runtime
checks. Missing configuration (`VALIDATOR_UNAVAILABLE`) and an invalid configuration
retain their typed errors and invalidate the prior result. A generation with no
resolved configuration is a failed request, never acceptance authority. The API,
adapter and CLI follow this same rule. Only the exact authorized pending path can
revoke its result; copied paths, other people/proposals and accepted history cannot. Only an actual completed validator run can retain
the original complete report, outcome, coverage and runtime/policy binding.
A report digest supplied inside the report is never execution authority.

Host workflow state is under `.runtime/prepared` and `.runtime/official-validation`.
These directories belong to the approved host, outside agent-writable candidate
and proposal output. The enforced threat boundary permits edits to proposals and
reports, not these host controls. File mode alone is not a hostile-host sandbox;
someone able to rewrite all host controls and the whole archive remains outside
this integrity guarantee. No signature or verified human identity is asserted.

Human review retains `officialValidationAuthority` in its digest-bound receipt;
accepted history then needs neither work controls nor installed Java to verify
that original binding. Missing or changed pending authority, scope, report,
command, environment, complete JRE (including macOS bundle files), packages,
profiles or required policy blocks review/commit. Every nonofficial baseline
family, result, reason and multiplicity must still match fresh validation.
Only `full-fhir` and `terminology` can be substituted by the authenticated result.
Extraction accuracy and clinical correctness remain unverified.

New pending preparations record their original baseline report and authority
version. Older ambiguous pending controls are rejected; prepare and explicitly
review again. Older pinned schemas that cannot retain execution authority block
new official runs, without automatic repinning. Existing accepted reports retain
their exact original bytes and pins. When they lack original execution authority,
readonly review labels their coverage `not-checked`/unattested, preserving stored
results and limitations in the explanation. It never invents a retrospective
execution attestation. Use the corrected reader for this guarantee.

The JAR gets a private temporary pathname so adjacent manifest Class-Path files
cannot be loaded. On the same filesystem this uses a hardlink to the verified
immutable JAR, otherwise an exclusive byte copy. Original input byte inventories
are checked before/after execution; reference tools are not rewritten. Runtime
and terminology byte pins and acquisition URLs are unchanged by this correction.


## Combined release and CI qualification

New vaults use agent kit 0.1.12. The original 0.1.0 review/validation schemas
remain unchanged; enriched reports use the separately pinned 0.1.1 validation
schema, and exact-issue 0.1.1 human receipts retain the execution authority. Old
vaults keep their own definitions and kit. No automatic repinning is performed.

The Linux offline-validator job runs both the actual supported corpus and
`tests/qualify_validator_authority.py` against an installed wheel. The latter
verifies a reachable network control, actual positive and schema-valid deeper
negative, unavailable required terminology, four early-request revocations,
missing Java, actual successful recovery, public replay rejection and preserved
history. Its legacy input comes from the immutable synthetic fixture via
`tests/setup_validator_legacy.py`; no execution attestation is added to old bytes.
The three disjoint agent/clinical/core groups run all pytest cases separately;
the base-only jobs retain optional dependency checks. Only a completed CI run
on the integrated commit establishes Linux results.
