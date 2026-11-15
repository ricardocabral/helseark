---
name: query-history
description: Answer selected-person history questions with exact revision and source citations while exposing contradictions and incomplete reads.
---

# query-history

Read [common archive instructions](../../AGENTS.md) first. Task ID: `query`.

Use supplied snapshot records and their evidence only. Cite `Type/id/_history/revision`, source digest, locator and quote for each assertion. Carry each value's unit, range, method, specimen, date precision and status where supplied. Separate contradictory assertions; exclude invalidated values from numeric trends without erasing history. Do not merge by label or convert units. Report returned counts/continuation and no-record scope. Write only `output/report.md`; missing evidence blocks a source-cited claim.

Contracts: [clinical model](../../docs/reference/clinical-model.md#identity-references-and-versions), [evidence checklist](../../docs/reference/clinical-model.md#evidence-checklist), [archive identity/revisions](../../docs/reference/archive-format.md#identity-and-revisions).

Prompt routes: [`query-with-evidence`](../../prompts/query-with-evidence.md).

Capability dependencies: `agent-context`, `clinical-query`. Check availability in the
[common capability section](../../AGENTS.md#capability-availability), then the trusted
runtime registry; this dependency list does not establish availability. The runtime supports file-scan query and bounded date-filtered contexts. Model behavior
requires a separate observed evaluation; deterministic tests are not model accuracy.


Operator query routes (fixed documented syntax, never assembled from source text):

- `helseark --vault PATH observations --person UUID --label LABEL --json`
- `helseark --vault PATH observations --person UUID --from-date YYYY-MM --to-date YYYY-MM --include-invalidated --json`
- `helseark --vault PATH timeline --person UUID --json`
- `helseark --vault PATH record --person UUID --resource Type/UUID/_history/REVISION --json`

All three accept `--at-head HEAD_JSON` for a historical snapshot. See the
[query workflow](../../docs/how-to/query-history.md) for Head capture, exact decimal
JSON, evidence-entry resolution and bounded date-filtered context pagination.
The timeline is the graph at its Head, not all superseded revisions. Follow exact
report `resultRefs`; show `REPORT_RESULT_REVISION_MISMATCH` instead of substituting
current corrections into a historical report. Native report narrative is available
through `record`; never invent a medical summary from resource references alone.
Unknown-time rows remain visible. Calendar bounds use the source calendar; offset
bounds compare UTC instants. Read each `QUERY_TIME_SELECTION` issue in a date-filtered
packet, including precision/relation/unknown bucket. Never infer an unknown zone.

An evidence binding identifies an exact accepted entry; do not copy a whole evidence
file into the model context. Keep the existing scoped evidence projection and
host-retained construction authority. `EVIDENCE_SCOPE_REQUIRED` requires a separate
whole-source disclosure decision; a retry is not authority to broaden the request.

For profile-set 0.2.0 history use `history --person PERSON --kind TYPE` (repeat
`--kind`) or timeline's native `resource`, sourceRefs and issues. Report native
status and verification qualifiers together. Unknown dates stay unknown; do not
turn recording time into onset or summarize assertions as inferred diagnoses.

Static presentation is a host operation: `helseark --vault PATH report --person UUID --out ABSENT_PATH --json`. See [generate reports](../../docs/how-to/generate-reports.md). It creates escaped offline HTML and formula-neutralized CSV from accepted query rows, retaining exact values, status, comparators, per-result ranges and incompatible contexts. No grouping or unit conversion. This does not expand the agent output permission beyond `output/report.md`; no accepted edits or source blob disclosure.
