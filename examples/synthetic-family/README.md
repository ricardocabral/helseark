# Executable synthetic family example

All identities and values are invented. Generated data is CC0-1.0; the generator
is Apache-2.0. Predetermined candidates and illustrative review decisions measure
workflow behavior, not model accuracy or medical correctness. Never run this
review automation on real health data.

Install this distribution with its pinned `pdf` extra and run from a clean
working directory, choosing an absent output directory on a local filesystem:

```sh
python /PATH/TO/ENV/share/helseark/examples/synthetic-family/generate.py \
  /same-disk/synthetic-family --synthetic-review-decisions
```

With a source checkout, the equivalent is `python examples/synthetic-family/generate.py
/same-disk/synthetic-family --synthetic-review-decisions` using the project Python
environment. The installed run uses the installed kit and supplied PDF/candidate;
no model, network, repository or original runtime cache is required.

The generator creates two equal-name people with separate UUIDs and two accepted
Observations each. It retains the original source PDF and extraction evidence,
explicit person assignments, inspected review views and separately written
synthetic decision files. Each import/correction first demonstrates that commit
without review is rejected. It corrects an invented method error to `M1`, checks
clinical `final`, exact `<0.050 mg/L` and month precision, reads the unchanged old
revision and native revision Provenance, then backs up, removes one person with
an approved digest, restores quarantine, and verifies an independent backup
restore. The unselected person's bytes must remain equal throughout.

Read `OUTPUT/result.json`: it contains actual CLI commands/exits, nonzero doctor
counts, source/history file hashes and sizes, both restored inventories, and
per-case checked/not-checked outcomes. UUIDs, timestamps and resulting digests
vary per run. Expected stable facts are two clinically nonempty people, two
initial measurements each, `0.050` preserved, zero other-person byte changes,
nonempty accepted history and zero doctor issues. `vault/` and `restored/` are
complete readable folder archives; `backup/`, `quarantine/`, decisions and plans
remain available for inspection. Quarantine is recoverable removal, not secure
deletion. Output creation fails if the requested directory already exists.

The unchanged independent `expected-facts.json` records five semantic cases.
`tests/family_oracle.py` compares their facts with observed correction/removal
behavior and can emit per-case coverage via `HELSEARK_FAMILY_LEDGER_RESULTS`.
The generator checks transcription and removal; laboratory amendment, error-entry
and cancelled-report semantics are explicitly not checked by this lesson and are
covered by the separate correction tests. Provenance CI checks declarations and
hashes only; it does not certify clinical correctness or absence of real data.

See the [first archive tutorial](../../docs/tutorials/first-archive.md) and
[family removal guide](../../docs/how-to/manage-family.md). The complete tutorial
and installed/restored onboarding are maintained separately from this example.
