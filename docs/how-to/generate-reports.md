# Generate an offline static report

Select a person and render accepted observations and the current graph timeline:

```sh
helseark --vault /path/to/vault report --person PERSON_UUID --json
```

The default fresh directory is `vault/derived/reports/PERSON_UUID`. Open its
`index.html` in a local browser. No server, network, fonts, scripts, model, OCR,
SQLite database or checkout is required. The result also contains
`observations.csv`, with one row per Observation and exact JSON for structured
fields. An explicit destination must be a fresh directory under `vault/derived`
or outside the vault:

```sh
helseark --vault /path/to/vault report --person PERSON_UUID --out /private/local-report --json
```

The library route is
`render_static_report(vault: Vault, person: PersonId, destination: Path) -> Path`
from `helseark.presentation`; it returns the published `index.html` path. It pins
one accepted Head for both queries. It never accepts candidates, changes accepted
records, or replaces an existing destination. A successful command returns exit
0 and a `path`; invalid/protected or existing destinations return exit 2, and
integrity/I/O failures return exit 5. Symlink destination ancestors are refused.

Read each result's status, comparator, exact decimal spelling, native date and
precision, per-result range, method, specimen, components and issues together.
`<0.050` is a bound, not a point. Missing/not-performed, qualitative negative and
zero remain distinct. Equal labels do not establish comparable contexts. The
report performs no arithmetic, conversions, trend grouping or clinical advice.
Cancelled/entered-in-error observations remain explicitly visible for audit.
The timeline is the current graph, not every historical revision; source report
result references and query revision-mismatch issues remain visible. Use
[query history](query-history.md) for historical Heads and complete native records.
Broader clinical-history presentation is outside this renderer's current contract.

Source links identify exact accepted evidence file/entry pointers with evidence
and original source digests and source DocumentReference revisions. Open the JSON
and follow the displayed `/entries/N` pointer for target fields, quotes and
locators; browsers do not necessarily scroll to JSON Pointer fragments. No source
blob is copied or embedded: shared sources can contain other people. Do not treat
a link as permission to share an entire source. These local links require the
vault at its original location. For a portable archive use the
[reviewed export workflow](export-records.md).

All source text is escaped in HTML. A restrictive content security policy forbids
remote content and scripts. CSV cells beginning with formula characters, including
after leading whitespace, receive a literal apostrophe. Tab/CR/LF-leading cells
also receive it. Spreadsheet applications differ; retain that protective prefix.
Use HTML or accepted native JSON when the exact original string is needed.
Decimal values are emitted without binary floating-point conversion, but a
spreadsheet can still round them when importing; import columns as text.

Reports contain sensitive selected-person data and local vault paths. They are
disposable projections, not review receipts, clinical certification or backups.
No report grants an agent permission to edit accepted records; imports always
require the existing human review flow. Existing vault and historical kit pins
are never rewritten. To rebuild, explicitly delete the report directory (or the
whole disposable `derived/` tree), then rerun the same command against an unchanged
Head. Bytes repeat at the same destination and vault location. A new Head or a
moved vault can legitimately change bytes. Keep external exports private and
remove them separately when no longer needed.
