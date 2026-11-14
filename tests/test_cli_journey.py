import json
import os
import subprocess
import sys

from helseark.archive import open_vault, resolve
from helseark.contracts import ResourceRef


def run(*args, env=None):
    return subprocess.run([sys.executable, "-m", "helseark.cli", *map(str, args)], capture_output=True, env=env)


def test_init_and_explicit_person_journey(tmp_path):
    root = tmp_path / "family"
    initialized = run("init", root, "--json")
    assert initialized.returncode == 0, initialized.stderr
    assert json.loads(initialized.stdout)["vaultId"]
    created = run("--vault", root, "person", "add", "--name", "Alex Example", "--birth-date", "1990", "--json")
    assert created.returncode == 0, created.stderr
    person = json.loads(created.stdout)["personId"]
    assert resolve(open_vault(root), person, ResourceRef("Patient", person))["birthDate"] == "1990"
    assert initialized.stderr == created.stderr == b""
    other = run("person", "add", "--name", "Alex Example", "--json", env={**os.environ, "HELSEARK_VAULT": str(root)})
    assert other.returncode == 0
    assert json.loads(other.stdout)["personId"] != person


def test_errors_are_safe_and_exit_codes_distinguish_versions(tmp_path):
    absent = run("person", "add", "--name", "PRIVATE NAME", "--json", env={k:v for k,v in os.environ.items() if k != "HELSEARK_VAULT"})
    assert absent.returncode == 2
    assert absent.stdout == b""
    assert b"PRIVATE" not in absent.stderr
    root = tmp_path / "vault"
    assert run("init", root).returncode == 0
    assert run("init", root).returncode == 2
    invalid = run("--vault", root, "person", "add", "--name", "PRIVATE NAME", "--birth-date", "no", "--json")
    assert invalid.returncode == 2
    assert b"PRIVATE" not in invalid.stderr
    config = json.loads((root / "vault.json").read_text())
    config["fhirVersion"] = "5.0.0"
    (root / "vault.json").write_text(json.dumps(config))
    incompatible = run("--vault", root, "person", "add", "--name", "Alex")
    assert incompatible.returncode == 6
    assert b"UNSUPPORTED_VERSION" in incompatible.stderr


import pytest
from helseark.archive import init_vault, add_person
from helseark.contracts import PersonDraft


@pytest.mark.parametrize('filename', ['vault.json', 'change.json', 'proposal.json', 'evidence.json', 'review.json', 'validation.json', 'resource'])
@pytest.mark.parametrize('raw', [b'{"PRIVATE RECORD":', b'{"x":1,"x":2}'])
def test_corrupt_stored_json_is_exit5(tmp_path, filename, raw):
    vault = init_vault(tmp_path / 'PRIVATE ROOT')
    person = add_person(vault, PersonDraft('PRIVATE NAME'))
    directory = next((vault.root / 'people' / person / 'accepted').iterdir())
    path = vault.root / filename if filename == 'vault.json' else directory / filename
    if filename == 'resource':
        path = next((directory / 'resources').iterdir())
    path.write_bytes(raw)
    result = run('--vault', vault.root, 'person', 'add', '--name', 'PRIVATE NAME', '--json')
    assert result.returncode == 5, result.stderr
    assert result.stdout == b''
    assert b'PRIVATE' not in result.stderr
    assert json.loads(result.stderr)['details']['path'] == path.relative_to(vault.root).as_posix()


@pytest.mark.parametrize('filename,pin', [(name, 'contractVersion') for name in ('change.json', 'proposal.json', 'evidence.json', 'review.json')] + [(name, pin) for name in ('change.json', 'proposal.json') for pin in ('fhirVersion', 'profileVersion', 'serializationVersion', 'archiveFormatVersion', 'agentKitVersion', 'agentKitLockSha256', 'definitionLockSha256')])
def test_unsupported_genesis_envelope_versions_are_exit6(tmp_path, filename, pin):
    vault = init_vault(tmp_path / 'vault')
    person = add_person(vault, PersonDraft('Synthetic'))
    directory = next((vault.root / 'people' / person / 'accepted').iterdir())
    path = directory / filename
    value = json.loads(path.read_bytes())
    if pin == 'contractVersion':
        value[pin] = 'future'
    else:
        value['versions'][pin] = 'future'
    path.write_text(json.dumps(value))
    result = run('--vault', vault.root, 'person', 'add', '--name', 'PRIVATE NAME', '--json')
    assert result.returncode == 6, result.stderr
    assert result.stdout == b'' and b'PRIVATE' not in result.stderr
