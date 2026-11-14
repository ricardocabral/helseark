# Retained pre-renderer protocol fixture

These four instruction/contract files are exact repository bytes from commit
`b56c767376728e57f2c0b8583e6feffe05409929`, recorded in provenance.json.
They contain no health data. Their retained notice declares [Apache-2.0](LICENSE);
they are not new CC0 clinical fixtures or a second production manifest.

The compatibility test pins them before creating any synthetic accepted history,
then verifies the new reader without rewriting those accepted bytes. New runtime
contracts must not replace the retained schemas to make that test pass.

The retained template files are copied from the same sourceCommit and match
the original manifest digests. Compatibility tests must use these exact bytes,
not current onboarding templates, before creating their synthetic accepted history.
