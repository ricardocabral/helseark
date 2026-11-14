# Synthetic profile examples

All people, actors, dates, values and codes here are invented. Original fixture
content is CC0-1.0. No real health data or terminology package is included.

`collection.json` contains 19 archive-shaped resource revisions (one Patient,
14 Observations, one report, specimen, document and Provenance). Its local
version references illustrate immutable accepted links, with versionless Patient
subject references. It is a schema-test collection, not a prepared proposal,
validator-context export or importable vault. A full-validator context must
rewrite references to revision URNs with a reversible closure map first.
The repeated `a` attachment digest is an explicitly synthetic placeholder:
there is no corresponding retained asset, source receipt, evidence envelope or
review receipt. Therefore this collection must not pass archive acceptance.

`expected-facts.json` is hand-authored independently of any importer and captures
native results and context. The trace source reads `<0,0500 mg/L`, with an adult
female interval printed as “less than 5”; the local clock reads `09:15` without
a zone and requires review. Partial dates, comparators, scale and text intervals
are preserved. Other cases cover long decimals, negative and source-coded
results, absence/not-performed, ratio/range, blood-pressure components,
method-specific panel children, nested microbiology narrative and amended,
cancelled and entered-in-error statuses. The synthetic code system uses the
reserved `.invalid` domain and must never be fetched or treated as verified.

Focused tests mutate copies in memory to demonstrate genuine upstream schema
failures and genuine schema successes for invalid profile/graph cases. A
wrong-person subject, missing subject/status, two values, value plus absence,
and comparator on a reference-range bound illustrate required runtime checks;
the tests never label these mutations semantically valid.

`semantic-cases.json` adds 37 standalone schema probes. Each contains a real
resource, the expected upstream `schemaValid` outcome, and an **unexecuted**
`expectedBaseline`/`unexecutedObligation` for the runtime worker. `supported-shape`
means an intended native representation, not acceptance; `reject` records a
required baseline failure; `requires-context` records missing graph context.
The tests execute the real retained schema on these resources. They do not
execute those baseline verdicts, evaluate FHIRPath, authenticate source assertions
or establish targetProfile conformance. These are schema probes, not an archive
or a full-validator context Bundle. Repeated resource IDs denote independent
probes and must not be combined into one candidate inventory.

Cases preserve unknown status with no value, text-only absence, narrative-only
report and a source-attributed lab narrative without inferring a diagnosis.
False, zero and time/dateTime/Period choices remain native. derivedFrom examples
name exact Observation and DocumentReference revisions in `collection.json`;
the correction Provenance adds role=revision for a deliberately absent prior
report revision and keeps role=source separate. Runtime must supply and verify
that prior revision, supersession and patient ownership. The revision-only
negative case cannot satisfy the required source entity. No new clinical
resource family is introduced.

Negative probes expose component choice/absence, obs-7, qty-3, inverted Range,
SampledData, unsupported derivedFrom and inherited focus/device references.
Eight separate comparator probes cover referenceRange.low/high, valueRange.low/
high and both component equivalents. They all pass schema, leaving mandatory
SimpleQuantity resolution/enforcement to runtime. Existing comparator-bearing
result Quantity and textual intervals remain positive preservation examples.
Extension-only subject reference, status, actor identifier and attachment title/
media type/URL probes also pass schema: primitive cardinality is not proof of a
literal value. Runtime must enforce these literal requirements. Offsetless full
dateTime is the single schema rejection in this file; honest partial dates and
raw missing-zone text remain supported in the original collection.

Any `syntheticSourceText` is hand-authored explanatory source text, with no
retained source hash, evidence pointer or review. No source extraction or evidence
acceptance has been tested. Runtime must validate the full supported baseline;
Task 10 must separately qualify actual invariant execution, terminology and
snapshot generation offline. Until then, those families are `not-checked` here.
