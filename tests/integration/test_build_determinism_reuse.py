"""Duplicate builds and embedding reuse (FR-005, FR-008, SC-002, research R6). Mocked provider."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from score_docs_assistant.storage.catalog import Catalog
from tests.helpers.build import build
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.snapshot_env import make_env


def _chunk_rows(data: Path, snapshot_id: str) -> list[tuple[object, ...]]:
    conn = sqlite3.connect(
        f"file:{data / 'snapshots' / snapshot_id / 'corpus.sqlite'}?mode=ro", uri=True
    )
    columns = [r[1] for r in conn.execute("PRAGMA table_info(chunks)") if r[1] != "rowid"]
    return conn.execute(f"SELECT {','.join(columns)} FROM chunks ORDER BY rowid").fetchall()


def test_two_builds_identical_chunks_and_full_reuse(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    provider = FakeEmbeddingProvider()
    first = build(env, provider)
    embedded_after_first = provider.embedded_count
    second = build(env, provider)
    assert first.snapshot_id != second.snapshot_id
    assert _chunk_rows(env.data, first.snapshot_id) == _chunk_rows(env.data, second.snapshot_id)
    assert provider.embedded_count == embedded_after_first  # zero new embedding requests
    assert second.counts.embedded_reused == second.counts.chunks
    assert second.counts.embedded_new == 0
    a = (env.data / "snapshots" / first.snapshot_id / "embeddings.f32").read_bytes()
    b = (env.data / "snapshots" / second.snapshot_id / "embeddings.f32").read_bytes()
    assert a == b


def test_identity_change_forces_full_reembedding(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    build(env, FakeEmbeddingProvider())
    other = FakeEmbeddingProvider(digest="e" * 64)
    result = build(env, other)
    assert result.counts.embedded_reused == 0
    assert other.embedded_count > 0


def test_reuse_skips_failed_and_deleted_snapshots(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    first = build(env, FakeEmbeddingProvider())
    catalog = Catalog.open(env.data, create=False)
    assert catalog is not None
    with catalog, catalog.transaction() as conn:
        conn.execute(
            "UPDATE snapshots SET state = 'deleted' WHERE snapshot_id = ?", (first.snapshot_id,)
        )
    provider = FakeEmbeddingProvider()
    result = build(env, provider)
    assert result.counts.embedded_reused == 0


def test_build_pins_reuse_sources_while_reading(tmp_path: Path, monkeypatch) -> None:
    from score_docs_assistant.storage import build as build_module

    env = make_env(tmp_path)
    first = build(env, FakeEmbeddingProvider())
    pinned: list[str] = []
    original = build_module.Pin

    class SpyPin(original):  # type: ignore[misc, valid-type]
        def __init__(self, data_dir: Path, snapshot_id: str) -> None:
            pinned.append(snapshot_id)
            super().__init__(data_dir, snapshot_id)

    monkeypatch.setattr(build_module, "Pin", SpyPin)
    build(env, FakeEmbeddingProvider())
    assert first.snapshot_id in pinned
