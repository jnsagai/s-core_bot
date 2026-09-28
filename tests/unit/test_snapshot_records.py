"""Snapshot domain records (data-model.md)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from score_docs_assistant.domain.snapshots import (
    ChunkerConfig,
    CoverageSummary,
    EmbeddingIdentity,
    ManifestCounts,
    SnapshotManifest,
    chunk_id,
    preprocessing_revision,
)

IDENTITY = EmbeddingIdentity(
    provider="ollama",
    model_tag="nomic-embed-text:latest",
    model_digest="a" * 64,
    dimension=768,
    preprocessing_revision="p" * 64,
)


def test_identity_equality_over_all_fields() -> None:
    assert IDENTITY.model_copy() == IDENTITY
    for field, value in [
        ("provider", "x"),
        ("model_tag", "x:latest"),
        ("model_digest", "b" * 64),
        ("dimension", 384),
        ("preprocessing_revision", "q" * 64),
        ("normalization", "none"),
    ]:
        assert IDENTITY.model_copy(update={field: value}) != IDENTITY


def test_records_are_frozen_and_reject_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        IDENTITY.dimension = 3  # type: ignore[misc]
    with pytest.raises(ValidationError):
        EmbeddingIdentity(**IDENTITY.model_dump(), extra="x")  # type: ignore[arg-type]


def test_chunk_id_stable_and_sensitive() -> None:
    base = chunk_id("1", "doc", 0, "h")
    assert base == chunk_id("1", "doc", 0, "h")
    assert (
        len(
            {
                base,
                chunk_id("2", "doc", 0, "h"),
                chunk_id("1", "doc2", 0, "h"),
                chunk_id("1", "doc", 1, "h"),
                chunk_id("1", "doc", 0, "h2"),
            }
        )
        == 5
    )


def test_chunker_config_hash_and_preprocessing_revision() -> None:
    config = ChunkerConfig()
    assert config.sha256() == ChunkerConfig().sha256()
    assert config.sha256() != ChunkerConfig(max_tokens=600).sha256()
    assert preprocessing_revision(config) == preprocessing_revision(ChunkerConfig(max_tokens=600))
    assert preprocessing_revision(config) != preprocessing_revision(
        ChunkerConfig(document_prefix="")
    )


def test_manifest_round_trip() -> None:
    manifest = SnapshotManifest(
        schema_version=1,
        snapshot_id="20260928T000000Z-00000000",
        created_at=datetime(2026, 9, 28, tzinfo=UTC),
        app_version="0.1.0",
        lock_sha256="l" * 64,
        source_revisions={"s": "r"},
        sources=[],
        processing_hashes={},
        chunker_version="1",
        chunker_config_sha256=ChunkerConfig().sha256(),
        token_count_method="pretoken-v1",
        semantic="present",
        embedding=IDENTITY,
        embedding_context_tokens=2048,
        counts=ManifestCounts(documents=0, entities=0, relations=0, chunks=0, chunks_by_kind={}),
        coverage=CoverageSummary(sources=[], limitations=[]),
        license_review=[],
        corpus_schema_version=1,
        files=[],
    )
    assert SnapshotManifest.model_validate_json(manifest.model_dump_json()) == manifest
