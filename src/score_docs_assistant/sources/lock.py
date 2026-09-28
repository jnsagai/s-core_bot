"""`data/source-lock.json`: atomic write, strict read, and verification of acquired files
(FR-003, FR-008; contracts/lock.md)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from score_docs_assistant.domain.errors import ConfigError
from score_docs_assistant.domain.ingestion import LockedSource, SourceLock
from score_docs_assistant.sources.paths import UnsafePathError, ensure_within, safe_relative_path

LOCK_FILENAME = "source-lock.json"


def source_root(data_dir: Path, source_id: str, revision: str) -> Path:
    return data_dir / "sources" / source_id / revision


def read_lock(path: Path) -> SourceLock:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError([(str(path), f"cannot read source lock: {exc}")]) from exc
    try:
        return SourceLock.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(
            [(".".join(str(p) for p in e["loc"]), e["msg"]) for e in exc.errors()]
        ) from exc


def write_lock(path: Path, lock: SourceLock) -> None:
    """temp file + fsync + os.replace: a crash leaves either the old lock or the new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(lock.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_files(root: Path, locked: LockedSource) -> list[str]:
    """Paths (relative) that are missing, unsafe, or whose content differs from the lock."""
    problems: list[str] = []
    for entry in [*locked.files, *locked.notice_files]:
        try:
            target = ensure_within(root, safe_relative_path(entry.path))
        except UnsafePathError:
            problems.append(entry.path)
            continue
        if not target.is_file() or file_sha256(target) != entry.sha256:
            problems.append(entry.path)
    return problems
