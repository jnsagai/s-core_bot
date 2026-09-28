"""`BuildService` end to end on synthetic sources (FR-009–FR-012, US1 AS1/AS7). Mocked provider."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.storage.catalog import Catalog
from tests.helpers.build import build
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.snapshot_env import SourceSpec, default_sources, make_env

CONTRACT_FILES = {
    "manifest.json",
    "corpus.sqlite",
    "embeddings.f32",
    "embedding-manifest.json",
    "reports/coverage.json",
    "reports/build-validation.json",
}


def _files(directory: Path) -> set[str]:
    return {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}


def test_build_publishes_validated_snapshot(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    result = build(env)
    snapshot = env.data / "snapshots" / result.snapshot_id
    assert result.state == "validated" and result.semantic == "present"
    assert _files(snapshot) == CONTRACT_FILES
    assert all(p.stat().st_mode & 0o777 == 0o444 for p in snapshot.rglob("*") if p.is_file())
    assert not any((env.data / "staging").iterdir())

    manifest = json.loads((snapshot / "manifest.json").read_text())
    for key in (
        "lock_sha256",
        "source_revisions",
        "processing_hashes",
        "chunker_version",
        "chunker_config_sha256",
        "token_count_method",
        "embedding",
        "files",
        "counts",
        "coverage",
        "license_review",
    ):
        assert manifest[key], key
    assert manifest["source_revisions"] == {"alpha": "a" * 40, "beta": "b" * 40}
    assert manifest["token_count_method"] == "pretoken-v1"
    assert [e["path"] for e in manifest["license_review"]] == ["docs/sharealike.rst"]
    assert manifest["counts"]["documents_without_chunks"] == 0
    assert {f["path"] for f in manifest["files"]} == CONTRACT_FILES - {"manifest.json"}

    conn = sqlite3.connect(f"file:{snapshot / 'corpus.sqlite'}?mode=ro", uri=True)
    for table in ("documents", "entities", "relations", "chunks"):
        count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        assert count == manifest["counts"][table]

    with Catalog.open(env.data, create=False) as catalog:  # type: ignore[union-attr]
        row = catalog.get(result.snapshot_id)
        assert row is not None and row.state == "validated"
        assert catalog.active_id() is None  # never activated without --activate


def test_required_source_failed_stops_before_chunking(tmp_path: Path) -> None:
    sources = default_sources()
    sources[1] = SourceSpec("beta", {}, revision="b" * 40, status="failed")
    env = make_env(tmp_path, sources)
    stages: list[str] = []
    with pytest.raises(SnapshotError) as exc_info:
        build(env, stage_hook=stages.append)
    assert exc_info.value.code == "REQUIRED_SOURCE_FAILED"
    assert "beta" in exc_info.value.message
    assert stages == []


def test_required_source_missing_on_disk(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    (env.data / "sources" / "beta" / ("b" * 40) / "docs" / "shared.rst").unlink()
    with pytest.raises(SnapshotError) as exc_info:
        build(env)
    assert exc_info.value.code == "REQUIRED_SOURCE_FAILED"


def test_optional_source_failure_becomes_limitation(tmp_path: Path) -> None:
    sources = [
        *default_sources(),
        SourceSpec("gamma", {}, "c" * 40, required=False, status="failed"),
    ]
    env = make_env(tmp_path, sources)
    result = build(env)
    manifest = json.loads(
        (env.data / "snapshots" / result.snapshot_id / "manifest.json").read_text()
    )
    assert any("gamma" in item for item in manifest["coverage"]["limitations"])


def test_low_disk_refused_before_staging(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    with pytest.raises(SnapshotError) as exc_info:
        build(env, free=1)
    assert exc_info.value.code == "DISK_INSUFFICIENT"
    assert not (env.data / "staging").exists()
    assert Catalog.open(env.data, create=False).jobs() == []  # type: ignore[union-attr]


@pytest.mark.parametrize("mode", ["wrong_dimension", "nan"])
def test_invalid_vectors_fail_the_build(tmp_path: Path, mode: str) -> None:
    env = make_env(tmp_path)
    with pytest.raises(SnapshotError) as exc_info:
        build(env, FakeEmbeddingProvider(mode=mode))
    assert exc_info.value.code == "EMBEDDING_INVALID_VECTOR"
    with Catalog.open(env.data, create=False) as catalog:  # type: ignore[union-attr]
        [snapshot] = catalog.snapshots()
        assert snapshot.state == "failed"
    assert (
        not list((env.data / "snapshots").glob("*")) if (env.data / "snapshots").exists() else True
    )


def test_runtime_unavailable_fails_without_lexical_flag(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    with pytest.raises(SnapshotError) as exc_info:
        build(env, FakeEmbeddingProvider(mode="unreachable"))
    assert exc_info.value.code == "EMBEDDING_UNAVAILABLE"
    assert "--lexical-only" in exc_info.value.message


def test_lexical_only_snapshot(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    provider = FakeEmbeddingProvider(mode="unreachable")
    result = build(env, provider, lexical_only=True)
    snapshot = env.data / "snapshots" / result.snapshot_id
    assert result.semantic == "absent"
    assert "embeddings.f32" not in _files(snapshot)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    assert manifest["semantic"] == "absent" and manifest["embedding"] is None
    conn = sqlite3.connect(f"file:{snapshot / 'corpus.sqlite'}?mode=ro", uri=True)
    hits = conn.execute("SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'watchdog'")
    assert hits.fetchone()[0] > 0
    assert provider.calls == []


def test_model_lock_digest_mismatch_is_unavailable(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    from tests.helpers.snapshot_env import write_model_lock

    write_model_lock(env.data, "9" * 64)
    with pytest.raises(SnapshotError) as exc_info:
        build(env, write_lock=False)
    assert exc_info.value.code == "EMBEDDING_UNAVAILABLE"


def test_too_long_input_fails_naming_chunk(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    with pytest.raises(SnapshotError) as exc_info:
        build(env, FakeEmbeddingProvider(too_long_chars=1000))
    assert exc_info.value.code == "EMBEDDING_INPUT_TOO_LONG"
    assert "alpha:docs/" in exc_info.value.message


def test_second_concurrent_build_is_busy(tmp_path: Path) -> None:
    from tests.helpers.procs import hold_ingest_lock, kill9

    env = make_env(tmp_path)
    proc = hold_ingest_lock(env.data, tmp_path)
    try:
        with pytest.raises(SnapshotError) as exc_info:
            build(env)
        assert exc_info.value.code == "BUILD_BUSY"
    finally:
        kill9(proc)


def test_document_without_chunkable_text_is_counted(tmp_path: Path) -> None:
    sources = default_sources()
    files = dict(sources[1].files)
    files["docs/only-dynamic.rst"] = (
        ".. SPDX-License-Identifier: Apache-2.0\n\n.. needtable::\n   :types: std_req\n"
    )
    sources[1] = SourceSpec("beta", files, revision="b" * 40)
    env = make_env(tmp_path, sources)
    result = build(env)
    assert result.counts.documents_without_chunks == 1
