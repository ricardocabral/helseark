# Retained pre-renderer protocol fixture

These four instruction/contract files are exact repository bytes from commit
`b56c767376728e57f2c0b8583e6feffe05409929`, recorded in provenance.json.
They contain no health data. They retain the repository's Apache-2.0 license;
they are not new CC0 clinical fixtures or a second production manifest.

The compatibility test pins them before creating any synthetic accepted history,
then verifies the new reader without rewriting those accepted bytes. New runtime
contracts must not replace the retained schemas to make that test pass.
