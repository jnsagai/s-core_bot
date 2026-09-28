"""Build several snapshots and drive lifecycle operations in tests (mocked provider)."""

from __future__ import annotations

from pathlib import Path

from score_docs_assistant.storage import lifecycle
from score_docs_assistant.storage.catalog import Catalog
from tests.helpers.build import app_config, build
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.snapshot_env import SnapshotEnv

MESSAGES: list[str] = []


def snapshots(env: SnapshotEnv, count: int, **kwargs: object) -> list[str]:
    return [build(env, **kwargs).snapshot_id for _ in range(count)]  # type: ignore[arg-type]


def activate(env: SnapshotEnv, snapshot_id: str, runtime=None, **index: object) -> list[str]:  # type: ignore[no-untyped-def]
    return lifecycle.activate(
        config=app_config(env.data, **index),
        snapshot_id=snapshot_id,
        runtime=runtime if runtime is not None else FakeEmbeddingProvider(),
        progress=MESSAGES.append,
    )


def rollback(env: SnapshotEnv, **index: object) -> list[str]:
    return lifecycle.rollback(
        config=app_config(env.data, **index),
        runtime=FakeEmbeddingProvider(),
        progress=MESSAGES.append,
    )


def state(env: SnapshotEnv, snapshot_id: str) -> str:
    with Catalog.open(env.data, create=False) as catalog:  # type: ignore[union-attr]
        row = catalog.get(snapshot_id)
        assert row is not None
        return row.state


def active(env: SnapshotEnv) -> str | None:
    with Catalog.open(env.data, create=False) as catalog:  # type: ignore[union-attr]
        return catalog.active_id()


def snapshot_dir(env: SnapshotEnv, snapshot_id: str) -> Path:
    return env.data / "snapshots" / snapshot_id


def build_and_activate(env: SnapshotEnv, count: int) -> list[str]:
    """Build and activate one snapshot at a time (retention runs after each activation)."""
    ids: list[str] = []
    for _ in range(count):
        [snapshot_id] = snapshots(env, 1)
        activate(env, snapshot_id)
        ids.append(snapshot_id)
    return ids
