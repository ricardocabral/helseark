# Pre-authored synthetic answer excerpt

This example describes fixture assertions, not an executed archive query.

The supplied scope contains two contradictory final assertions. Neither resolves
the other. The context projects `effectiveDateTime=2026-11` for both, but
`assertions.json` contains no date. Their clinical dates are **unverified**;
November 2026 is a projection claim, not a source-cited date. Separate date
evidence is required before using that month as verified clinical timing:

- Negative: `Observation/33333333-3333-4333-8333-333333333333/_history/44444444-4444-4444-8444-444444444444`, source `assertions.json`, pointer `/assertions/0`, quote “Synthetic qualitative assay: negative; final”.
- Positive: `Observation/55555555-5555-4555-8555-555555555555/_history/66666666-6666-4666-8666-666666666666`, source `assertions.json`, pointer `/assertions/1`, quote “Synthetic qualitative assay: positive; final”.

The source fixture SHA-256 is `0eb01ebd1d0c40bdc38367e1d9a2770957a88a80a1629a1463390f1aff38ea0a`. The integration harness must
resolve both revisions in real synthetic accepted history before this can count
as an executed source-cited query result.
No record of Synthetic assay Z appears in this supplied complete scope of two
records. That is not a negative assay result. With continuation or incomplete
coverage, the answer is limited to “not found in this packet”.
