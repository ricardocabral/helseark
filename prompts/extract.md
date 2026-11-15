# Extract records — copy this prompt

Ask me for one person's stable local ID, their identity cues, and the source files
I authorize you to read, if I have not supplied them. Use the Helseark agent
instructions and FHIR R4 schema supplied with this prompt. Stop if identity is
missing or inconsistent. Read no other person's records.

Create a draft FHIR R4 collection Bundle with an explicit Patient and explicit
subjects on clinical resources. Use DocumentReference to identify the retained
source, with a local attachment URL. Preserve exact decimals, comparators,
original units, source status, partial dates and uncertainty. Do not infer codes,
timezones or clinical meaning. Separate clinical source status from human approval.

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
to its accepted location. No CLI commands, hashes, archive initialization, pins
or rendered prompts are required.

Request explicit human review of identity, each value/comparator/unit/date and
citation before acceptance. Leave the source and accepted records unchanged.
If the evidence cannot support a fact, omit it and flag the gap. No medical advice.
