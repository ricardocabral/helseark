# Provenance, review and immutable revisions

A logical resource ID identifies a record across revisions. Its meta.versionId
identifies exact accepted bytes. Historical references include that version so an
old report can continue referring to the old result even when a newer result exists.
A Head identifies a selected person's accepted snapshot by sequence, transaction
and change digest; it is not a household-wide timestamp.

DocumentReference describes retained source assets. Field evidence binds exact
resource revisions and JSON Pointers to source hashes, quotations and locators.
PDF text extraction has its own retained bytes and receipt. Generated IDs and
bookkeeping use generated evidence rather than invented source quotes. Matching
a quote verifies text consistency; it cannot prove that the right row or person
was selected. FHIR Provenance records derivation without replacing field evidence.

Preparation allocates final revisions and inventories the proposed content. Review
binds those bytes, validation and base. A changed candidate, receipt or base cannot
authorize different publication. Local reviewer labels are not signatures or proof
of human identity. Clinical status such as final is a source fact, independent of
whether a user has accepted the import.

An exact accepted retry returns the existing transaction. Source digest equality
alone does not mean two assertions are medically equivalent. Re-extraction needs
explicit intent and correspondence; omitted facts remain in history. This branch
binds exact issue acknowledgments and pinned prior-resource comparisons; its
deterministic lesson is not a clinical qualification.

A correction adds revisions; recoverable removal, laboratory amendment and archive
migration have different meanings. Correction uses the same human review path.
Removal quarantines selected paths while disclosing retained shared metadata;
restore recovers those paths. Migration creates a separate verified vault. See [review](../reference/review.md), [queries](../how-to/query-history.md)
and [evolution](evolution.md).
