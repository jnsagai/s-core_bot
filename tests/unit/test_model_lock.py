"""Atomic lock write, unknown-field rejection, interrupted-pull safety, and compare outcomes
(FR-022, FR-023)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from score_docs_assistant.domain.models import (
    InstalledModel,
    ModelLock,
    ModelLockEntry,
    ModelLockRuntime,
)
from score_docs_assistant.models.lock import compare_role, read_lock, write_lock


def _lock(digest: str = "sha256:a") -> ModelLock:
    return ModelLock(
        profile="local-small",
        runtime=ModelLockRuntime(provider="ollama", version="0.34.0"),
        models=[
            ModelLockEntry(
                role="generation",
                tag="gen:latest",
                digest=digest,
                size_bytes=1,
                acquired_at=datetime.now(UTC),
            )
        ],
    )


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "model-lock.json"
    write_lock(path, _lock())
    loaded = read_lock(path)
    assert loaded is not None
    assert loaded.models[0].digest == "sha256:a"


def test_write_lock_is_atomic_temp_and_replace(tmp_path: Path) -> None:
    path = tmp_path / "model-lock.json"
    write_lock(path, _lock("sha256:first"))
    write_lock(path, _lock("sha256:second"))
    assert list(tmp_path.iterdir()) == [path]  # no leftover temp file
    assert read_lock(path).models[0].digest == "sha256:second"  # type: ignore[union-attr]


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ModelLock(
            profile="x",
            runtime=ModelLockRuntime(provider="ollama", version="0.34.0"),
            models=[],
            unexpected_field=True,  # type: ignore[call-arg]
        )


def test_interrupted_write_leaves_previous_lock_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "model-lock.json"
    write_lock(path, _lock("sha256:original"))
    before = path.read_bytes()

    def _raise_replace(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("os.replace", _raise_replace)
    with pytest.raises(KeyboardInterrupt):
        write_lock(path, _lock("sha256:new"))

    assert path.read_bytes() == before
    leftover_temp_files = [p for p in tmp_path.iterdir() if p != path]
    assert leftover_temp_files == []


def test_compare_outcomes() -> None:
    lock = _lock("sha256:a")
    installed_match = [InstalledModel(tag="gen:latest", digest="sha256:a", size_bytes=1)]
    installed_mismatch = [InstalledModel(tag="gen:latest", digest="sha256:different", size_bytes=1)]

    assert compare_role(lock, "generation", installed_match) == "match"
    assert compare_role(lock, "generation", installed_mismatch) == "mismatch"
    assert compare_role(lock, "generation", []) == "missing_installed"
    assert compare_role(None, "generation", installed_match) == "not_locked"
