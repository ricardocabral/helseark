"""Offline kit closure and bounded, explicit-person context packets.

Only manifest-listed instructions are loadable. Clinical/source content never
participates in routing. Packets are disposable read snapshots, not authority,
permission grants or agent execution. Task4 owns prompt rendering.
"""
from dataclasses import asdict, is_dataclass, replace
from collections.abc import Mapping
import hashlib
from pathlib import Path
import re
import shutil
from uuid import uuid4

from jsonschema import Draft202012Validator

from .archive import _bundled_root, _safe, _read, _history, head, resolve
from .contracts import (ArchiveError, Vault, ResourceRef, AgentTask, ContextRequest,
    AgentTaskDescriptor, CapabilityAvailability, ContextFile, ContextContinuation,
    AgentContext, ImportPacket, RenderedPrompt, Issue, Head, FHIRResource, JsonValue, uuid_string, sha256_string)
from .serialization import decode_json, decode_canonical_json, encode_json, hash_bytes
from .validation import DefinitionRegistry, load_definition_registry, _pointer, _walk

_TASKS = frozenset(('inspect', 'import', 'query', 'correct', 'export', 'verify', 'migrate'))
_CAPABILITIES = frozenset(('agent-discovery', 'agent-context', 'schema-export',
    'baseline-validation', 'person-identity', 'raw-record-selection', 'pdf-intake', 'candidate-read', 'clinical-query', 'reviewed-publication'))
