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


AgentTask: TypeAlias = Literal['inspect', 'import', 'query', 'correct', 'export', 'verify', 'migrate']


@dataclass(frozen=True)
class ContextContinuation:
    personId: PersonId
    taskId: AgentTask
    base: Head
    requestSha256: Sha256
    offset: int


@dataclass(frozen=True)
class ContextRequest:
    sourceHashes: tuple[Sha256, ...] = ()
    resourceRefs: tuple[ResourceRef, ...] = ()
    fromDate: str | None = None
    toDate: str | None = None
    maxRecords: int = 100
    maxDataBytes: int = 262144
    continuation: ContextContinuation | None = None

    def __post_init__(self):
        object.__setattr__(self, 'sourceHashes', tuple(self.sourceHashes))
        object.__setattr__(self, 'resourceRefs', tuple(self.resourceRefs))
        for digest in self.sourceHashes:
            sha256_string(digest)
        if (type(self.maxRecords) is not int or self.maxRecords < 1 or
                type(self.maxDataBytes) is not int or self.maxDataBytes < 1 or
                any(not isinstance(ref, ResourceRef) for ref in self.resourceRefs)):
            raise ArchiveError('INVALID_INPUT', 'Context limits must be positive integers and references typed.')


@dataclass(frozen=True)
class CapabilityAvailability:
    status: Literal['available', 'unavailable']
    missingCapabilities: tuple[str, ...]


@dataclass(frozen=True)
class AgentTaskDescriptor:
    id: AgentTask
    intent: str
    skillPath: str | None
    promptIds: tuple[str, ...]
    requiredInputs: tuple[str, ...]
    optionalInputs: tuple[str, ...]
    outputs: tuple[str, ...]
    permittedOperations: tuple[str, ...]
    requiredCapabilities: tuple[str, ...]
    availability: CapabilityAvailability
    referencePaths: tuple[str, ...]
    schemaPaths: tuple[str, ...]
    expectedChecks: tuple[str, ...]
    scenarioId: str


@dataclass(frozen=True)
class ContextFile:
    # Instructions/records are packet-relative; contracts/sources are absolute
    # references into the retained vault. sourcePath always identifies exact bytes.
    path: str
    sha256: Sha256
    size: int
    sourcePath: str


@dataclass(frozen=True)
class AgentContext:
    path: Path
    manifestSha256: Sha256
    personId: PersonId
    base: Head
    taskId: AgentTask
    kitVersion: str
    protocolVersion: int
    instructionPaths: tuple[ContextFile, ...]
    contractPaths: tuple[ContextFile, ...]
    selectedSources: tuple[ContextFile, ...]
    selectedRecords: tuple[ContextFile, ...]
    returnedCount: int
    continuation: ContextContinuation | None
    issues: tuple[Issue, ...]
    totalCount: int
    dataBytes: int
    instructionBytes: int
    identity: ContextFile
    availability: CapabilityAvailability
    permittedOperations: tuple[str, ...]
    kitManifest: ContextFile
    evidencePaths: tuple[ContextFile, ...]
    expectedChecks: tuple[str, ...]
    outputPaths: tuple[str, ...]
