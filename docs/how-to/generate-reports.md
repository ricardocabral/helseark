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
integrity/I/O failures return exit 5. Direct symlinks and symlink destination
ancestors are refused. Missing ordinary parent directories are supported, including
nested external exports. Concurrent creation of the destination fails without
replacing the competing directory, even if it is empty.

On macOS/Linux local filesystems, publication traverses directories with no-follow
handles and uses handle-relative exclusive directory rename. The report files are
complete before the destination becomes visible. Replacement of a checked parent
pathname cannot redirect file writes, publication or cleanup through a new symlink.
Detected parent replacement/relocation fails with `INVALID_DESTINATION`; recovery
does not follow the output pathname or write into accepted history. Private staging
is normally in the system temporary directory, or on the destination filesystem for
a different mounted volume. Ordinary failures remove task-owned stage files; missing
parent directories created for an unsuccessful request can remain empty. If a
replacement races the final native rename, the command reports changed authority
and the complete report can remain in the original directory. Preserve it for
inspection; never follow the replacement pathname to remove it.

Directory handles authorize specific directory inodes; they do not freeze their
location. Host permissions must prevent other principals from relocating those
opened inodes between an identity check and a mutating syscall, and from tampering
with private staging. A same-user/root process with those powers is outside this
bounded path-authority guarantee. Identity checks detect observed relocation; they
are not an atomic ancestry lock or a hostile-host authenticity guarantee. If a
same-filesystem staging authority moves, error recovery retains that private stage
for inspection instead of mutating its new location. Do not automatically move it
back or clean protected paths. These assumptions apply to external destinations as
well as derived output. Unsupported no-replace platforms fail closed.

Read each result's status, comparator, exact decimal spelling, native date and
precision, per-result range, method, specimen, components and issues together.
`<0.050` is a bound, not a point. Missing/not-performed, qualitative negative and
zero remain distinct. Equal labels do not establish comparable contexts. The
report performs no arithmetic, conversions, trend grouping or clinical advice.
Cancelled/entered-in-error observations remain explicitly visible for audit.
The timeline is the current graph, not every historical revision; source report
result references and query revision-mismatch issues remain visible. Use
[query history](query-history.md) for historical Heads and complete native records.
The native timeline includes the eight supported history families, with status,
unknowns, native fields and evidence retained. `report.svg` is a standalone textual
factual figure of those same native assertions and citations. It adds no numeric
axes, aggregation or inferred comparability. HTML is the complete accessible
structured view; the SVG contains no scripts or embedded original sources.

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
after leading Unicode whitespace, control (`Cc`) or format (`Cf`) characters,
receive a literal apostrophe. This includes NUL, BOM and zero-width-space prefixes;
the original characters remain after the apostrophe. This is the supported byte
neutralization policy, not a qualification of every spreadsheet importer.
Tab/CR/LF-leading cells also receive it. Spreadsheet applications differ; retain that protective prefix.
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
