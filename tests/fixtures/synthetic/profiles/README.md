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
