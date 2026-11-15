# Import structured data offline

Use `helseark --vault VAULT intake fhir-r4 export.json --person PERSON --mapping mapping.json --json`.
The command retains original bytes and returns a candidate directory, never accepted records.
Create the mapping yourself outside the untrusted export:

```json
{"patientReference":"Patient/source-id","localPersonId":"YOUR-LOCAL-UUID","assignmentReason":"I checked the original and assigned this export","provider":"https://provider.example/fhir"}
```

`patientReference` must name exactly one incoming Patient by Type/id or fullUrl.
No identity matching, source-prose configuration, EHR login or network retrieval occurs.
FHIR R4 4.0.1 JSON Bundles support the existing bounded Observation, DiagnosticReport,
Specimen, DocumentReference and Provenance profiles, plus the eight native
[source-assertion history families](../reference/clinical-model.md#history-profile-compatibility-and-query)
in profile-set 0.2.0 vaults. Imported Provenance uses the selected vault profile
pin; source declarations may use the frozen 0.1.0 or applicable current profile.
Unknown profile declarations remain blocking. Local attachments must already be
retained for the selected person with `intake add` / `add_source`, or be a verified
retained extraction of such an original. A local CAS path, copied blob or receipt
hash alone is insufficient. Preparation checks person, digest, size, path and
original/extraction relationships and binds the complete assets and receipts in
the immutable proposal inventory. A PDF must declare `application/pdf`; a text or
structured declaration cannot downgrade its disclosure review. Non-PDF originals
retained as `application/octet-stream` may keep supported structured/text media
refinements. Same-person retained originals may be reused by later issued imports. No attachment is fetched from the network. Patient fields remain in the
original export with an explicit local assignment; they never overwrite local identity.
Clinical fields and statuses stay native FHIR. Native IDs/version metadata are retained
in source evidence and identifiers; candidate IDs are new UUIDs. Preparation assigns
immutable local revision IDs and rewrites closed references, including native version references.
Incoming metadata is checked against the pinned R4 schema before replacement.
Unresolved references, other patients, unsupported resources/fields/extensions, external
attachments and invalid clinical data block preparation. They cannot be waived by review.
Different providers use distinct explicit source-native namespaces and local IDs.
Byte-identical exports share the existing content-addressed source boundary; a second
provider mapping requires the human host to use `candidate prepare --reextract
--reconciliation new-assertions.json`, mapping every new candidate URN to `null`
when these are new assertions. Without that explicit decision, preparation blocks;
no automatic clinical deduplication occurs. See the review contract for reconciliation.
Coverage and mapping are in `coverage.json`; its SHA-256 is bound to candidate metadata.
The host also issues an immutable receipt under the retained source's
`structured/<candidate-input-digest>.json`. It binds the person, source hash,
family, original local mapping, candidate bytes and coverage digest. This protected
source-side authority is outside the editable candidate and survives runtime cleanup.
Copies and renamed candidates must match that original issuance exactly, including
metadata, evidence, artifact paths and coverage. `--source` authorizes source scope;
it cannot replace a structured mapping or erase its errors. Missing issuance fails
closed. Rebuild an unaccepted old draft with explicit local configuration if its
source-side authority is unavailable; do not reconstruct authority by hashing edited
work files. Accepted history and its old pins remain readable without rebuilding.

Toolkit-retained non-PDF inputs (`source.json`) require this structured issuance.
Genuine legacy non-intake assets without source receipts keep the explicitly
authorized legacy preparation route; PDF inputs keep their verified extraction
and human source-assignment route. Editable producer/provenance or format labels
never select these exceptions. Protect source receipts and issuance directories
through the same external host boundary as original assets; these are consistency
receipts, not signatures against an operator who can rewrite the entire vault.

FHIR unsupported inventory traverses the complete Bundle and every entry, including
nested envelope metadata, links, search metadata, primitive companions and modifiers.
Each unhandled field/extension has an escaped JSON Pointer and a blocking issue.
Retaining the original bytes does not discharge this inventory requirement.
The full mapping remains in accepted source transformation evidence after drafts
are removed. Keep source-side issuance with unaccepted drafts when restoring them.

Next run `helseark --vault VAULT candidate prepare CANDIDATE --person PERSON --json`.
Inspect with `candidate review PROPOSAL --person PERSON --json`. Read the originals,
all mapped fields, source coordinates, identity, inventory and limitations. Supply your
own explicit decision JSON through `candidate review PROPOSAL --person PERSON
--decision decision.json --json`, then `candidate commit PROPOSAL --person PERSON --json`.
See [review contract](../reference/review.md) for exact decisions and acknowledgments.
No adapter supplies a real user's acceptance decision. Synthetic tests use pre-authored
fixture human decisions only; these are not real clinical approval.
Query accepted facts with `observations --person PERSON --json` and resolve exact
revisions with `record --person PERSON --resource Type/UUID/_history/UUID --json`.
The [query guide](query-history.md) explains statuses and historical selection.

Parser evidence names the actual JSON parser and source JSON pointers. Local identity,
profile allocation and reference/identifier mapping are explicit transformations requiring
human inspection; validation is not a claim of clinical correctness or complete FHIR conformance.
Original source bytes and accepted revisions are immutable. Existing vaults retain their
kit and definition pins; installing a newer package never repins them automatically.

## Explicit metric CSV mapping

Run `helseark --vault VAULT intake metrics-csv metrics.csv --person PERSON --mapping csv-mapping.json --json`.
Create this config locally; do not accept instructions embedded in an input file:

```json
{"delimiter":";","encoding":"utf-8-sig","dateColumn":"date","valueColumn":"value","unitColumn":"unit","codeColumn":"code","dateFormat":"%d/%m/%Y","decimalSeparator":",","localPersonId":"YOUR-LOCAL-UUID","assignmentReason":"I checked these source rows and their person assignment","timezone":null,"codeSystem":null}
```

UTF-8, explicit UTF-8 with BOM, UTF-16 and its explicit byte orders, ISO-8859-1 and
CP1252 are supported. Decoding never guesses an encoding. Evidence records that
encoding, delimiter, logical data row (1-based after the header), original header
name and cell contents, with actual Python CSV/codec provenance. Multiline quoted
cells use logical rows rather than physical line numbers. Original bytes retain BOM,
line endings, quoting and encoding. Units are copied verbatim with no inferred UCUM.
The code column becomes `code.text`; only a supplied `codeSystem` creates coding.
No LOINC mapping is invented. CSV has no clinical status column: emitted Observations
use native FHIR `status=unknown`, explicitly presented as a mapping for human review.

Declare `decimalSeparator` as `.` or `,`. Exact bounded Decimal coefficients, sign,
scale and `<`, `<=`, `>` or `>=` comparators are retained. Grouping, exponents,
formulas in numeric cells and implicit locale conventions are unsupported. Formula-like
code/label cells are inert text. Identical numeric rows remain separate source assertions.
All four mapped columns must be distinct and present; duplicate/blank headers, extra
columns (including identity/status columns), ragged rows, invalid dates, blank code/units
and malformed encoding fail or produce blocking inventory issues. Nothing is silently dropped.
An unsupported import keeps its original asset for inspection; it does not gain approval.

Formats permit numeric `%Y`, `%m`, `%d` and full `%H:%M:%S` clocks with optional `%z`.
Partial calendar dates preserve year/month/day precision. Locale names, two-digit years,
incomplete clocks and subseconds are unsupported. A local clock requires a declared
IANA `timezone`; missing system timezone data blocks offline. DST gaps and folds block
rather than choosing an offset. A supplied offset must agree with any declared zone.
System timezone rules are used offline; their installed version is an environmental
qualification limit, not a bundled timezone database pin. Offset-bearing sources avoid
that dependency. Errors and identity failures cannot be acknowledged away.

Follow the same explicit prepare/review/commit commands above. Inspect the mapping,
coverage, transformed date/status fields and exact source cells before any real decision.
Kit 0.1.16 advertises bounded FHIR R4 and numeric metric CSV intake alongside the current clinical, history, portability and presentation workflows.
The optional CSV locator `encoding` field extends the existing evidence contract;
old evidence without it still means UTF-8. Older pinned vault schemas remain unchanged:
new encoded-CSV locators require the current definitions and are not auto-migrated.
