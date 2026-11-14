"""Immutable file authority: lock, verified history, publication and resolution.

The internal publisher accepts a *prepared* directory, never arbitrary clinical
CLI input. Task 6 owns candidate preparation and human review for imports.
"""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime, timezone
import fcntl
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sysconfig
from uuid import uuid4
from typing import Iterator

from jsonschema import Draft202012Validator

from .contracts import ArchiveError, VaultConfig, Vault, PersonDraft, Head, ResourceRef, FHIRResource, uuid_string
from .serialization import encode_json, decode_json, hash_bytes

_ENVELOPES = ("proposal.json", "evidence.json", "review.json", "validation.json")


def _safe(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if not parts or relative != "/".join(parts) or any(p in (".", "..") for p in parts) or PurePosixPath(relative).is_absolute() or "\\" in relative:
        raise ArchiveError("UNSAFE_PATH", "Archive path is not confined.")
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ArchiveError("UNSAFE_PATH", "Symlink in archive path.", {"path": relative})
    return path


def _read(root: Path, relative: str) -> bytes:
    path = _safe(root, relative)
    try:
        if not path.is_file():
            raise ArchiveError("INTEGRITY", "Missing regular archive file.", {"path": relative})
        return path.read_bytes()
    except OSError:
        raise ArchiveError("IO_ERROR", "Cannot read archive file.", {"path": relative}) from None


def _json(root: Path, relative: str, *, data: bytes | None = None):
    try:
        return decode_json(_read(root, relative) if data is None else data)
    except ArchiveError as error:
        error.details.setdefault("path", str(root / relative))
        raise


def _schema(vault: Vault, name: str, value):
    lock_data = _read(vault.root, "definitions/lock.json")
    if hash_bytes(lock_data) != vault.config.definitionLockSha256:
        raise ArchiveError("DEFINITION_MISMATCH", "Definition lock checksum mismatch.")
    relative = f"schemas/0.1.0/{name}.schema.json"
    lock = decode_json(lock_data)
    entries = [entry for artifact in lock["artifacts"] for entry in artifact["files"] if entry["path"] == relative]
    schema_data = _read(vault.root, "definitions/" + relative)
    if len(entries) != 1 or hash_bytes(schema_data) != entries[0]["sha256"] or len(schema_data) != entries[0]["size"]:
        raise ArchiveError("DEFINITION_MISMATCH", "Pinned envelope contract checksum mismatch.")
    schema = decode_json(schema_data)
    if not Draft202012Validator(schema).is_valid(value):
        raise ArchiveError("INVALID_ENVELOPE", "Archive envelope violates its pinned contract.", {"schema": name})


def _versions(vault: Vault):
    return {k: v for k, v in asdict(vault.config).items() if k != "vaultId"}


def _sync_directory(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path: Path, data: bytes):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _sync_tree(root: Path):
    for parent, dirs, files in os.walk(root, topdown=False, followlinks=False):
        parent = Path(parent)
        for name in dirs + files:
            _safe(root, (parent / name).relative_to(root).as_posix())
        for name in files:
            with (parent / name).open("rb") as stream:
                os.fsync(stream.fileno())
        _sync_directory(parent)


@contextmanager
def _writer_lock(vault: Vault):
    """POSIX advisory lock; never steal by age. Death releases the OS lock."""
    runtime = _safe(vault.root, ".runtime")
    runtime.mkdir(mode=0o700, exist_ok=True)
    _safe(vault.root, ".runtime/staging").mkdir(mode=0o700, exist_ok=True)
    _sync_directory(runtime)
    _sync_directory(vault.root)
    path = _safe(vault.root, ".runtime/writer.lock")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ArchiveError("ARCHIVE_BUSY", "Another vault writer holds the lock.") from None
        yield
    finally:
        os.close(fd)


def _bundled_root():
    source = Path(__file__).resolve().parents[2]
    if (source / "definitions/lock.json").is_file():
        return source
    return Path(sysconfig.get_path("data")) / "share/helseark"


def init_vault(root: Path, config: VaultConfig | None = None) -> Vault:
    root = Path(root).absolute()
    if root.exists() or root.is_symlink():
        raise ArchiveError("DESTINATION_EXISTS", "Vault destination must not exist.")
    root.parent.mkdir(parents=True, exist_ok=True)
    bundle = _bundled_root()
    lock_bytes = _read(bundle, "definitions/lock.json")
    if config is None:
        config = VaultConfig(1, "0.1.0", "0.1.0", "4.0.1", "helseark-json-1",
                             hash_bytes(lock_bytes), None, None, str(uuid4()))
    if config.definitionLockSha256 != hash_bytes(lock_bytes):
        raise ArchiveError("DEFINITION_MISMATCH", "Requested definitions are not bundled.")
    stage = root.parent / f".helseark-init-{uuid4()}"
    try:
        stage.mkdir(mode=0o700)
        (stage / "definitions").mkdir()
        _write(stage / "definitions/lock.json", lock_bytes)
        lock = decode_json(lock_bytes)
        for artifact in lock["artifacts"]:
            for entry in artifact["files"]:
                data = _read(bundle, entry["path"])
                if hash_bytes(data) != entry["sha256"] or len(data) != entry["size"]:
                    raise ArchiveError("DEFINITION_MISMATCH", "Bundled contract checksum mismatch.")
                target = _safe(stage / "definitions", entry["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                _write(target, data)
        for relative in ("people", ".runtime/staging"):
            (stage / relative).mkdir(parents=True)
        _write(stage / "vault.json", encode_json(asdict(config)))
        _write(stage / "README.md", b"Helseark archive format 1. Accepted JSON is authoritative.\n"
               b"Do not edit accepted history. Staging is unpublished and ignored.\n"
               b"Task 1 supports init/person add only; no clinical import or full FHIR validation.\n"
               b"Copy this whole folder while no writer is active to retain definitions and history.\n")
        open_vault(stage)
        _sync_tree(stage)
        # Rename of a nonempty destination fails; never replace a vault.
        if root.exists() or root.is_symlink():
            raise ArchiveError("DESTINATION_EXISTS", "Vault destination already exists.")
        os.rename(stage, root)
        _sync_directory(root.parent)
        return open_vault(root)
    except OSError:
        raise ArchiveError("IO_ERROR", "Vault initialization failed.") from None
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def open_vault(root: Path) -> Vault:
    root = Path(root).absolute()
    if root.is_symlink():
        raise ArchiveError("UNSAFE_PATH", "Vault root cannot be a symlink.")
    value = _json(root, "vault.json")
    # Check supported pins before reporting a generic envelope error.
    expected = {"archiveFormatVersion": 1, "contractVersion": "0.1.0",
                "profileVersion": "0.1.0", "fhirVersion": "4.0.1",
                "serializationVersion": "helseark-json-1",
                "agentKitVersion": None, "agentKitLockSha256": None}
    if not isinstance(value, dict) or any(value.get(k) != v for k, v in expected.items()):
        raise ArchiveError("UNSUPPORTED_VERSION", "Vault version pins are unsupported.")
    try:
        vault = Vault(root, VaultConfig(**value))
    except TypeError:
        raise ArchiveError("INVALID_ENVELOPE", "Invalid vault configuration.") from None
    lock_data = _read(root, "definitions/lock.json")
    if hash_bytes(lock_data) != vault.config.definitionLockSha256:
        raise ArchiveError("DEFINITION_MISMATCH", "Definition lock checksum mismatch.")
    lock = decode_json(lock_data)
    for artifact in lock["artifacts"]:
        for entry in artifact["files"]:
            data = _read(root, "definitions/" + entry["path"])
            if hash_bytes(data) != entry["sha256"] or len(data) != entry["size"]:
                raise ArchiveError("DEFINITION_MISMATCH", "Definition inventory checksum mismatch.", {"path": entry["path"]})
    _schema(vault, "vault", value)
    for relative in ("people",):
        if not _safe(root, relative).is_dir():
            raise ArchiveError("INTEGRITY", "Missing vault directory.", {"path": relative})
    # Fail closed on corrupt accepted state, including people the caller did not select.
    for path in (root / "people").iterdir():
        uuid_string(path.name)
        _history(vault, path.name)
    return vault


def _files(root: Path) -> set[str]:
    if root.is_symlink():
        raise ArchiveError("UNSAFE_PATH", "Payload root is a symlink.")
    result = set()
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = _safe(root, (Path(parent) / name).relative_to(root).as_posix())
            if not path.is_dir() and not path.is_file():
                raise ArchiveError("UNSAFE_PATH", "Payload is not a regular file or directory.")
        for name in files:
            result.add((Path(parent) / name).relative_to(root).as_posix())
    return result


def _verify_payload(vault: Vault, person: str, directory: Path, base: Head | None):
    proposal = _json(directory, "proposal.json")
    evidence = _json(directory, "evidence.json")
    validation = _json(directory, "validation.json")
    review = _json(directory, "review.json")
    for name, value in (("proposal", proposal), ("evidence", evidence), ("validation", validation), ("review", review)):
        _schema(vault, name, value)
    digest = hash_bytes(_read(directory, "proposal.json"))
    previous = base.changeSha256 if base else None
    if proposal["personId"] != person or evidence["personId"] != person or review["personId"] != person:
        raise ArchiveError("PERSON_MISMATCH", "Envelope belongs to a different person.")
    if proposal["baseChangeSha256"] != previous or review["baseChangeSha256"] != previous:
        raise ArchiveError("STALE_BASE", "Reviewed base differs from accepted history.")
    if proposal["versions"] != _versions(vault):
        raise ArchiveError("UNSUPPORTED_VERSION", "Proposal pins differ from the vault.")
    if (review["proposalSha256"] != digest or validation["checkedProposalSha256"] != digest
            or review["validationSha256"] != hash_bytes(_read(directory, "validation.json"))
            or proposal["evidenceSha256"] != hash_bytes(_read(directory, "evidence.json"))):
        raise ArchiveError("REVIEW_MISMATCH", "Reviewed payload digests do not match.")
    if any(issue["severity"] == "error" for issue in validation["issues"]) or any(c["result"] == "failed" for c in validation["coverage"]):
        raise ArchiveError("VALIDATION_BLOCKED", "Failed checks cannot be accepted.")
    expected_files = set(_ENVELOPES)
    seen = set()
    for entry in proposal["resources"]:
        key = (entry["type"], entry["id"])
        if key in seen:
            raise ArchiveError("INTEGRITY", "Duplicate logical resource in one change.")
        seen.add(key)
        expected_path = f"resources/{entry['type']}-{entry['id']}.json"
        if entry["path"] != expected_path:
            raise ArchiveError("UNSAFE_PATH", "Unexpected resource inventory path.")
        expected_files.add(expected_path)
        data = _read(directory, expected_path)
        resource = _json(directory, expected_path, data=data)
        if (hash_bytes(data) != entry["sha256"] or not isinstance(resource, dict)
                or resource.get("resourceType") != entry["type"] or resource.get("id") != entry["id"]
                or not isinstance(resource.get("meta"), dict)
                or resource["meta"].get("versionId") != entry["versionId"]):
            raise ArchiveError("INTEGRITY", "Resource revision or checksum mismatch.", {"path": expected_path})
        if entry["type"] == "Patient" and entry["id"] != person:
            raise ArchiveError("PERSON_MISMATCH", "Patient identity differs from person directory.")
    for asset in proposal["assets"]:
        if asset["path"] != f"assets/sha256/{asset['sha256']}/blob":
            raise ArchiveError("UNSAFE_PATH", "Unexpected asset path.")
        data = _read(vault.root, f"people/{person}/{asset['path']}")
        if hash_bytes(data) != asset["sha256"] or len(data) != asset["size"]:
            raise ArchiveError("INTEGRITY", "Asset checksum mismatch.")
    actual = _files(directory) - {"change.json"}
    if actual != expected_files or not proposal["resources"]:
        raise ArchiveError("INTEGRITY", "Payload inventory is incomplete or contains extra files.")
    return proposal


def _history(vault: Vault, person: str):
    uuid_string(person)
    accepted = _safe(vault.root, f"people/{person}/accepted")
    if not accepted.is_dir():
        raise ArchiveError("PERSON_NOT_FOUND", "No accepted history for the selected person.")
    result, base, current, revisions = [], None, {}, set()
    for directory in sorted(accepted.iterdir()):
        _safe(vault.root, directory.relative_to(vault.root).as_posix())
        change_data = _read(directory, "change.json")
        change = _json(directory, "change.json", data=change_data)
        _schema(vault, "change", change)
        sequence = len(result) + 1
        if (change["sequence"] != sequence or directory.name != f"{sequence:08d}-{change['transactionId']}"
                or change["personId"] != person or change["versions"] != _versions(vault)
                or change["previousChangeSha256"] != (base.changeSha256 if base else None)):
            raise ArchiveError("INTEGRITY", "Accepted chain sequence, identity or parent mismatch.", {"path": directory.relative_to(vault.root).as_posix()})
        proposal = _verify_payload(vault, person, directory, base)
        if (change["preparedContentSha256"] != hash_bytes(_read(directory, "proposal.json"))
                or change["resources"] != proposal["resources"] or change["assets"] != proposal["assets"]
                or change["transactionId"] != proposal["transactionId"]
                or change["payload"] != {n: hash_bytes(_read(directory, n)) for n in _ENVELOPES}):
            raise ArchiveError("INTEGRITY", "Change inventory differs from reviewed payload.")
        for entry in change["resources"]:
            key = (entry["type"], entry["id"])
            if entry["supersedesVersionId"] != current.get(key) or entry["versionId"] in revisions:
                raise ArchiveError("INTEGRITY", "Broken or reused resource revision.")
            current[key] = entry["versionId"]
            revisions.add(entry["versionId"])
        if sequence == 1 and ("Patient", person) not in current:
            raise ArchiveError("INTEGRITY", "Genesis must create its Patient identity.")
        base = Head(sequence, change["transactionId"], hash_bytes(change_data))
        result.append((base, directory, change))
    return result


def head(vault: Vault, person: str) -> Head | None:
    history = _history(vault, person)
    return history[-1][0] if history else None


def _snapshot(vault: Vault, person: str, at: Head | None):
    history = _history(vault, person)
    if at is None:
        return history
    for i, (item, _, _) in enumerate(history):
        if item == at:
            return history[:i + 1]
    raise ArchiveError("UNKNOWN_HEAD", "Snapshot head is not in this person's history.")


def resolve(vault: Vault, person: str, ref: ResourceRef, at: Head | None = None) -> FHIRResource:
    for _, directory, change in reversed(_snapshot(vault, person, at)):
        for entry in change["resources"]:
            if (entry["type"], entry["id"]) == (ref.resourceType, ref.id) and (ref.versionId is None or entry["versionId"] == ref.versionId):
                return _json(directory, entry["path"])
    raise ArchiveError("RESOURCE_NOT_FOUND", "Resource revision is absent from this person's snapshot.")


def iter_current(vault: Vault, person: str, at: Head | None = None) -> Iterator[FHIRResource]:
    current = {}
    for _, directory, change in _snapshot(vault, person, at):
        for entry in change["resources"]:
            current[(entry["type"], entry["id"])] = (directory, entry["path"])
    for key in sorted(current):
        directory, path = current[key]
        yield _json(directory, path)


def _publication_boundary(boundary: str):
    """Internal process-death test hook. Never enables or skips validation."""
    if os.environ.get("_HELSEARK_TEST_CRASH_AT") == boundary:
        os._exit(91)


def _publish_locked(vault: Vault, person: str, payloadDirectory: Path, expectedBase: Head | None) -> Head:
    accepted = _safe(vault.root, f"people/{person}/accepted")
    current = head(vault, person)
    if current != expectedBase:
        raise ArchiveError("STALE_BASE", "Archive changed since preparation.")
    # Copy only after scanning for symlinks and special files; verify the copied bytes.
    files = _files(payloadDirectory)
    if "change.json" in files:
        raise ArchiveError("INVALID_INPUT", "Prepared payload cannot supply change.json.")
    stage = _safe(vault.root, f".runtime/staging/{uuid4()}")
    stage.mkdir(mode=0o700)
    for relative in sorted(files):
        target = _safe(stage, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        _write(target, _read(payloadDirectory, relative))
    proposal = _verify_payload(vault, person, stage, current)
    sequence = current.sequence + 1 if current else 1
    change = {"contractVersion": "0.1.0", "personId": person, "transactionId": proposal["transactionId"],
              "sequence": sequence, "previousChangeSha256": current.changeSha256 if current else None,
              "versions": _versions(vault), "preparedContentSha256": hash_bytes(_read(stage, "proposal.json")),
              "resources": proposal["resources"], "assets": proposal["assets"],
              "payload": {n: hash_bytes(_read(stage, n)) for n in _ENVELOPES}}
    _write(stage / "change.json", encode_json(change))
    # Validate the revision chain before the commit point without exposing staging.
    prior = _history(vault, person)
    existing = {}
    revisions = set()
    for _, _, old in prior:
        for entry in old["resources"]:
            existing[(entry["type"], entry["id"])] = entry["versionId"]
            revisions.add(entry["versionId"])
    for entry in change["resources"]:
        if entry["supersedesVersionId"] != existing.get((entry["type"], entry["id"])) or entry["versionId"] in revisions:
            raise ArchiveError("INTEGRITY", "Invalid revision succession.")
        revisions.add(entry["versionId"])
    if not current and not any(e["type"] == "Patient" and e["id"] == person for e in change["resources"]):
        raise ArchiveError("INTEGRITY", "Genesis requires its Patient.")
    destination = accepted / f"{sequence:08d}-{proposal['transactionId']}"
    if destination.exists() or destination.is_symlink():
        raise ArchiveError("DESTINATION_EXISTS", "Accepted destination already exists.")
    _sync_tree(stage)
    _sync_directory(stage.parent)
    _sync_directory(accepted.parent)
    _sync_directory(vault.root / "people")
    _publication_boundary("before-rename")
    os.rename(stage, destination)
    _publication_boundary("after-rename")
    _sync_directory(accepted)
    _sync_directory(stage.parent)
    return Head(sequence, proposal["transactionId"], hash_bytes(_read(destination, "change.json")))


def _publish_change(vault: Vault, person: str, payloadDirectory: Path, expectedBase: Head | None) -> Head:
    uuid_string(person)
    try:
        with _writer_lock(vault):
            open_vault(vault.root)
            return _publish_locked(vault, person, Path(payloadDirectory), expectedBase)
    except OSError:
        raise ArchiveError("IO_ERROR", "Change publication failed; reopen to determine committed state.") from None


def _patient(details: PersonDraft, person: str, revision: str, now: str):
    if (not isinstance(details.displayName, str) or not details.displayName.strip()
            or len(details.displayName) > 1024 or (details.note is not None and (not isinstance(details.note, str) or len(details.note) > 1048576))):
        raise ArchiveError("INVALID_PERSON", "Person name or note is invalid.")
    patient = {"resourceType": "Patient", "id": person, "meta": {"versionId": revision, "lastUpdated": now},
               "name": [{"text": details.displayName}]}
    if details.birthDate is not None:
        value = details.birthDate
        try:
            if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?", value):
                raise ValueError
            date.fromisoformat(value + ("-01-01" if len(value) == 4 else "-01" if len(value) == 7 else ""))
        except ValueError:
            raise ArchiveError("INVALID_PERSON", "Birth date must be a valid year, month or date.") from None
        patient["birthDate"] = value
    # A note is source evidence, not invented FHIR clinical content.
    encode_json(patient)
    return patient


def add_person(vault: Vault, details: PersonDraft, *, clock=None, uuid_factory=None) -> str:
    factory = uuid_factory or uuid4
    person, revision, transaction = (uuid_string(str(factory())) for _ in range(3))
    instant = (clock or (lambda: datetime.now(timezone.utc)))()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ArchiveError("INVALID_INPUT", "Preparation clock must have a timezone.")
    now = instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    patient = _patient(details, person, revision, now)
    reference = f"Patient/{person}/_history/{revision}"
    entries = [{"resourceRef": reference, "pointer": "/name/0/text", "kind": "user-entry", "value": details.displayName, "rule": None}]
    if details.birthDate is not None:
        entries.append({"resourceRef": reference, "pointer": "/birthDate", "kind": "user-entry", "value": details.birthDate, "rule": None})
    if details.note is not None:
        entries.append({"resourceRef": reference, "pointer": "", "kind": "user-entry", "value": details.note, "rule": "self-reported identity note; not a clinical assertion"})
    for pointer in ("/id", "/meta"):
        entries.append({"resourceRef": reference, "pointer": pointer, "kind": "generated", "value": "local archive identity/version", "rule": "person-add-1"})
    evidence = {"contractVersion": "0.1.0", "personId": person, "entries": entries}
    temporary = _safe(vault.root, f".runtime/staging/{uuid4()}")
    try:
        with _writer_lock(vault):
            open_vault(vault.root)
            person_dir = _safe(vault.root, f"people/{person}")
            if person_dir.exists():
                raise ArchiveError("DESTINATION_EXISTS", "Person ID already exists.")
            temporary.mkdir(mode=0o700)
            (temporary / "resources").mkdir()
            resource_path = f"resources/Patient-{person}.json"
            _write(temporary / resource_path, encode_json(patient))
            _write(temporary / "evidence.json", encode_json(evidence))
            proposal = {"contractVersion": "0.1.0", "personId": person, "transactionId": transaction,
                        "kind": "user-entry", "candidateSha256": hash_bytes(encode_json(asdict(details))),
                        "baseChangeSha256": None, "versions": _versions(vault),
                        "resources": [{"type": "Patient", "id": person, "versionId": revision, "path": resource_path,
                                       "sha256": hash_bytes(encode_json(patient)), "supersedesVersionId": None}],
                        "assets": [], "evidenceSha256": hash_bytes(encode_json(evidence))}
            _write(temporary / "proposal.json", encode_json(proposal))
            digest = hash_bytes(encode_json(proposal))
            validation = {"checkedProposalSha256": digest, "coverage": [
                {"family": "narrow-patient-constructor", "result": "passed", "reason": None},
                {"family": "full-fhir-and-terminology", "result": "not-checked", "reason": "Task 2 definitions not installed."}], "issues": []}
            _write(temporary / "validation.json", encode_json(validation))
            review = {"contractVersion": "0.1.0", "decision": "accept", "personId": person,
                      "proposalSha256": digest, "validationSha256": hash_bytes(encode_json(validation)),
                      "baseChangeSha256": None, "reviewer": {"kind": "local-user", "label": "explicit person add"},
                      "reviewedAt": now, "confirmedPerson": True, "acknowledgedIssues": []}
            _write(temporary / "review.json", encode_json(review))
            (person_dir / "accepted").mkdir(parents=True, mode=0o700)
            _publish_locked(vault, person, temporary, None)
            return person
    except OSError:
        raise ArchiveError("IO_ERROR", "Person publication failed; reopen to determine committed state.") from None
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
