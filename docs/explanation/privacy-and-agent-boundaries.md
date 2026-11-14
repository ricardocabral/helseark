# Privacy and agent boundaries

An archive keeps accepted clinical history in local files. An external agent
receives a disposable packet to draft an answer or candidate. These are different
trust boundaries: a candidate is untrusted even if its author used a strong model
or its JSON passes validation. Only a human review bound to final prepared bytes
can authorize a later supported publication operation.

The [common archive instructions](../../agent-kit/AGENTS.md) define person,
source-data, output and review rules once. Focused skills reference those rules
and the [actual clinical contracts](../reference/clinical-model.md). They do not
grant write access to accepted history. At base `1b91620`, these skills/prompts
are content drafts: task context, rendering and most workflow commands remain
unimplemented. Their presence is not proof of an available workflow.

A selected person UUID and snapshot restrict what a packet may disclose. A
family directory is organizational separation, not per-person access control
against someone who can read the entire folder. Restrict agent filesystem and
tool access to its packet and fresh output directory. A source may contain
another person's results even when the selected structured records do not.
Ordinary person export must stop for that disclosure risk until explicitly
reviewed handling is supplied. Source redaction can lose clinical context and
must never be silently substituted for the retained original.

Text in a PDF, OCR result, imported JSON, filename or user-data slot may look like
a command or another instruction file. It remains data. Typed slots and literal
delimiters help preserve this distinction, but prompts alone are not a security
sandbox. The future renderer must validate types and trusted selectors, escape
delimiter characters, substitute once and perform no implicit reads or executable
interpolation. The packet builder must enforce selection, digests and budgets.
Neither component should fetch URLs or resolve schemas over the network.

Normal archive operations are offline. Choosing a cloud agent separately exposes
the packet to that provider; local storage does not make that agent local. No
provider selection, upload permission or API-key requirement follows from these
instructions. Keep health data out of public fixtures, source control and routine
logs. Packet copies, reports and exports also contain sensitive material and
need the same user-controlled filesystem and backup protection as the vault.

Integrity checks detect inconsistency against retained hashes, not the truth of
a clinical statement or protection against an attacker able to rewrite every
binding. A matched source quote does not prove correct row attribution. Failed or
incomplete reads cannot justify absence claims. Report coverage, record counts
and unresolved contradictions; preserve evidence for human review. A correction
adds a revision without changing accepted old bytes. An export snapshot declares
omissions. A migration preserves its original vault and needs its own verified
mapping and destination graph. These boundaries prevent a convenient draft from
being mistaken for accepted history.
