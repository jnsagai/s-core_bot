"""Read and compare `<data_dir>/model-lock.json` (F001: read-only; atomic write added by T052)."""

from __future__ import annotations

import json
from pathlib import Path

from score_docs_assistant.domain.models import (
    InstalledModel,
    LockCompareStatus,
    ModelLock,
    ModelRole,
)

from .runtime import normalize_tag


def read_lock(path: Path) -> ModelLock | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return ModelLock(**data)


def compare_role(
    lock: ModelLock | None, role: ModelRole, installed: list[InstalledModel]
) -> LockCompareStatus:
    entry = lock.entry_for_role(role) if lock is not None else None
    if entry is None:
        return "not_locked"
    match = next((m for m in installed if m.tag == normalize_tag(entry.tag)), None)
    if match is None:
        return "missing_installed"
    if match.digest != entry.digest:
        return "mismatch"
    return "match"
