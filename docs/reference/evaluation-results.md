# Historical external-agent observations

This is a distributable summary of earlier maintainer observations, read on
2026-11-14 from the retained Task5 corrected evaluation and postmerge reports.
No model was run for the documentation foundation. These measurements do not
qualify this branch's inherited publication/query behavior.

The evaluated source was [7221cf3](https://github.com/ricardocabral/helseark/commit/7221cf30d84f6339467493ba91e1b1e17db3e7f7),
whose tree was later matched to the Task5 merged runtime. The six actual trials
used gpt-6.1-sol at medium reasoning: five unchanged original scenarios and one
separate supplementary distinct-result scenario. Four trials stopped without
candidates: injection, scan, mixed-person cues and rotated report lacking status.
These are observed scope/uncertainty stops, not successful clinical extractions.

The original clinical trial produced 2 Observations in 4 resources; independent
Decimal-parsed scoring found exact 0.050, comparator <, mg/L, M1, printed range,
month precision, final status and “not detected”; 22 source quotes resolved.
A separate supplementary trial produced 2 Observations in 3 resources, preserving
2.700, comparator >, mg/L, month/final and a reactive screening result;
15 source quotes resolved. Both CLI candidate validations returned exit 3 with
zero error issues and mandatory review. No clinical accepted transactions were
created by these trials. Original ambiguous qualitative attribution remained
unresolved; matching tokens/quotes is not proof of independent row attribution.

For the four stopping trials, an explicit receipt audit found 57 input receipts
and 8,439,991 receipt bytes summed per trial, with no receipt mismatches. This
is partial receipt accounting, not complete implicit I/O telemetry. External
process-skill reads were disclosed. No efficiency improvement or causal claim
from the small paired sample is justified. Earlier misses were retained rather
than erased by the supplementary case.

The historical [Task5 CI](https://github.com/ricardocabral/helseark/actions/runs/43640690345)
passed 684 tests per OS at the reported 2026-11-14 21:26 UTC read. That is historical
Task5 evidence, not a fresh run or approval of this documentation branch.
Terminology, full FHIR conformance, generic provider coverage, visual completeness,
medical correctness and production release readiness are not established.
The deterministic [first lesson](../tutorials/first-archive.md) is a different test.
