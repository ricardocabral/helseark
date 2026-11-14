# Synthetic examples and evaluation handoff

Use the raw [workflow inputs](../../tests/fixtures/synthetic/agent-workflows/README.md)
with the independent [expected facts](../../tests/fixtures/expected/agent-workflows/).
All health content is invented. These are not actual model outputs, a supported
vault or a successful end-to-end journey. Original synthetic data is CC0.

An evaluator gives a fresh model only its documented entry point and bounded
raw packet, reserving the expected facts for scoring. Record runtime/model,
kit/prompt/skill digests, input files/bytes, record counts, discovery attempts,
write-scope violations, factual/evidence omissions and stop reason. Compare an
actual baseline with actual rendered entry-point execution when available.
No such evaluation has been run for this content slice.

`extraction-fragment.json` illustrates only the expected clinical value subtree
for `<0,05`; it is not a Bundle, complete evidence map or accepted record.
`query-answer-excerpt.md` illustrates citations and the absence distinction using
pre-authored fixture assertions; it does not claim a live query was performed.
Candidate construction must use pinned full contracts and retained source hashes,
not copy these fragments into an accepted directory.

Pending integration checks must render through the real context/renderer, create
real synthetic source assets and histories, validate emitted candidate/evidence,
resolve all query citations and ensure accepted bytes remain unchanged. Exercise
adversarial delimiter/slot text, wrong-person data, stale heads, omitted facts,
unsafe outputs, unavailable commands and continuation. Markdown/frontmatter/link
checks establish content hygiene only, not agent behavior or extraction quality.
