"""Local archive records. Clinical payloads remain FHIR JSON trees."""
from dataclasses import dataclass, field
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
    # Original context builder authority; host-only, excluded from document().
    trustedContextSha256: Sha256 | None = field(default=None, repr=False, compare=False)


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
    # Host control, never derived from untrusted packet authority.
    candidatePath: Path | None = field(default=None, repr=False, compare=False)


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
    receiptSha256: Sha256 | None = None


@dataclass(frozen=True)
class ReviewView:
    identitySummary: dict
    resourcesAdded: tuple[dict, ...]
    revisionsChanged: tuple[dict, ...]
    omissions: tuple[str, ...]
    duplicateCandidates: tuple[str, ...]
    sourceLinks: tuple[dict, ...]
    issues: tuple[dict, ...]
    validationCoverage: tuple[dict, ...]
    # Disposable comparisons resolved at the proposal's exact selected-person base.
    comparisons: tuple[dict, ...] = ()
    omittedResources: tuple[dict, ...] = ()


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
    includeSourceExtractions: bool = False

    def __post_init__(self):
        object.__setattr__(self, 'sourceHashes', tuple(self.sourceHashes))
        object.__setattr__(self, 'resourceRefs', tuple(self.resourceRefs))
        for digest in self.sourceHashes:
            sha256_string(digest)
        if (type(self.includeSourceExtractions) is not bool or
                type(self.maxRecords) is not int or self.maxRecords < 1 or
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
    # Instructions/records/evidence are packet-relative; contracts/sources are
    # absolute retained references. Identity/evidence sourcePath identifies the
    # disposable projection itself, never a broader original payload.
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
    # One budgeted evidenceSelection JSON per returned exact revision, in order.
    evidencePaths: tuple[ContextFile, ...]
    expectedChecks: tuple[str, ...]
    outputPaths: tuple[str, ...]
    # None only for retained pre-renderer context contracts which lack these fields.
    maxRecords: int | None = None
    maxDataBytes: int | None = None
    # Optional exact retained extraction reads, bound by original host authority.
    selectedExtractions: tuple[ContextFile, ...] = ()
    # Host-only builder receipt. Never serialized into the editable packet.
    trustedContextSha256: Sha256 | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    promptId: str
    promptVersion: str
    promptSha256: Sha256
    skillSha256: Sha256
    kitSha256: Sha256
    inputContractIds: tuple[str, ...]
    outputContractIds: tuple[str, ...]


@dataclass(frozen=True)
class IntakeLimits:
    sourceBytes: int = 104857600
    pdfPages: int = 500
    candidateResources: int = 10000
    jsonDepth: int = 64
    textFieldBytes: int = 1048576

    def __post_init__(self):
        if any(type(value) is not int or value <= 0 for value in (
                self.sourceBytes, self.pdfPages, self.candidateResources,
                self.jsonDepth, self.textFieldBytes)):
            raise ArchiveError("INVALID_LIMIT", "Intake limits must be positive integers.")


@dataclass(frozen=True)
class ExtractionArtifact:
    method: str
    toolVersion: str
    pagesPath: Path
    pagesSha256: Sha256
    pageCount: int
    issues: tuple[Issue, ...]


@dataclass(frozen=True)
class ObservationFilter:
    codeSystem: str | None = None
    code: str | None = None
    exactSourceLabel: str | None = None
    fromDate: str | None = None
    toDate: str | None = None
    includeInvalidated: bool = False

    def __post_init__(self):
        for value in (self.codeSystem, self.code, self.exactSourceLabel):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ArchiveError('INVALID_FILTER', 'Code selectors and labels must be nonempty strings.')
        if type(self.includeInvalidated) is not bool:
            raise ArchiveError('INVALID_FILTER', 'includeInvalidated must be boolean.')
        # Query owns all calendar/interval rules, including context filters.
        from .query import _date_window
        _date_window(self.fromDate, self.toDate)


@dataclass(frozen=True)
class EvidenceRef:
    """Exact accepted entry binding; does not project free text from whole evidence."""
    evidencePath: str
    evidenceSha256: Sha256
    entryPointer: str
    sourceSha256: Sha256 | None
    sourceDocument: str | None


@dataclass(frozen=True)
class ObservationRow:
    resourceRef: ResourceRef
    effective: JsonValue
    timePrecision: str
    timeFilterRelation: Literal['contained', 'overlap', 'unknown']
    code: JsonValue
    value: JsonValue
    unit: str | None
    comparator: str | None
    referenceRanges: JsonValue
    method: JsonValue
    specimenRef: JsonValue
    status: str | None
    sourceRefs: tuple[EvidenceRef, ...]
    issues: tuple[Issue, ...]
    valueType: str | None
    effectiveType: str | None
    timeBucket: Literal['dated', 'unknown']
    component: JsonValue
    dataAbsentReason: JsonValue
    note: JsonValue
    interpretation: JsonValue
    hasMember: JsonValue
    derivedFrom: JsonValue


@dataclass(frozen=True)
class TimelineRow:
    resourceRef: ResourceRef
    status: str | None
    effective: JsonValue
    timePrecision: str
    timeBucket: Literal['dated', 'unknown']
    effectiveType: str | None
    resultRefs: tuple[ResourceRef, ...]
    sourceRefs: tuple[EvidenceRef, ...]
    issues: tuple[Issue, ...]


@dataclass(frozen=True)
class IntegrityReport:
    issues: tuple[Issue, ...]
    checkedChanges: int
    checkedResources: int
    checkedAssets: int
    orphanPaths: tuple[str, ...]


@dataclass(frozen=True)
class ExportSelection:
    mode: Literal['full-person', 'selected-current']
    resourceRefs: tuple[ResourceRef, ...] = ()
    includeSources: bool = True

    def __post_init__(self):
        if self.mode not in ('full-person', 'selected-current') or type(self.includeSources) is not bool:
            raise ArchiveError('INVALID_INPUT', 'Invalid export selection.')
        if self.mode == 'full-person' and (self.resourceRefs or not self.includeSources):
            raise ArchiveError('INVALID_INPUT', 'Full-person retains all history and sources; use selected-current for omissions.')


@dataclass(frozen=True)
class ExportReceipt:
    path: Path
    manifestSha256: Sha256
    peopleCount: int
    resourceCount: int
    assetCount: int
    omissions: tuple[str, ...]
