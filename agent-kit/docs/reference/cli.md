# CLI reference

Applies to toolkit 0.1.2 / kit 0.1.17; see [compatibility](compatibility.md).
`helseark` and `python -m helseark.cli` call the same implementation. No command
launches a model. Put global `--vault PATH` before the command. Its only default is
`HELSEARK_VAULT`; there is no parent-directory search. Clinical commands require
`--person UUID`. Use absolute paths for host/agent handoffs.

## Commands

In this table `V` is an explicit vault, `P` a person UUID, and destination paths
must be absent. `--json` is available on every leaf command. Repeat options marked
“repeat” rather than passing comma-separated strings.

| Command after `helseark` | Inputs, defaults and result |
|---|---|
| `init NEW_PATH` | New format-1 vault, UUID and pinned definitions/kit; returns path/vaultId |
| `--vault V person add --name TEXT` | Optional `--birth-date YYYY[-MM[-DD]]`, `--note TEXT`; self-reported Patient; returns personId |
| `--vault V intake add SOURCE --person P --packet NEW_PATH` | Optional `--agent-output NEW_ABSOLUTE_PATH`, `--confirm-person`; retains source and builds packet; returns path, source, extraction, issues and host trustedContextSha256; no clinical acceptance |
| `--vault V schema export --resource TYPE --out NEW_PATH` | Repeat resource; copies local contracts/definitions. Without vault/env uses installed definitions through a temporary vault |
| `--vault V validate candidate DIRECTORY --person P` | Reads untrusted candidate and returns coverage/issues; never publishes |
| `--vault V validate proposal DIRECTORY --person P` | Validates exact prepared proposal; returns checkedProposalSha256/coverage/issues |
| `--vault V candidate prepare DIRECTORY --person P` | Returns prepared path, proposalSha256, validation and disposition; optional repeat `--source HASH` is explicit host source authority; `--reextract` and `--reconciliation JSON_PATH` are explicit user inputs for existing-source correspondence |
| `--vault V candidate review PROPOSAL --person P` | Without `--decision` inspects only; with user-controlled `--decision JSON_PATH` records exact receipt. See [review](review.md) |
| `--vault V candidate commit PROPOSAL --person P` | Requires bound receipt/host continuity; returns committed/already-accepted disposition, Head and logicalResources |
| `--vault V observations --person P` | Native accepted Observation rows, defaults current and excludes cancelled/entered-in-error. Optional `--label` exact source text, `--code-system`, `--code`, `--from-date`, `--to-date`, `--include-invalidated`, `--at-head HEAD_JSON_PATH` |
| `--vault V timeline --person P` | Current accepted resource timeline; optional `--at-head HEAD_JSON_PATH`; unknown-time bucket retained |
| `--vault V record --person P --resource REF` | Native FHIR resource; optional `--at-head HEAD_JSON_PATH` |
| `--vault V doctor` | Read-only integrity report: checkedChanges/Resources/Assets, issues, orphanPaths; never repairs/deletes |
| `--vault V backup create --out NEW_PATH` | Complete folder snapshot, optional `--include-work`; excludes derived/runtime; returns ExportReceipt |
| `backup verify BUNDLE_DIRECTORY` | No vault needed; verifies inventory and closure; returns IntegrityReport |
| `backup restore BUNDLE_DIRECTORY --into NEW_PATH` | No vault needed; verifies/stages/publishes fresh vault; returns path/vaultId; no ZIP/tar input |
| `--vault V export --person P --out NEW_PATH` | Default `--mode full-person`; alternative `selected-current`; repeat `--resource REF`; `--no-sources` only for selected snapshots. PDFs block ordinary source-inclusive person export with SOURCE_SCOPE_REVIEW_REQUIRED |
| `agent tasks` | Installed task descriptors without person reads; with vault/env uses its pinned kit |
| `--vault V agent context --task TASK --person P --out NEW_PATH` | Repeat `--source HASH`, `--resource REF`; optional from/to dates, `--continuation PRIOR_CONTEXT_JSON`; defaults max-records 100, max-data-bytes 262144; returns exact packet and host trustedContextSha256 |
| `--vault V agent render --context CONTEXT_JSON --person P --prompt ID --variables JSON_PATH --trusted-context-sha256 HOST_DIGEST` | Verifies original host authority and typed slots, returns text/provenance/readable paths; executes no agent |

`REF` is `Type/UUID` or `Type/UUID/_history/UUID`. `HEAD_JSON_PATH` is a path
to a JSON file containing the exact object with sequence (positive integer),
transactionId and changeSha256; pass the file path, not a literal JSON object.
It selects an existing person snapshot; it is not a date. Query rows include resourceRef, effective,
timePrecision, timeFilterRelation, code, value/valueType, unit/comparator, referenceRanges, method,
status, sourceRefs and issues. Use Decimal-preserving JSON for numeric scale.
No trend aggregation, conversion or inferred diagnosis is performed. See
[query semantics](../how-to/query-history.md).

Source intake caps source bytes at 100 MiB. Optional PDF extraction uses pinned
pypdf, with page/text limits documented in [PDF extraction](pdf-extraction.md).
Context instructions have a 32 KiB cap; data limits count selected payload bytes,
not all process I/O or rendered metadata. Over-budget whole values fail rather
than truncate. Import packets do not disclose all historical records. A declared
prompt for an unavailable capability is not an available command.

## Correction, removal, migration and reviewed disclosure

| Command after `helseark --vault V` | Inputs and result |
|---|---|
| `correct --person P --resource REF --reason TEXT` | Starts a bounded editable draft; reason begins transcription:, entered-in-error: or cancellation:. Prepare/review/commit remain mandatory |
| `candidate prepare DIRECTORY --person P --source HASH --amendment-target REF --amendment-reason TEXT` | Explicit laboratory amendment from a newly retained source; no automatic matching |
| `erase plan --person P --quarantine NEW_PATH --out NEW_FILE` | Seals selected paths and retained shared migration metadata disclosure |
| `erase apply PLAN --approve DIGEST` | Digest-approved native recoverable moves; repeat exact apply to resume |
| `erase restore QUARANTINE --approve DIGEST` | Restores actual quarantined paths without replacing existing files; never purges |
| `migrate plan --to-contract 0.1.0` | Emits supported identity-copy plan; `--test-only-legacy` opts into labeled wrapper machinery |
| `migrate plan --to-fhir VERSION` | Separate unsupported FHIR conversion report, exit 6 |
| `migrate apply --plan FILE --reviewed-plan-sha256 DIGEST --into NEW_PATH` | Verified separate vault; `--resume` explicitly resumes staging; repeat fixture opt-in when applicable |
| `export-plan --person P --out NEW_PATH` | Source disclosure plan; default full-person, optional selected-current/resources and supplied `--derivatives FILE` |
| `export-review --plan PLAN --decision FILE` | Records explicit human disclosure decision |
| `export --person P --out NEW_PATH --review PLAN` | Bound original inclusion or derivative exchange; no blanket source authority |

See [correction](../how-to/correct-record.md), [family recovery](../how-to/manage-family.md),
[migration](../how-to/migrate-archive.md) and [source disclosure](../how-to/export-records.md).
Removal retains approval-bound shared historical receipts, including encoded UUIDs;
quarantine is recoverable and is not secure erasure. Migration validates historical
receipts against their own inventory, never today's mutable heads/work.

## Output

`--json` writes strict JSON to stdout (one object or array, not JSONL). Domain
errors write safe code/message/details JSON to stderr; normal successful output
contains sensitive data. Query, candidate, doctor, backup and export outputs are
JSON even without the flag. Other plain output is command-specific paths, person
IDs, task lines or validation text. Argparse help is human-readable. No default
error dump of source content is intended.

## Errors and recovery

| Exit | Meaning / representative codes | Supported response |
|---|---|---|
| 0 | Completed operation; already-accepted is also success | Check disposition/counts; validation success is not review |
| 2 | Invalid input, fatal validation or budget; INVALID_INPUT, DESTINATION_EXISTS, PERSON_MISMATCH, CONTEXT_BUDGET_EXCEEDED | Correct explicit scope/input or choose absent target; do not waive fatal issues |
| 3 | Review needed/blocked; REVIEW_REQUIRED, IDENTITY_UNCONFIRMED, REVIEW_MISMATCH, SOURCE_SCOPE_REVIEW_REQUIRED | Inspect exact proposal/identity, reprepare when changed; selected source-free snapshot may meet a different export goal |
| 4 | STALE_BASE, ARCHIVE_BUSY | Wait for actual writer; rebuild/review against current selected head |
| 5 | Integrity/I/O, KIT_MISMATCH, DEFINITION_MISMATCH; unmapped domain errors default here | Preserve bytes; doctor and verified backup recovery into a new path |
| 6 | Unsupported version/capability or missing dependency/kit/definition | Acquire matching approved local tools/artifacts outside normal operations; never silently fetch/repin |

Validation reports use 2 for errors, 3 for unresolved review issues, and dedicated
4/5/6 for stale/integrity/unsupported cases. Doctor returns 5 for errors, 3 for
other issues, 0 only when no issues. Backup verify returns 5 for reported issues.
Some adapter errors supply an explicit exit in details; read the safe code and
retainedSource receipt, not just the number. See [recovery](../how-to/troubleshoot.md).
## Structured intake, history, OCR, reports and optional validation

| Command after `helseark --vault V` | Inputs and result |
|---|---|
| `intake fhir-r4 SOURCE --person P --mapping FILE` | Explicit IdentityMapping; issued candidate/coverage, no acceptance |
| `intake metrics-csv SOURCE --person P --mapping FILE` | Explicit CsvMetricMapping, decimal/dialect/unit/time policy; issued candidate |
| `intake add SOURCE --person P --packet NEW_PATH --ocr-config FILE` | Retained extraction from pinned local tools; optional macOS-only |
| `history --person P --kind TYPE` | Repeat kind for eight native history families; optional exact `--at-head` |
| `report --person P --out NEW_PATH` | Static HTML/CSV/SVG selected snapshot; default vault/derived/reports/PERSON |
| `validate proposal DIRECTORY --person P --official-config FILE` | Host config, new generation/report; optional `--require-official`; never review/acceptance |

See [structured mapping](../how-to/import-structured-data.md), [history](../how-to/query-history.md),
[OCR](../how-to/run-ocr.md), [reports](../how-to/generate-reports.md) and
[official validator](../how-to/run-offline-validator.md). Failed explicit validator
requests revoke earlier pending authority; re-run successfully and review anew.
Host reconciliation files are regular/no-follow and bounded at 64 MiB; review
decisions at 1 MiB. FIFO/device/symlink inputs fail without waiting for a producer.
