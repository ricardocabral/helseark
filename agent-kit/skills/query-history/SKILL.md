---
name: query-history
description: Answer selected-person history questions with exact revision and source citations while exposing contradictions and incomplete reads.
---

# query-history

Read [common archive instructions](../../AGENTS.md) first. Task ID: `query`.

Use supplied snapshot records and their evidence only. Cite `Type/id/_history/revision`, source digest, locator and quote for each assertion. Carry each value's unit, range, method, specimen, date precision and status where supplied. Separate contradictory assertions; exclude invalidated values from numeric trends without erasing history. Do not merge by label or convert units. Report returned counts/continuation and no-record scope. Write only `output/report.md`; missing evidence blocks a source-cited claim.

Contracts: [clinical model](../../../docs/reference/clinical-model.md#identity-references-and-versions), [evidence checklist](../../../docs/reference/clinical-model.md#evidence-checklist), [archive identity/revisions](../../../docs/reference/archive-format.md#identity-and-revisions).

Prompt routes: [`query-with-evidence`](../../prompts/query-with-evidence.md).

Capability dependencies: `agent-context`, `clinical-query`. Check availability in the
[common capability section](../../AGENTS.md#capability-availability), then the trusted
runtime registry; this dependency list does not establish availability. This skill is
draft-only until those dependencies are implemented and evaluated.
