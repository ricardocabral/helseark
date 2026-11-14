# Query accepted history

Choose the person explicitly, even in a one-person vault. These read-only commands
work offline with the installed distribution; no checkout, cache, database or
model is required. Inputs are accepted FHIR files, never candidate drafts.

```sh
helseark --vault /path/to/vault observations --person UUID --label 'Proteína C reativa — ultrassensível' --json
helseark --vault /path/to/vault observations --person UUID --from-date 2026-11 --to-date 2026-11 --json
helseark --vault /path/to/vault observations --person UUID --code-system urn:synthetic:lab --code crp --include-invalidated --json
helseark --vault /path/to/vault timeline --person UUID --json
helseark --vault /path/to/vault record --person UUID --resource Observation/UUID/_history/REVISION_UUID --json
```

Outputs use exact decimal JSON. Parse decimals with `Decimal`, never binary float.
The observation's `valueType` identifies its native FHIR `value` subtree; a missing
value with `dataAbsentReason`, a negative qualitative result and zero are distinct.
Read each range/unit/method/specimen/status beside that measurement. Components
retain their own values/ranges. `sourceRefs` locate exact accepted evidence entries
by path, digest and entry pointer; those entries bind source hashes/documents,
locators, quotes and target pointers. Use `record` for the complete native result,
report narrative, specimen or pinned child. Equal labels do not justify combining
results, drawing a trend or converting units.

Calendar date filters include partial-date/period overlaps and undated rows. Read
`timeFilterRelation` and `timeBucket`: an unknown date is not evidence that the
measurement happened within the range. Offset timestamp filters compare instants;
date-only times cannot be assigned a timezone. Do not mix those filter modes.
Default observations omit cancelled/entered-in-error values; timeline retains their
statuses. Neither command computes a clinical chronology from ambiguous dates.

For a reproducible snapshot, save the selected person's exact Head through the
installed library (the three fields are also `base` in an agent context):

```python
from pathlib import Path
from dataclasses import asdict
from helseark.archive import open_definitions, head
from helseark.serialization import encode_json
vault = open_definitions(Path('/path/to/vault'))
Path('head.json').write_bytes(encode_json(asdict(head(vault, 'PERSON_UUID'))))
```

Add `--at-head head.json` to observations, timeline or record. An unknown Head fails
explicitly. Reports keep their exact historical result references after a child
correction; `REPORT_RESULT_REVISION_MISMATCH` warns that today's current observation
differs. Follow the pinned report child with `record`, not a new logical lookup.
To inspect earlier revisions use their exact references or an earlier Head. Current
timeline is the graph at its Head, not a log of all accepted transactions.

For a model handoff, select explicit revisions and prepare bounded date-filtered
pages. The CLI never invokes a model:

```sh
helseark --vault /path/to/vault agent context --task query --person UUID --resource Observation/UUID --from-date 2026-11 --to-date 2026-11 --max-records 100 --out /absent/page-1 --json
```

Retain `trustedContextSha256` from stdout outside the packet. For subsequent pages,
repeat the same filters/selectors and pass `--continuation /absent/page-1/context.json`
with a fresh output path. Continue until `continuation=null`; report returned and
total counts. Unknown dates stay selected and `QUERY_TIME_SELECTION` issues expose
the query relation and precision. A changed selection or Head invalidates the
continuation. Rendering still needs the host-retained digest; see the
[host handoff protocol](../reference/agent-protocol.md#prompt-rendering-and-host-handoff).
An `EVIDENCE_SCOPE_REQUIRED` failure is not permission to add a source: obtain
explicit authority for the whole source or narrow the references. Ambiguous or
oversized evidence fails without truncation or broader disclosure.

For an offline HTML/CSV view of one accepted snapshot, use the host
[static report workflow](generate-reports.md). It preserves per-result context
and includes invalidated results for audit without combining them into trends.
