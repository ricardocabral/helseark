# Why the archive uses FHIR and files

Helseark's clinical authority is the immutable FHIR R4 resource revision. Evidence,
review and change envelopes describe how that revision entered the archive; they
do not keep a second normalized measurement. A query row is a projection and can
be rebuilt from accepted files. A PDF is retained binary evidence, so a vault
containing PDFs is not text-only.

FHIR supplies native distinctions between an Observation, a report, a specimen
and a document. Local profiles bound what this toolkit interprets. Preserving a
source label without inventing a terminology code loses less meaning than guessing
an equivalence. Decimal tokens, comparison signs, partial dates, units and ranges
belong to each measurement, rather than to a global lab-name catalog.

The publication path is source → untrusted candidate → prepared final bytes →
explicit review receipt → accepted change. A local writer lock, staging and atomic
rename make complete changes visible together on qualified local filesystems.
Each change inventories payload bytes and its predecessor. These hashes detect
inconsistency, not authenticity against an actor who can replace every binding.
There is no server, required database or embedded model runtime.

Each person has an independent Patient ID, assets and chain. Separate copies of
identical source bytes simplify person boundaries. Family organization does not
provide OS access control. Read [privacy](privacy-and-agent-boundaries.md) before
giving an agent filesystem access, and [archive format](../reference/archive-format.md)
for exact contracts. Filesystem durability beyond tested process-crash boundaries,
medical correctness and general FHIR conformance are not established.
