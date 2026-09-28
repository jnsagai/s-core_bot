"""Sync fixture repositories and normalize them — the full F002 pipeline without network."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx

from score_docs_assistant.ingestion.normalize import NormalizationOutcome, NormalizationService
from score_docs_assistant.sources.git_client import GitClient
from score_docs_assistant.sources.lock import read_lock
from score_docs_assistant.sources.sync import SyncService
from tests.helpers.registries import make_registry

REPO_ROOT = Path(__file__).parent.parent.parent
PROFILES = REPO_ROOT / "config" / "parser-profiles"
FILE_GIT = GitClient(allowed_protocols=frozenset({"file"}))


def sync(
    data: Path, sources: list[dict[str, Any]], http: httpx.Client | None = None, **limits: int
) -> int:
    registry = make_registry(sources, **limits)
    return SyncService(registry, data, git=FILE_GIT, http_client=http).run().exit_code


def normalize(data: Path, profiles: Path = PROFILES) -> NormalizationOutcome:
    lock_path = data / "source-lock.json"
    lock_sha = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    return NormalizationService(read_lock(lock_path), lock_sha, data, profiles).run()
