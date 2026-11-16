# Local terminology search and mapping review

The [Helseark skill](../skills/helseark/SKILL.md) can use a small local helper to
search pinned LOINC releases and translations and check proposed LOINC/UCUM
coding. No experimental Helseark runtime is required. Text-only records remain
valid when the catalog or source context is unavailable. The helper does not
choose a clinical mapping or accept a record.

## Set up a catalog separately

Obtain an official ZIP from [LOINC downloads](https://loinc.org/downloads/), using
your own account when required. Download through the official site yourself;
do not put credentials in commands, notes or this repository. Retain the release
identifier, original ZIP, trusted SHA-256 and applicable notices. The
[Portuguese (Brazil) translation](https://loinc.org/translations/pt-br/) is included
as `AccessoryFiles/LinguisticVariants/ptBR11LinguisticVariant.csv`; see also
[LOINC international translations](https://loinc.org/international/).

Obtain `ucum-essence.xml` from the official
[UCUM release artifacts](https://ucum.org/docs/artifacts). Review the
[LOINC license](https://loinc.org/license/) and [UCUM terms](https://ucum.org/license)
before use or redistribution; upstream materials are not covered by Helseark's
MIT license. Do not commit account downloads or patient data to this repository.

Acquisition is an explicit network operation. For a public HTTPS artifact with an
independently reviewed digest, the helper can fetch to a new file:

```sh
python3 skills/helseark/scripts/terminology.py fetch \
  --url 'https://example.org/official-artifact' \
  --sha256 REVIEWED_SHA256 --output /private/catalog-downloads/NEWFILE
```

Replace the placeholder URL and digest with the reviewed official artifact.
This fetch command is not an authenticated LOINC downloader. It verifies supplied
bytes against the digest; it cannot establish the digest's trustworthiness.
Build a new local package from the retained files:

```sh
python3 skills/helseark/scripts/terminology.py install \
  --loinc-zip /private/catalog-downloads/LOINC.zip \
  --loinc-version RELEASE \
  --ucum-xml /private/catalog-downloads/ucum-essence.xml \
  --destination /private/catalogs/NEW-DIRECTORY
```

The package retains `manifest.json`, `loinc.zip` and `ucum.xml`. The manifest pins
artifact digests and release metadata; lookup verifies integrity locally. Keep
packages outside health folders and use an exact package path. Installation
records the supplied release identifier; review that it matches the acquired ZIP.
Updates create a new package after explicit acquisition and review. They do not
rewrite earlier drafts, accepted files or approved mapping evidence.

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

During extraction, the agent searches the original label across the installed
English terms and available linguistic variants, including translated components
when full translated names are blank. It can try useful translations,
expanded abbreviations or alternate spellings without making the user identify
a language. Retain the original label, search terms and translation uncertainty
in the evidence. A language guess is neither clinical evidence nor permission to
interpret a decimal comma or date format.

```sh
python3 skills/helseark/scripts/terminology.py search \
  --package /private/catalogs/RELEASE --text 'proteína C reativa' --limit 10
```

Optional `--system`, `--property`, `--time`, `--scale` and `--method` filters narrow
candidates using known context. Results are ordered by code, not clinical
relevance; a lone result does not establish equivalence. Translations and example
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
  --package /private/catalogs/RELEASE \
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
digests used for the check; retain these actual pins in the mapping evidence.
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
