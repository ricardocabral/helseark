"""Small CLI; all archive behavior is shared with the library."""
import argparse
from dataclasses import asdict
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from .archive import init_vault, open_vault, open_definitions, add_person, _json, _open_vault_metadata, _bundled_root
from .contracts import ArchiveError, PersonDraft, uuid_string, ResourceRef, ContextRequest, ContextContinuation, Head
from .query import observations, timeline, parse_reference
from .archive import resolve
from .contracts import ObservationFilter
from .intake import add_source, build_packet, read_candidate, prepare_candidate
from .review import read_prepared, render_review, record_review, read_receipt
from .contracts import ReviewDecision
from .archive import commit_candidate
