"""Read, compare, and atomically write `<data_dir>/model-lock.json`."""

from __future__ import annotations

import json
import os
import tempfile
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


def write_lock(path: Path, lock: ModelLock) -> None:
    """Write via temp file + fsync + os.replace so a crash or KeyboardInterrupt never leaves a
    partially written lock — the previous file is either fully replaced or untouched."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(lock.model_dump_json(indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


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
