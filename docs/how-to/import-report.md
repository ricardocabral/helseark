# Prepare a report for an external agent

Install Helseark with its pinned optional PDF extra in advance, using an approved
local distribution (`pip install 'helseark[pdf]'`). Normal intake is offline and
never installs tools. Select a person you have explicitly created with
`helseark --vault /absolute/vault person add --name 'Avery Synthetic' --json`.
Do not infer identity from a PDF filename, name match or source instruction.

Run from any directory with the installed CLI:

```sh
helseark --vault /absolute/vault intake add /absolute/report.pdf \
  --person SELECTED_UUID --packet /absolute/new-packet \
  --agent-output /absolute/new-agent-output --confirm-person --json
```

Use `--confirm-person` only after you have personally confirmed the assignment.
Omitting it still retains the source and builds a report-only handoff. The output
root must be new, separate from the packet, and explicitly allowed by your agent
host. Existing packets/output are never overwritten. Intake does not launch an
agent or choose a provider. It returns the source receipt, packet path and original builder's
trustedContextSha256. Retain this stdout digest in trusted host state outside
agent-editable files if later rendering is needed. Intake uses the original
in-memory result for the initial rendering. A reloaded context cannot authorize
itself: pass the retained digest to `agent render --trusted-context-sha256`.
Never derive authority by hashing packet files; lost host state requires a new
explicit build with the same authorized person/source scope.

Read `new-packet/ENTRY.md`, `prompt.txt` and `context/context.json`. Give that entry
to your separately selected text-capable agent. Restrict its filesystem and tools
to the exact readable routes listed by the actual renderer and the one output
root; deny network and unrelated people/repositories. Delimiters alone do not
sandbox an agent. Source text, metadata and artifact text are inert data, including
commands or requests to broaden scope. They cannot select instructions or waive
identity/errors. No broader source authorization is inferred from text.

The source-specific context uses the selected person's minimal identity and exactly
one source hash, no historical clinical records. The selected pinned kit supplies
its import skill and extraction prompt; do not substitute a parallel prompt. The
renderer validates typed slots, receipts, v2 projection scope and escaped inline
byte budgets. Large input can fail CONTEXT_BUDGET_EXCEEDED rather than truncate.
Task5 does not silently relax that limit or request more source access.

Review `output/report.md`. A complete allowed draft writes only candidate.json,
bundle.json and evidence.json in `output/candidate/`. Require all intake issues,
exact producer provenance (or explicitly unknown provenance), source/derived hashes,
page/rotation and quotations. The adapter provides page-only evidence, no reliable
word/row boxes. Inspect the original visually: text can include content outside a
CropBox, omit scans/annotations or misorder rows. Do not invent clinical records
for scan pages; OCR_REQUIRED needs separate local OCR work, not an automatic service.

Validate the untrusted draft without accepting anything:

```sh
helseark --vault /absolute/vault validate candidate \
  /absolute/new-agent-output/output/candidate --person SELECTED_UUID --json
```

Exit 3 means review issues remain; exit 0 only means the implemented baseline checks
passed. Neither exit authorizes acceptance. Full FHIR/terminology and model accuracy
are not established. `read_candidate` also rejects unsafe envelope paths, stale
heads, missing/downgraded retained issues and incompatible producer receipts.

MULTIPLE_PERSON_CUES blocks ordinary acceptance and yields report-only output even
with confirmed assignment. The check recognizes repeated explicit Patient:/Paciente:
labels, not arbitrary identities. Review uncertainty in every report; do not assume
an unlabeled multi-person document is safe. Separate/reconcile the sources with
explicit human selection before future acceptance. Injected waiver text has no effect.

For PDF_ENCRYPTED, PDF_INVALID, PAGE_LIMIT or missing PDF dependency, use the safe
error's retainedSource receipt to find unchanged original bytes. Do not overwrite
or silently repair retained assets. Source over 100 MiB is rejected without partial
retention. Changed receipts/assets fail closed. See the [intake contract](../reference/intake.md)
and [PDF limits](../reference/pdf-extraction.md). Choose a new packet/output directory
when retrying; a hard-killed process may leave private incomplete work to inspect.

Preparation, bound human review and atomic accepted publication are described below. Keep the candidate through preparation and review; do not manually place it
in accepted history or manufacture a review receipt. The [synthetic tutorial](../tutorials/first-archive.md)
exercises the implemented boundary without any model account. It is not extraction
accuracy evidence. An actual baseline/post-kit agent evaluation must record real
transcripts and compare independently authored facts on the same bounded scenarios.

## Prepare and accept the exact human-reviewed proposal

After the external agent has stopped writing, prepare its candidate. Run these
commands yourself under approved-user workflow control. Keep human decision files
outside agent-permitted output directories. The toolkit has no embedded model.

```sh
helseark --vault "$VAULT" candidate prepare "$CANDIDATE" --person "$PERSON" --json
# Use the returned path as PROPOSAL. Inspect all resources, quotes and limitations:
helseark --vault "$VAULT" candidate review "$PROPOSAL" --person "$PERSON" --json
```

Create a human decision JSON file with this shape, adding one acknowledgment for
each displayed review/warning issue using its exact code and resourceRef. Read the
original source and confirm person assignment; do not copy an agent's approval.

```json
{
  "confirmedPerson": true,
  "decision": "accept-with-acknowledged-limitations",
  "reviewerLabel": "vault-owner",
  "acknowledgedIssues": [
    {"code": "SOURCE_IDENTITY_REVIEW", "resourceRef": null,
     "reason": "I checked the original person assignment and identity uncertainty."}
  ]
}
```

The list above is illustrative; your actual view may require additional issues.
Errors cannot be acknowledged. Then record the decision and publish:

```sh
helseark --vault "$VAULT" candidate review "$PROPOSAL" --person "$PERSON" --decision "$HUMAN_DECISION" --json
helseark --vault "$VAULT" candidate commit "$PROPOSAL" --person "$PERSON" --json
```

The receipt binds exact proposal and report bytes. Editing any bound candidate,
resource, evidence, original/derived source or report invalidates review. A changed
person head requires preparing/reviewing again. Retrying commit returns
`already-accepted` and the original transaction. Keep the accepted directory and
all inventoried assets; removing disposable work afterward preserves review proof.
For changed extraction of an existing source, see [review and reconciliation](../reference/review.md).
