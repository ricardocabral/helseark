# Query records — copy this prompt

Ask me for one person's stable local ID, my question, the records and source
citations I authorize you to read, and any date range if I have not supplied them.
Use the supplied Helseark agent instructions. Stop on ambiguous identity.

Answer only from that person's supplied records. Show the resource ID and exact
file/revision, FHIR field, source filename and page/row/pointer for every factual
answer. Preserve exact decimals, bounds, units, source status and date precision.
For each match state uncertainty, conflicting records, and whether its date is
inside, overlaps, or cannot be placed within the requested range. Keep unknown
dates visible rather than silently assigning or excluding them.

Use the [terminology guide](../docs/terminology.md) for automatic multilingual
search expansion with the bundled English/PT-BR vocabulary and Janusmed aliases,
or an explicitly selected full pinned catalog. No account or download is required.
Honor the existing terminology preference; acquisition/setup is a separate task.
Report the terms, mappings and files searched;
search expansion does not authorize editing records or declaring equivalence.
Keep grouping for charts or retrieval separate from observation mappings. Preserve
specimen, original dates and unknown dates, bounds, duplicates and method
differences; shared labels or codes alone do not establish comparability.

Do not convert units, invent codes, compare incomparable results, infer a diagnosis,
or interpret a missing record as proof something did not occur. State what files
were searched and what was unavailable. Return a readable answer and unresolved
questions only; do not edit any records. No CLI, hash or protocol setup is needed.
No medical advice.
