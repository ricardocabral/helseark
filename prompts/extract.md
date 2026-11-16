# Extract records — copy this prompt

Ask me for one person's stable local ID, their identity cues, and the source files
I authorize you to read, if I have not supplied them. Use the Helseark agent
instructions and FHIR R4 schema supplied with this prompt. Stop if identity is
missing or inconsistent. Read no other person's records.

Create a draft FHIR R4 collection Bundle with an explicit Patient and explicit
subjects on clinical resources. Use DocumentReference to identify the retained
source, with a local attachment URL. Give each Bundle entry a UUID URN `fullUrl`
and use that exact URN for references to it from other entries, as in the example.
Preserve exact decimals, comparators,
original units, source status, partial dates and uncertainty. Do not guess codes,
timezones or clinical meaning. Follow the [terminology
guide](../docs/terminology.md): search the
bundled English/PT-BR vocabulary and Janusmed aliases automatically, or use an
explicitly selected full pinned package, across translations and useful language
variants. Do not require a language choice or use it to infer numeric/date locale.
You may propose new mappings supported by source citations for specimen,
property, timing, scale and relevant method. Abstain on missing or ambiguous
context. Preserve `code.text` and original quantity fields; add supported native
FHIR LOINC Coding with version and UCUM system/code. Distinguish source-provided
coding from proposals in evidence, retaining catalog pins, alternatives and check
results. Local checking cannot establish clinical equivalence. Separate clinical
source status from human approval.

If I supply a confirmed profile.fhir.json, reuse its Patient ID and confirmed
details. For PDFs, report unreadable pages rather than guessing their contents.
Keep personal notes labeled as user-reported statements, not confirmed diagnoses.

Return the complete draft JSON, a readable citation list mapping every clinical
field to source filename, page/row/pointer and exact quote, and a review note with
all unresolved questions. Label generated IDs and reference construction. Describe
any normalization such as decimal comma to decimal point. Follow the supplied
example; machine-readable evidence is optional. If I authorize a new destination,
save bundle.fhir.json, evidence.md and review.md there without overwriting files;
otherwise return their contents for me to save. Source attachment paths must
resolve from the Bundle's location and remain valid if I copy the reviewed import
to its accepted location. No experimental CLI, archive initialization or rendered
prompts are required.
Terminology proposals retain their vocabulary/catalog pins and supporting evidence.
At setup, offer once to use the supplied vocabulary, import an existing ZIP or
download full LOINC after account creation; honor an existing choice. Declining
is fully supported, including uncoded source text outside coverage. Never ask
for a password in chat; account acquisition is separate from offline extraction.
I may review proposed new aliases or mappings with the draft; they do not become
shared repository vocabulary automatically.

Request explicit human review of identity, each value/comparator/unit/date and
citation and any mapping proposal/evidence before acceptance. Leave the source
and accepted records unchanged.
If the evidence cannot support a fact, omit it and flag the gap. No medical advice.
