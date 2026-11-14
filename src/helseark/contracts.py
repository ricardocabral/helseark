"""Local archive records. Clinical payloads remain FHIR JSON trees."""
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal, TypeAlias
from uuid import UUID
import re

PersonId: TypeAlias = str
ResourceId: TypeAlias = str
RevisionId: TypeAlias = str
TransactionId: TypeAlias = str
Sha256: TypeAlias = str
JsonValue: TypeAlias = None | bool | int | Decimal | str | list["JsonValue"] | dict[str, "JsonValue"]
FHIRResource: TypeAlias = dict[str, JsonValue]


class ArchiveError(Exception):
    def __init__(self, code: str, safeMessage: str, details: dict | None = None):
        self.code, self.safeMessage, self.details = code, safeMessage, details or {}
        super().__init__(f"{code}: {safeMessage}")


def uuid_string(value: str) -> str:
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ArchiveError("INVALID_ID", "Expected a lowercase UUID.") from None
    return value


def sha256_string(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ArchiveError("INVALID_DIGEST", "Expected a lowercase SHA-256 digest.")
    return value


@dataclass(frozen=True)
class VaultConfig:
    archiveFormatVersion: int
    contractVersion: str
    profileVersion: str
    fhirVersion: str
    serializationVersion: str
    definitionLockSha256: Sha256
    agentKitVersion: str | None
    agentKitLockSha256: Sha256 | None
    vaultId: str


@dataclass(frozen=True)
class Vault:
    root: Path
    config: VaultConfig


@dataclass(frozen=True)
class Head:
    sequence: int
    transactionId: TransactionId
    changeSha256: Sha256


@dataclass(frozen=True)
class ResourceRef:
    resourceType: str
    id: ResourceId
    versionId: RevisionId | None = None

    def __post_init__(self):
        if not re.fullmatch(r"[A-Z][A-Za-z0-9]{0,63}", self.resourceType):
            raise ArchiveError("INVALID_REFERENCE", "Invalid resource type.")
        uuid_string(self.id)
        if self.versionId is not None:
            uuid_string(self.versionId)


@dataclass(frozen=True)
class PersonDraft:
    displayName: str
    birthDate: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Literal["error", "review", "warning", "info"]
    pointer: str | None
    resourceRef: str | None
    message: str


@dataclass(frozen=True)
class CheckCoverage:
    family: str
    result: Literal["passed", "failed", "not-checked"]
    reason: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    checkedProposalSha256: Sha256 | None
    coverage: tuple[CheckCoverage, ...]
    issues: tuple[Issue, ...]


@dataclass(frozen=True)
class SourceReceipt:
    personId: PersonId
    sourceSha256: Sha256
    size: int
    mediaType: str
    assetPath: Path
    existingImport: TransactionId | None = None


@dataclass(frozen=True)
class ImportPacket:
    path: Path
    importId: str
    personId: PersonId
    source: SourceReceipt


@dataclass(frozen=True)
class Candidate:
    path: Path
    candidateId: str
    personId: PersonId
    base: Head | None
    bundle: JsonValue
    evidence: JsonValue
    unresolved: tuple[Issue, ...]


@dataclass(frozen=True)
class PreparedProposal:
    path: Path
    personId: PersonId
    candidateSha256: Sha256
    proposalSha256: Sha256
    base: Head | None
    validation: ValidationReport


@dataclass(frozen=True)
class ReviewDecision:
    confirmedPerson: bool
    decision: Literal["accept", "accept-with-acknowledged-limitations"]
    acknowledgedIssues: tuple[dict, ...]
    reviewerLabel: str


@dataclass(frozen=True)
class ReviewReceipt:
    path: Path
    proposalSha256: Sha256
    validationSha256: Sha256
    base: Head | None


@dataclass(frozen=True)
class CommitResult:
    disposition: Literal["committed", "already-accepted"]
    head: Head
    logicalResources: tuple[ResourceRef, ...]
