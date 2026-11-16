# Local terminology search and mapping review

The [Helseark skill](../skills/helseark/SKILL.md) can use a small local helper to
search pinned LOINC releases and translations and check proposed LOINC/UCUM
coding. No experimental Helseark runtime is required. Text-only records remain
valid when the catalog or source context is unavailable. The helper does not
choose a clinical mapping or accept a record.

## Use the supplied vocabulary

A fresh checkout includes a [bilingual starter vocabulary](../vocabulary/README.md):
24 active LOINC 2.83 concepts, official PT-BR variants, 327 retrieval aliases
(326 from Janusmed), and complete unmodified UCUM 2.2 essence definitions.
The manifest pins source artifacts, notices, coverage and every used file.
Neither an account nor a download is required. Keep the repository with the skill;
the helper resolves its default vocabulary relative to its own script.

```sh
python3 skills/helseark/scripts/terminology.py search --text 'LDL-Colesterol'
python3 skills/helseark/scripts/terminology.py search --text 'LDL cholesterol'
python3 skills/helseark/scripts/terminology.py search --text 'hemoglobina glicada'
```

Without `--package`, both `search` and `check` use this bundle. Covered families
include lipids, HbA1c, TSH, creatinine, hemoglobin, CRP and selected blood counts;
see the manifest for the exact coverage. A missing match is a coverage gap, not
an invalid record. Preserve source text when coding is unsupported.

Janusmed supplied authorized synonym strings, not LOINC mappings. The candidate
associations are Helseark retrieval aids, explicitly marked `retrieval_only`.
Search preserves ambiguity and the `%` token; alias matches never establish
clinical equivalence. No human-approved reusable clinical mappings are shipped.

## Optionally complement the bundle

At setup or when broader coverage would help, an agent offers once: continue with
the supplied vocabulary, import an existing official ZIP, or download full LOINC
after account creation. Honor a preference already supplied, retaining it in
private setup/review notes rather than clinical profile fields. Declining is
fully supported; do not repeatedly prompt for every unmatched label. A read-only
query does not create preference files or acquire catalogs.

Acquisition is a separate explicit operation. Search, checking and extraction
remain offline. Keep full packages in a private terminology cache outside the
repository and health archive. New releases never rewrite accepted records,
previous packages or approved mapping evidence.

### Import an existing ZIP

Obtain an official ZIP from [LOINC downloads](https://loinc.org/downloads/) using
your own account when required. Keep the actual release identifier, original
bytes and applicable notices. The [Portuguese (Brazil) translation](https://loinc.org/translations/pt-br/)
is included at `AccessoryFiles/LinguisticVariants/ptBR11LinguisticVariant.csv`.
Use the bundled UCUM file or an independently acquired official release:

```sh
python3 skills/helseark/scripts/terminology.py install \
  --loinc-zip /path/to/private/downloads/Loinc_2.83.zip \
  --loinc-version 2.83 --ucum-xml vocabulary/ucum.xml \
  --destination /path/to/private/catalogs/loinc-2.83
```

Replace example paths with private locations whose parent directories exist;
the output destination must be new. Installation retains `manifest.json`,
`loinc.zip` and `ucum.xml` and checks pinned artifacts offline on each lookup.
The supplied release identifier must match the acquired ZIP.

### Download using your account

Create a LOINC account and accept the official terms yourself. Run the separate
[acquisition script](../skills/helseark/scripts/loinc_download.py) in a local user
terminal. Both username and password are prompted without echo and stay outside
the agent conversation. Never paste passwords into chat or put them in command
arguments, URLs, logs, notes or repository files. The script requires a user
terminal and refuses an echoed-input fallback.

```sh
python3 skills/helseark/scripts/loinc_download.py \
  --version 2.83 --destination /path/to/private/downloads/loinc-2.83
```

The [official authenticated Download API](https://loinc.org/kb/api/download/)
returns release metadata and ZIP bytes. The script verifies the requested
release, restricts requests to the official HTTPS origin, refuses redirects,
checks the metadata's MD5 and retains a local SHA-256 in `receipt.json` alongside
`loinc.zip`. MD5 checks transfer integrity; the SHA-256 pins the acquired bytes
for later use. Neither proves clinical meaning. It publishes into a fresh private
directory only after verification; the receipt is the completion marker.
It does not install a catalog or modify records. Then use the import command
above with the downloaded ZIP. Browser download and local import remain a
supported fallback. Never run credential entry inside an agent-controlled terminal
whose input could be captured in the conversation or transcript.

Authenticated live acquisition requires a user account and has not been exercised
with real credentials here. Automated acquisition tests exercise synthetic HTTPS
metadata, ZIP bytes, redirects and failure cleanup with no account.

The existing `terminology.py fetch --url URL --sha256 DIGEST --output NEWFILE`
command remains available for credential-free public HTTPS artifacts with an
independently reviewed digest; it is not the authenticated LOINC downloader.
Review [LOINC licensing](../vocabulary/LICENSES/LOINC.txt) and
[UCUM licensing](../vocabulary/LICENSES/UCUM.txt) before redistribution.

### Select the full package offline

```sh
python3 skills/helseark/scripts/terminology.py search \
  --package /path/to/private/catalogs/loinc-2.83 --text 'mau colesterol'
```

The selected full package supplies the clinical definitions and can find codes
outside starter coverage. Bundled aliases remain discovery aids only where each
target code, active status and all six axes can be reconciled with that package.
Results record selected and bundled pins, revalidation and suppressed-candidate
diagnostics. A changed or missing definition does not silently inherit an alias
association. Human-approved rules remain release-specific; one coding proposal
uses one pinned catalog release. No full-package file is overlaid on the bundle.

The helper limits each input artifact and each consumed ZIP member to 256 MiB,
and the total uncompressed bytes read from the core and linguistic-variant CSVs
to 512 MiB. Unused accessory contents are not read or extracted. All ZIP member
paths, symlink flags and duplicate names are checked, with at most 10,000 members.
Automated tests use synthetic distributions. A local check on 2026-11-16 of the
official LOINC 2.83 ZIP confirmed installation of 112,405 codes and 21 languages,
and Portuguese component searches for C-reactive protein and triglycerides.
This checks package compatibility and retrieval, not clinical equivalence or
other releases. Full-release parsing retains catalogs in memory; the local check
used about 1.5 GB of peak process memory. If a package exceeds these bounds or
has an unsupported layout, report that limitation and retain uncoded source text.
Do not substitute an unverified package.

## Search automatically, then assess context

During extraction, the agent searches the original label across the bundled or selected
English terms and available linguistic variants, including translated components
when full translated names are blank. It can try useful translations,
expanded abbreviations or alternate spellings without making the user identify
a language. Retain the original label, search terms and translation uncertainty
in the evidence. A language guess is neither clinical evidence nor permission to
interpret a decimal comma or date format.

```sh
python3 skills/helseark/scripts/terminology.py search \
  --text 'proteína C reativa' --limit 10
```

Optional `--system`, `--property`, `--time`, `--scale` and `--method` filters narrow
candidates using known context. Exact bundled-alias matches appear before broad
native-token matches, with stable code ordering within each group. This is a
retrieval signal, not clinical ranking; a lone result does not establish equivalence. Translations and example
UCUM units aid discovery; example units are not a whitelist of clinically valid
assignments.

LOINC defines observations through [component, property, time, system, scale and
method](https://loinc.org/kb/users-guide/major-parts-of-a-loinc-term/). Cite source
support for each relevant axis, including specimen and method. Do not substitute
an assumed serum specimen, mass concentration, point-in-time collection or method
for missing information. An empty method in a catalog term does not erase a
source's method difference. If context is missing, contradictory or leaves
multiple plausible codes, abstain: retain source text and list the unresolved
candidates and questions. Do not guess a code from memory.

## Propose a mapping in the draft

An agent may propose a new mapping, not just reuse an existing one. Keep the
source-provided coding distinct from agent-proposed coding in readable evidence.
For each proposal retain the source filename/location/quote, target resource and
fields, source context, alternatives, rationale, catalog versions/digests and
local check result. Cite translations as terminology aids, not source facts.

The helper reads one Observation JSON and a supporting proposal JSON:

```sh
python3 skills/helseark/scripts/terminology.py check \
  --observation /private/health/drafts/NEW/observation.fhir.json \
  --proposal /private/health/drafts/NEW/mapping-proposal.json
```

The proposal has `loinc`, optional `ucum`, `context` and `evidence`. Both context
and evidence contain `component`, `property`, `time`, `system`, `scale` and
`method`; context values are the candidate's axis strings, while evidence values
cite the source and explain the assignment. An empty method needs explicit
explanation. Additional context can identify `lab`, `local_test`, `specimen` and
`unit`. Any proposed UCUM code requires a nonempty original
`valueQuantity.unit`, an exactly matching literal `context.unit`, and a nonempty
`evidence.unit` citation explaining the source unit and proposed assignment.
Missing original units or unit evidence leave the proposal unresolved; do not
choose a unit automatically. See the
[invented terminology examples](../examples/terminology/).

`check` returns issues, proposed native FHIR additions and the artifact/manifest
digests used for the check, including the vocabulary version when applicable;
retain these actual pins in the mapping evidence.
It never edits the Observation. It checks catalog membership, declared axes and
supported UCUM syntax. It does not read or prove source citations, establish dimensional
compatibility, verify clinical equivalence, run a complete UCUM validator or
approve anything. A successful result still requires human review. Unsupported
unit syntax must remain unresolved rather than be declared invalid clinical data.

In the final draft, use `Observation.code.coding` with `system = http://loinc.org`,
the package release in `version`, the code and catalog display. Preserve the
original `code.text` and source coding. A supported UCUM assignment uses
`valueQuantity.system = http://unitsofmeasure.org` and `valueQuantity.code`;
preserve the original `unit`, numeric token/scale and comparator. Do not convert
values or alter spelling/case to force a unit match. The proposal and review note
support the FHIR record; they are not a second canonical clinical store.

## Review and reuse within explicit conditions

Review the exact final draft, proposal and mapping evidence together. Record the
actual reviewer, date, decision and remaining concerns. A helper result, source
`final` status or prior approval of another record is not approval of this draft.
Any changed file needs fresh review. Enriching an accepted record requires a new
correction draft with before/after evidence; preserve the prior accepted bytes.

If the reviewer approves future reuse, state its scope: laboratory, local test,
specimen, method and unit, with rule version, LOINC release and supporting evidence.
The optional proposal `rule` records `decision: approved`, `approved_by`,
`approved_at` (ISO date), `version`, `loinc_version`, `evidence`, `conditions`
(the five scope fields), `loinc` and optional `ucum`. All conditions must match
cited context for the new source. The helper can report eligibility for human
review; it cannot authenticate the reviewer or make approval reusable outside its
scope. Changed method, specimen, unit or release requires reassessment. Retain
fresh source citations and review the new draft even when reusing a rule.

## Queries and charts

Language-assisted search can expand a query without editing records. Report
which terms, records and mappings were searched and preserve unknown dates,
original specimen/collection dates, bounds, duplicates and method differences.
Grouping for retrieval or a chart is a separate decision from coding an
Observation. A shared code or label does not prove measurements comparable; do
not merge distinct observations or infer a trend from incomparable results.
