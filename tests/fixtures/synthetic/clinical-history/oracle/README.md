# Independent history oracle

CC0-1.0 invented data only. `source.json` was manually written as short source
sentences. `candidate-resources.json` was separately written as a proposed FHIR
representation. The independently specified
[expected facts](../../../expected/clinical-history-facts.json) are never used to
construct the source or clinical candidate fields. Runtime setup assigns only
local identity, IDs, source attachment bookkeeping and evidence links.

This modest corpus retains eight representative assertions, one per family,
grounded in the independent Task13 review: reported evening use with unknown
adherence, an order with unknown actual use, suspected onset versus recording
time, explicit negative allergy, a year-only vaccination with unknown series,
not-done procedure, cancelled encounter with unknown period, and a mother's
history with exact age and false contributed-to-death. ImagingStudy remains
source only with an explicit review limitation. Decimal tokens are intentional.
The adjacent manifest records provenance, source digest and test obligations.

`tests/test_clinical_history_oracle.py` consumes these files through public
validation, preparation, review, publication, reopen, history, timeline and exact
revision resolution APIs. Expected facts are checked before preparation, in the
review view, and after publication/query. Every family also has one clinical
leaf whose evidence is removed or forged as generated evidence; each starts
from a nonempty error-free baseline and asserts its specific rejection.

The existing 17-resource family fixtures and their generated source comparisons
remain useful storage coverage. This independent oracle guards selected source
meaning, unknowns and omissions without duplicating that suite. Pre-authored
candidates and synthetic human decisions establish bounded toolkit behavior;
no extraction engine/model, clinical truth, human review effectiveness, or
complete FHIR/terminology conformance is qualified here. Quote consistency alone
cannot prove that a proposed clinical value correctly interprets a source.
