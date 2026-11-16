# Bundled bilingual vocabulary

This starter vocabulary works offline with the Helseark skill and standalone
terminology helper. No LOINC account or download is required:

```sh
python3 skills/helseark/scripts/terminology.py search --text 'mau colesterol'
python3 skills/helseark/scripts/terminology.py search --text 'LDL cholesterol'
```

Paths above are relative to the repository; the helper locates this vocabulary
relative to its own file, so it also works from another working directory.
Keep the repository alongside the skill when copying it.

## Coverage and source

Version 0.1.0 includes 24 active LOINC 2.83 concepts across 12 starter families:
LDL, HDL, total cholesterol, triglycerides, HbA1c, TSH, creatinine, hemoglobin,
C-reactive protein, leukocytes, relative neutrophils and absolute neutrophils.
Corresponding official Brazilian Portuguese rows are present for 23 concepts.
Unmodified UCUM 2.2 essence definitions support the existing bounded unit checker.

There are 327 retrieval aliases: 326 supplied from Janusmed's authorized
vocabulary snapshot and one Helseark spelling. Language tags distinguish
165 English, 108 PT-BR and 54 unspecified-locale entries; unspecified entries
are not asserted to be English or Portuguese. Two mislabeled CJK entries were
excluded. Original synonym spelling and source IDs are retained. The
[manifest](manifest.json) lists exact family coverage, versions, hashes,
provenance and limitations.

Janusmed supplied synonym strings, not a LOINC crosswalk. Helseark's candidate
associations are retrieval aids requiring source context and human review.
Broad aliases deliberately retrieve multiple candidates: calculated/direct LDL,
mass/molar concentration and HbA1c standardization remain distinct. `%` is a
meaningful search token. No approved reusable clinical rules are shipped in
[mappings.json](mappings.json); never invent approval metadata to populate it.

## Notices

- Official LOINC subset: [upstream copyright and license](LICENSES/LOINC.txt).
  All upstream columns and field values are retained; only records are selected.
  [Translation documentation](LICENSES/LinguisticVariantsReadMe.txt) and
  [producer relationships](LICENSES/LinguisticVariants.csv) are retained unchanged.
- UCUM: [copyright, license and warranty disclaimer](LICENSES/UCUM.txt).
  Copyright ©1999–2024 Regenstrief Institute, Inc. All rights reserved.
- Janusmed strings: [attribution and scope of permission](LICENSES/Janusmed.txt).
  Helseark-authored associations and additional aliases use the repository's
  [MIT license](../LICENSE). Upstream LOINC and UCUM content does not.

## Contributions and releases

Propose aliases separately from clinical mappings. Supply exact term, language,
provenance and redistribution authority, candidate codes with pinned release,
and invented positive/ambiguous examples. An alias can legitimately have several
targets. A new term or candidate association needs independent review, never
automatic promotion from a patient's draft. Do not publish patient content.

For a new official subset, use an explicitly acquired release, preserve upstream
field values and required relationships, include its original license/notices,
and record original artifact/member hashes. Do not substitute ad hoc translations
for official fields. Review upstream translation and third-party restrictions.
Keep privately sourced exports outside the checkout; publish only authorized
vocabulary entries. Inspect the actual words as well as their source locale tags.

Update the vocabulary version and every changed artifact digest together. Keep
LOINC code/release identity separate from the vocabulary release. Recheck alias
targets against active definitions and method/specimen/property distinctions;
never transfer clinical approval to another release. Preserve previously used
catalog packages and accepted record versions. A generated search index, if
added later, must remain reproducible from these maintained source files.

Run the focused checks in [CONTRIBUTING.md](../CONTRIBUTING.md), including all
`test_terminology*.py` tests. Demonstrate fresh-checkout offline search/check,
ambiguity, corruption rejection and unchanged source observations. These tests
verify retrieval and declared context, not clinical equivalence.
