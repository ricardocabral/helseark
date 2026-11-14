from pathlib import Path
import pytest
from helseark.archive import init_vault, open_vault, add_person, head, resolve, iter_current
from helseark.contracts import PersonDraft, ResourceRef, ArchiveError


def test_person_creation_is_readable_without_database(tmp_path):
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("Alex Example", "2000-02", "Self reported"))
    reopened = open_vault(vault.root)
    patient = resolve(reopened, person, ResourceRef("Patient", person))
    assert patient["id"] == person
    assert patient["name"] == [{"text": "Alex Example"}]
    assert patient["birthDate"] == "2000-02"
    assert list(iter_current(reopened, person)) == [patient]
    assert head(reopened, person).sequence == 1
    assert not list(vault.root.rglob("*.sqlite"))
    other = add_person(vault, PersonDraft("Alex Example"))
    assert other != person
    assert head(vault, other).sequence == 1
    with pytest.raises(ArchiveError):
        resolve(vault, other, ResourceRef("Patient", person))


def test_invalid_person_does_not_publish(tmp_path):
    vault = init_vault(tmp_path / "vault")
    for draft in [PersonDraft(""), PersonDraft("Alex", "2001-02-30")]:
        with pytest.raises(ArchiveError):
            add_person(vault, draft)
    assert list((vault.root / "people").iterdir()) == []

# Build real second revisions, using the documented retained-proposal protocol.
# This is a storage fixture, not a clinical import API.
import os
import shutil
import subprocess
import sys
from uuid import uuid4
from helseark.archive import _publish_change
from helseark.serialization import encode_json, decode_json, hash_bytes


def write_json(path, value):
    path.write_bytes(encode_json(value))


def update_payload(vault, person, destination):
    base = head(vault, person)
    source = vault.root / "people" / person / "accepted" / f"{base.sequence:08d}-{base.transactionId}"
    shutil.copytree(source, destination)
    (destination / "change.json").unlink()
    proposal = decode_json((destination / "proposal.json").read_bytes())
    proposal["baseChangeSha256"] = base.changeSha256
    proposal["transactionId"] = str(uuid4())
    proposal["kind"] = "correction"
    resource = proposal["resources"][0]
    patient = decode_json((destination / resource["path"]).read_bytes())
    resource["supersedesVersionId"] = patient["meta"]["versionId"]
    patient["meta"]["versionId"] = str(uuid4())
    patient["name"][0]["text"] = "Alex Revised"
    write_json(destination / resource["path"], patient)
    resource["versionId"] = patient["meta"]["versionId"]
    resource["sha256"] = hash_bytes((destination / resource["path"]).read_bytes())
    write_json(destination / "proposal.json", proposal)
    proposal_hash = hash_bytes((destination / "proposal.json").read_bytes())
    validation = decode_json((destination / "validation.json").read_bytes())
    validation["checkedProposalSha256"] = proposal_hash
    write_json(destination / "validation.json", validation)
    review = decode_json((destination / "review.json").read_bytes())
    review.update(baseChangeSha256=base.changeSha256, proposalSha256=proposal_hash,
                  validationSha256=hash_bytes((destination / "validation.json").read_bytes()))
    write_json(destination / "review.json", review)
    return base


def publish_child(vault, person, payload, base, boundary):
    script = """
import sys
from pathlib import Path
from helseark.archive import open_vault, _publish_change
from helseark.contracts import Head
v = open_vault(Path(sys.argv[1]))
_publish_change(v, sys.argv[2], Path(sys.argv[3]), Head(int(sys.argv[4]), sys.argv[5], sys.argv[6]))
"""
    return subprocess.run([sys.executable, "-c", script, str(vault.root), person, str(payload),
                           str(base.sequence), base.transactionId, base.changeSha256],
                          env={**os.environ, "_HELSEARK_TEST_CRASH_AT": boundary}, capture_output=True)


def test_crash_before_rename_has_no_visible_change(tmp_path):
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("Alex Example"))
    payload = tmp_path / "prepared"
    base = update_payload(vault, person, payload)
    child = publish_child(vault, person, payload, base, "before-rename")
    assert child.returncode == 91, child.stderr
    reopened = open_vault(vault.root)
    assert head(reopened, person) == base
    assert resolve(reopened, person, ResourceRef("Patient", person))["name"][0]["text"] == "Alex Example"
    # A real, complete but unpublished staging directory was left on disk.
    staged = list((vault.root / ".runtime/staging").glob("*/change.json"))
    assert len(staged) == 1
    # Crash released the OS lock; the exact same prepared update can publish.
    assert _publish_change(reopened, person, payload, base).sequence == 2


def test_crash_after_rename_has_complete_change(tmp_path):
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("Alex Example"))
    payload = tmp_path / "prepared"
    base = update_payload(vault, person, payload)
    child = publish_child(vault, person, payload, base, "after-rename")
    assert child.returncode == 91, child.stderr
    reopened = open_vault(vault.root)
    assert head(reopened, person).sequence == 2
    current = resolve(reopened, person, ResourceRef("Patient", person))
    assert current["name"][0]["text"] == "Alex Revised"
    assert len(list((vault.root / "people" / person / "accepted").iterdir())) == 2
    assert resolve(reopened, person, ResourceRef("Patient", person), at=base)["name"][0]["text"] == "Alex Example"
    with pytest.raises(ArchiveError, match="STALE_BASE"):
        _publish_change(reopened, person, payload, base)


def test_second_writer_reports_busy(tmp_path):
    vault = init_vault(tmp_path / "vault")
    script = """
import sys
from pathlib import Path
from helseark.archive import open_vault, _writer_lock
with _writer_lock(open_vault(Path(sys.argv[1]))):
    print("locked", flush=True)
    sys.stdin.readline()
"""
    child = subprocess.Popen([sys.executable, "-c", script, str(vault.root)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "locked"
        with pytest.raises(ArchiveError, match="ARCHIVE_BUSY"):
            add_person(vault, PersonDraft("Alex Example"))
    finally:
        child.communicate("\n", timeout=10)
    assert child.returncode == 0
    add_person(vault, PersonDraft("Alex Example"))


def test_parent_hash_mismatch_blocks_read(tmp_path):
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("Alex Example"))
    payload = tmp_path / "prepared"
    base = update_payload(vault, person, payload)
    _publish_change(vault, person, payload, base)
    second = sorted((vault.root / "people" / person / "accepted").iterdir())[1]
    change = decode_json((second / "change.json").read_bytes())
    change["previousChangeSha256"] = hash_bytes(b"different parent")
    write_json(second / "change.json", change)
    for read in [lambda: open_vault(vault.root), lambda: head(vault, person),
                 lambda: list(iter_current(vault, person)),
                 lambda: resolve(vault, person, ResourceRef("Patient", person), at=base)]:
        with pytest.raises(ArchiveError, match="INTEGRITY"):
            read()


def test_symlink_payload_rejected(tmp_path):
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("Alex Example"))
    payload = tmp_path / "prepared"
    base = update_payload(vault, person, payload)
    resource = next((payload / "resources").iterdir())
    external = tmp_path / "outside.json"
    resource.rename(external)
    resource.symlink_to(external)
    with pytest.raises(ArchiveError, match="UNSAFE_PATH"):
        _publish_change(vault, person, payload, base)
    assert head(vault, person) == base


def test_edited_review_target_and_unknown_fields_fail_closed(tmp_path):
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("Alex Example"))
    payload = tmp_path / "prepared"
    base = update_payload(vault, person, payload)
    proposal = decode_json((payload / "proposal.json").read_bytes())
    proposal["candidateSha256"] = hash_bytes(b"edited after review")
    write_json(payload / "proposal.json", proposal)
    with pytest.raises(ArchiveError, match="REVIEW_MISMATCH"):
        _publish_change(vault, person, payload, base)
    assert head(vault, person) == base
    review = decode_json((payload / "review.json").read_bytes())
    review["unknown"] = True
    write_json(payload / "review.json", review)
    with pytest.raises(ArchiveError, match="INVALID_ENVELOPE"):
        _publish_change(vault, person, payload, base)


def test_accepted_resource_tamper_detected(tmp_path):
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("Alex Example"))
    resource = next((vault.root / "people" / person / "accepted").glob("*/resources/*.json"))
    resource.write_bytes(resource.read_bytes() + b" ")
    with pytest.raises(ArchiveError, match="INTEGRITY"):
        open_vault(vault.root)


def test_definition_tamper_and_unknown_vault_fields(tmp_path):
    vault = init_vault(tmp_path / "vault")
    schema = vault.root / "definitions/schemas/0.1.0/review.schema.json"
    schema.write_bytes(schema.read_bytes() + b" ")
    with pytest.raises(ArchiveError, match="DEFINITION_MISMATCH"):
        open_vault(vault.root)
    second = init_vault(tmp_path / "second")
    config = decode_json((second.root / "vault.json").read_bytes())
    config["extra"] = True
    write_json(second.root / "vault.json", config)
    with pytest.raises(ArchiveError, match="INVALID_ENVELOPE"):
        open_vault(second.root)


def test_revision_and_snapshot_resolution(tmp_path):
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("Alex Example"))
    original = resolve(vault, person, ResourceRef("Patient", person))
    base = update_payload(vault, person, tmp_path / "prepared")
    latest = _publish_change(vault, person, tmp_path / "prepared", base)
    assert resolve(vault, person, ResourceRef("Patient", person, original["meta"]["versionId"])) == original
    assert list(iter_current(vault, person, at=base)) == [original]
    assert list(iter_current(vault, person, at=latest))[0]["name"][0]["text"] == "Alex Revised"
    wrong_head = type(base)(base.sequence, base.transactionId, hash_bytes(b"not a head"))
    with pytest.raises(ArchiveError, match="UNKNOWN_HEAD"):
        list(iter_current(vault, person, at=wrong_head))


def test_runtime_is_not_required_to_read_or_reopen(tmp_path):
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("Alex Example"))
    shutil.rmtree(vault.root / ".runtime")
    reopened = open_vault(vault.root)
    assert resolve(reopened, person, ResourceRef("Patient", person))["name"][0]["text"] == "Alex Example"
    assert not (vault.root / ".runtime").exists()  # reads do not recreate runtime
    second = add_person(reopened, PersonDraft("Alex Example"))
    assert head(reopened, second).sequence == 1


def test_pinned_contract_edit_after_open_blocks_read(tmp_path):
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("Alex Example"))
    schema = vault.root / "definitions/schemas/0.1.0/change.schema.json"
    schema.write_bytes(schema.read_bytes() + b" ")
    with pytest.raises(ArchiveError, match="DEFINITION_MISMATCH"):
        head(vault, person)


@pytest.mark.parametrize("boundary,visible", [("before-rename", False), ("after-rename", True)])
def test_person_genesis_crash_boundaries(tmp_path, boundary, visible):
    vault = init_vault(tmp_path / "vault")
    child = subprocess.run([sys.executable, "-m", "helseark.cli", "--vault", str(vault.root),
                            "person", "add", "--name", "Alex Example", "--json"],
                           env={**os.environ, "_HELSEARK_TEST_CRASH_AT": boundary}, capture_output=True)
    assert child.returncode == 91, child.stderr
    reopened = open_vault(vault.root)
    person = next((vault.root / "people").iterdir()).name
    if visible:
        assert head(reopened, person).sequence == 1
        assert resolve(reopened, person, ResourceRef("Patient", person))["id"] == person
    else:
        assert head(reopened, person) is None
        assert list(iter_current(reopened, person)) == []
    # Both boundaries release the lock and preserve the first person's state.
    another = add_person(reopened, PersonDraft("Another Example"))
    assert another != person


def test_prepare_clock_and_ids_are_explicit_and_collision_does_not_overwrite(tmp_path):
    from datetime import datetime, timezone
    vault = init_vault(tmp_path / "vault")
    ids = ["11111111-1111-4111-8111-111111111111",
           "22222222-2222-4222-8222-222222222222",
           "33333333-3333-4333-8333-333333333333"]
    person = add_person(vault, PersonDraft("Alex"), clock=lambda: datetime(2000, 1, 2, tzinfo=timezone.utc),
                        uuid_factory=iter(ids).__next__)
    patient = resolve(vault, person, ResourceRef("Patient", person))
    assert patient["meta"] == {"versionId": ids[1], "lastUpdated": "2000-01-02T00:00:00Z"}
    before = head(vault, person)
    with pytest.raises(ArchiveError, match="DESTINATION_EXISTS"):
        add_person(vault, PersonDraft("Different"), uuid_factory=iter(ids).__next__)
    assert head(vault, person) == before


def test_normal_operations_with_network_forbidden(tmp_path):
    script = """
import sys
from pathlib import Path
def offline(event, args):
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise AssertionError("Network attempt")
sys.addaudithook(offline)
from helseark.archive import init_vault, add_person, open_vault, resolve
from helseark.contracts import PersonDraft, ResourceRef
v = init_vault(Path(sys.argv[1]))
p = add_person(v, PersonDraft("Alex Example"))
assert resolve(open_vault(v.root), p, ResourceRef("Patient", p))["id"] == p
"""
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path / "vault")], capture_output=True)
    assert result.returncode == 0, result.stderr


def rebind_proposal(directory, proposal):
    write_json(directory / "proposal.json", proposal)
    digest = hash_bytes((directory / "proposal.json").read_bytes())
    validation = decode_json((directory / "validation.json").read_bytes())
    validation["checkedProposalSha256"] = digest
    write_json(directory / "validation.json", validation)
    review = decode_json((directory / "review.json").read_bytes())
    review["proposalSha256"] = digest
    review["validationSha256"] = hash_bytes((directory / "validation.json").read_bytes())
    write_json(directory / "review.json", review)


def test_duplicate_revision_in_one_change_never_becomes_visible(tmp_path):
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("Alex"))
    payload = tmp_path / "prepared"
    base = update_payload(vault, person, payload)
    proposal = decode_json((payload / "proposal.json").read_bytes())
    observation_id = str(uuid4())
    version = proposal["resources"][0]["versionId"]
    observation = {"resourceType": "Observation", "id": observation_id,
                   "meta": {"versionId": version, "lastUpdated": "2026-11-14T00:00:00Z"},
                   "status": "final", "code": {"text": "Synthetic fixture"},
                   "subject": {"reference": f"Patient/{person}"},
                   "dataAbsentReason": {"text": "Not performed"}}
    path = f"resources/Observation-{observation_id}.json"
    write_json(payload / path, observation)
    proposal["resources"].append({"type": "Observation", "id": observation_id, "versionId": version,
                                   "sha256": hash_bytes((payload / path).read_bytes()), "path": path,
                                   "supersedesVersionId": None})
    rebind_proposal(payload, proposal)
    with pytest.raises(ArchiveError, match="INTEGRITY"):
        _publish_change(vault, person, payload, base)
    assert head(open_vault(vault.root), person) == base


def test_malformed_resource_meta_is_a_typed_failure(tmp_path):
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("Alex"))
    payload = tmp_path / "prepared"
    base = update_payload(vault, person, payload)
    proposal = decode_json((payload / "proposal.json").read_bytes())
    entry = proposal["resources"][0]
    resource = decode_json((payload / entry["path"]).read_bytes())
    resource["meta"] = []
    write_json(payload / entry["path"], resource)
    entry["sha256"] = hash_bytes((payload / entry["path"]).read_bytes())
    rebind_proposal(payload, proposal)
    with pytest.raises(ArchiveError, match="INTEGRITY"):
        _publish_change(vault, person, payload, base)
    assert head(vault, person) == base


def test_corruption_identifies_affected_file_without_private_message(tmp_path):
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("PRIVATE NAME"))
    change = next((vault.root / "people" / person / "accepted").glob("*/change.json"))
    change.write_bytes(b'{"PRIVATE RECORD":')
    with pytest.raises(ArchiveError) as raised:
        open_vault(vault.root)
    assert raised.value.details.get("path") == change.relative_to(vault.root).as_posix()
    assert "PRIVATE" not in raised.value.safeMessage


@pytest.mark.parametrize('field', ['id', 'versionId', 'transactionId', 'type', 'sha256'])
def test_newline_tokens_never_publish(tmp_path, field):
    vault = init_vault(tmp_path / 'vault')
    person = add_person(vault, PersonDraft('Synthetic'))
    payload = tmp_path / 'prepared'
    base = update_payload(vault, person, payload)
    proposal = decode_json((payload / 'proposal.json').read_bytes())
    entry = proposal['resources'][0]
    if field == 'transactionId':
        proposal[field] += '\n'
    else:
        old_path = entry['path']
        entry[field] += '\n'
        resource = decode_json((payload / old_path).read_bytes())
        if field == 'id':
            resource['id'] = entry[field]
        elif field == 'versionId':
            resource['meta']['versionId'] = entry[field]
        elif field == 'type':
            resource['resourceType'] = entry[field]
        if field in ('id', 'type'):
            entry['path'] = f"resources/{entry['type']}-{entry['id']}.json"
            (payload / old_path).unlink()
        write_json(payload / entry['path'], resource)
        if field != 'sha256':
            entry['sha256'] = hash_bytes((payload / entry['path']).read_bytes())
    rebind_proposal(payload, proposal)
    with pytest.raises(ArchiveError, match='INVALID_ENVELOPE'):
        _publish_change(vault, person, payload, base)
    assert head(open_vault(vault.root), person) == base


def test_newline_vault_id_cannot_open(tmp_path):
    vault = init_vault(tmp_path / 'vault')
    path = vault.root / 'vault.json'
    value = decode_json(path.read_bytes())
    value['vaultId'] += '\n'
    write_json(path, value)
    with pytest.raises(ArchiveError, match='INVALID_ENVELOPE'):
        open_vault(vault.root)


def test_exact_pinned_revision_survives_update_and_reopen(tmp_path):
    vault = init_vault(tmp_path / 'vault')
    person = add_person(vault, PersonDraft('Synthetic'))
    original = resolve(vault, person, ResourceRef('Patient', person))
    ref = ResourceRef('Patient', person, original['meta']['versionId'])
    payload = tmp_path / 'prepared'
    base = update_payload(vault, person, payload)
    _publish_change(vault, person, payload, base)
    reopened = open_vault(vault.root)
    assert resolve(reopened, person, ref) == original
    assert resolve(reopened, person, ResourceRef('Patient', person)) != original


def test_ancestor_alias_allowed_but_root_alias_rejected(tmp_path):
    container = tmp_path / 'container'
    container.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(container, target_is_directory=True)
    vault = init_vault(alias / 'vault')
    person = add_person(vault, PersonDraft('Synthetic'))
    assert head(open_vault(container / 'vault'), person) == head(open_vault(alias / 'vault'), person)
    direct = tmp_path / 'direct'
    direct.symlink_to(vault.root, target_is_directory=True)
    with pytest.raises(ArchiveError, match='UNSAFE_PATH'):
        open_vault(direct)


@pytest.mark.parametrize('damage', ['schema', 'binding', 'inventory', 'revision', 'asset'])
def test_integrity_diagnostics_are_opaque_relative_paths(tmp_path, damage):
    vault = init_vault(tmp_path / 'PRIVATE ROOT')
    person = add_person(vault, PersonDraft('PRIVATE NAME'))
    directory = next((vault.root / 'people' / person / 'accepted').iterdir())
    change_path = directory / 'change.json'
    change = decode_json(change_path.read_bytes())
    if damage == 'schema':
        proposal = decode_json((directory / 'proposal.json').read_bytes())
        proposal['PRIVATE FIELD'] = 'PRIVATE VALUE'
        write_json(directory / 'proposal.json', proposal)
    elif damage == 'binding':
        review = decode_json((directory / 'review.json').read_bytes())
        review['proposalSha256'] = 'a' * 64
        write_json(directory / 'review.json', review)
    elif damage == 'inventory':
        (directory / 'PRIVATE EXTRA').write_text('PRIVATE CONTENT')
    elif damage == 'revision':
        change['resources'][0]['supersedesVersionId'] = str(uuid4())
        write_json(change_path, change)
    else:
        proposal = decode_json((directory / 'proposal.json').read_bytes())
        proposal['assets'] = [{'sha256': 'a' * 64, 'size': 1, 'mediaType': 'text/plain', 'path': 'assets/sha256/' + 'a' * 64 + '/blob'}]
        write_json(directory / 'proposal.json', proposal)
    with pytest.raises(ArchiveError) as raised:
        open_vault(vault.root)
    path = raised.value.details.get('path')
    assert path and not Path(path).is_absolute()
    assert 'PRIVATE' not in str(raised.value.details) + raised.value.safeMessage
    assert (vault.root / path).exists() or damage == 'asset'


@pytest.mark.parametrize('field', ['id', 'versionId', 'transactionId', 'type', 'sha256'])
def test_newline_tokens_in_genesis_cannot_open(tmp_path, field):
    vault = init_vault(tmp_path / 'vault')
    person = add_person(vault, PersonDraft('Synthetic'))
    path = next((vault.root / 'people' / person / 'accepted').glob('*/change.json'))
    value = decode_json(path.read_bytes())
    target = value if field == 'transactionId' else value['resources'][0]
    target[field] += '\n'
    write_json(path, value)
    with pytest.raises(ArchiveError, match='INTEGRITY'):
        open_vault(vault.root)


@pytest.mark.parametrize('filename,field', [('validation.json', 'checkedProposalSha256'), ('proposal.json', 'evidenceSha256')])
def test_binding_diagnostic_identifies_affected_envelope(tmp_path, filename, field):
    vault = init_vault(tmp_path / 'vault')
    person = add_person(vault, PersonDraft('Synthetic'))
    directory = next((vault.root / 'people' / person / 'accepted').iterdir())
    value = decode_json((directory / filename).read_bytes())
    value[field] = 'a' * 64
    write_json(directory / filename, value)
    with pytest.raises(ArchiveError) as raised:
        open_vault(vault.root)
    expected = 'validation.json' if filename == 'validation.json' else 'evidence.json'
    assert raised.value.details['path'] == (directory / expected).relative_to(vault.root).as_posix()


def test_definition_corruption_reports_actual_vault_relative_path(tmp_path):
    vault = init_vault(tmp_path / 'vault')
    path = vault.root / 'definitions/schemas/0.1.0/proposal.schema.json'
    path.write_bytes(b'{"PRIVATE RECORD":')
    with pytest.raises(ArchiveError, match='DEFINITION_MISMATCH') as raised:
        open_vault(vault.root)
    assert raised.value.details['path'] == path.relative_to(vault.root).as_posix()


@pytest.mark.parametrize("token", [
    "1e128", "0e128", "0.1e-128", "9" * 128 + "e128",
    "-0." + "0" * 509,
])
def test_canonical_numeric_payload_survives_publication_and_reopen(tmp_path, token):
    from helseark.serialization import decode_canonical_json
    vault = init_vault(tmp_path / "vault")
    person = add_person(vault, PersonDraft("Synthetic Serialization Fixture"))
    payload = tmp_path / "prepared"
    base = update_payload(vault, person, payload)
    proposal = decode_canonical_json((payload / "proposal.json").read_bytes())
    entry = proposal["resources"][0]
    patient = decode_canonical_json((payload / entry["path"]).read_bytes())
    # Storage-only synthetic field, with no claim of clinical validation.
    patient["_serializationFixture"] = decode_json(token.encode())
    write_json(payload / entry["path"], patient)
    expected_bytes = (payload / entry["path"]).read_bytes()
    entry["sha256"] = hash_bytes(expected_bytes)
    rebind_proposal(payload, proposal)
    published = _publish_change(vault, person, payload, base)
    reopened = open_vault(vault.root)
    current = resolve(reopened, person, ResourceRef("Patient", person))
    assert encode_json(current) == expected_bytes
    assert list(iter_current(reopened, person)) == [current]
    assert head(reopened, person) == published
    assert "_serializationFixture" not in resolve(
        reopened, person, ResourceRef("Patient", person), at=base)
    actual = current["_serializationFixture"]
    expected = patient["_serializationFixture"]
    assert actual == expected
    if "." in token:
        assert actual.as_tuple() == expected.as_tuple()


@pytest.mark.parametrize("raw", [b"1e999999999", b"9" * 129,
                                 b"0." + b"0" * 511])
def test_canonical_archive_boundary_rejects_unbounded_numbers(tmp_path, raw):
    from helseark.archive import _json
    (tmp_path / "fixture.json").write_bytes(raw)
    with pytest.raises(ArchiveError) as error:
        _json(tmp_path, "fixture.json")
    assert error.value.code == "INTEGRITY"
    assert error.value.details == {"path": "fixture.json"}
