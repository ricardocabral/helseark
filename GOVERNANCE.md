# Project governance

Helseark is currently coordinated by the
[repository owner, ricardocabral](https://github.com/ricardocabral).
There is no separate foundation, steering committee or guaranteed support team.
The owner is responsible for release, licensing and repository visibility decisions.
CODEOWNERS routes reviews; it does not by itself enforce approval or grant merge
permission. The [conduct policy](CODE_OF_CONDUCT.md) applies to maintainers too.

Contributors propose focused changes through issues and pull requests. Maintainers
coordinate overlapping work and document compatibility/privacy decisions in the
relevant public reference or issue. Contributors do not need private plans to
understand an assigned issue. Contract changes require explicit compatibility
review; accepted archive history cannot be reinterpreted silently.

An independent reviewer checks each implementation before integration. The
coordinator resolves findings, records reasons for declined suggestions, confirms
CI and integrates approved work. Agents do not merge without explicit owner
authorization. No automatic merge authority follows from a plan or green tests.

Maintainer roles and review access are granted by the owner based on demonstrated
contributions and responsible handling of sensitive-data boundaries. Discuss
technical disagreements in the relevant issue with reproducible evidence; the
owner decides unresolved scope or release questions. Use private channels for
security or conduct reports. A private alternate for owner-related conduct
concerns is still a [public-launch requirement](docs/maintainers/releasing.md).

The [contribution guide](CONTRIBUTING.md), [coding guide](docs/development/coding-guide.md)
and [release checklist](docs/maintainers/releasing.md) define the working process.
