# Propose a correction — copy this prompt

Ask me for one person's stable local ID, the exact record file/revision and field
to correct, the reason, and supporting source or explicitly attributed user
statement if I have not supplied them. Use the supplied Helseark agent
instructions. Stop on identity conflicts or an unclear target.

Read only the selected record and authorized evidence. Return a complete separate
FHIR R4 draft of the corrected resource, a field-by-field before/after list,
reason, citations (filename, page/row/pointer, exact quote), and unresolved issues.
Keep exact decimal scale, comparator, unit, date precision and uncertainty. Label
user assertions as such instead of inventing source support. Do not silently
change source-reported clinical status or guess codes or clinical meaning.
For terminology enrichment use the [terminology guide](../docs/terminology.md)
and pinned local helper. You may propose a new mapping with source citations for
every relevant axis, or reuse a human-approved mapping only where its stated
conditions match.
Search available translations and language variants automatically; language alone
establishes neither equivalence nor numeric/date locale. Retain source labels,
units and values, catalog pins, alternatives, check results and a clear distinction
between source coding and proposed coding. Abstain on missing or ambiguous context.
Include the mapping proposal and evidence in the exact files reviewed.

Identify the prior version in the review note and describe affected references
for human review. Do not overwrite the original, rewrite its evidence or approval,
update other resources automatically, or mark the proposal accepted. Require a
human to record reviewer, date, exact proposed file/revision, decision and remaining
concerns before retaining it as a new accepted revision. Keep the old version.
No CLI, hash or protocol setup is needed. No medical advice.
