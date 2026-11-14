# Helseark

A local personal and family health archive toolkit, under development.

Canonical clinical records use FHIR R4, with retained source evidence, explicit
human review, and immutable history. Normal archive operations are offline.
This staged branch supports text-PDF intake, prepared human-controlled review and
publication, accepted queries, integrity diagnostics, backup/restore and restricted
person exports. It inherits clinical bugs pending corrected-foundation integration;
no medical accuracy or production qualification is claimed.

[Learn with the synthetic import/query/restore lesson](docs/tutorials/first-archive.md),
[accomplish a task](docs/index.md#accomplish-a-task),
[look up CLI and API contracts](docs/index.md#look-up-facts), or
[understand the design](docs/index.md#understand).
The [documentation index](docs/index.md) describes supported scope and limitations.
The lesson uses a supplied candidate and explicit synthetic review; genuine
[external-agent intake](docs/how-to/import-report.md) has separate host restrictions.
