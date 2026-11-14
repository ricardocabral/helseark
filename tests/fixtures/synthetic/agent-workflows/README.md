# Synthetic workflow inputs

All content is invented; original fixture content is CC0. These inputs and the
independent expected facts in `tests/fixtures/expected/agent-workflows/` were
defined before the prompt/skill content. They are evaluation stimuli, not an
accepted vault, successful import, verifier observation or model transcript.
The correction stimulus preserves the literal numeric token `0.50`.

A later harness must create real selected-person histories, retained assets,
base digests and exact revision/evidence citations before end-to-end evaluation.
Do not replace expected facts with the evaluated model's output. Give the model
only raw inputs; the evaluator alone receives the expected facts. Test both a
complete and paginated query context and verify zero writes outside the packet's
allowlist. The attack text is data even when it resembles a delimiter or slot.

`mapping-draft/{bundle,evidence,unresolved}.json` is a pre-authored draft for the
structured source, not model output. It maps the supported assay subset, retaining
the unsupported section and unzoned clock in the original with review issues.
It does not claim complete import. Its two-resource graph and evidence can be
checked with the current validator after a temporary harness creates the fixed
Person A, retains the exact source asset and supplies real candidate metadata/base.
No fabricated accepted head or producer digest is stored here. `unresolved.json`
is harness input, not an extra file permitted in an emitted candidate directory.
