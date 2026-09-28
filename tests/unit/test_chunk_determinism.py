"""Deterministic chunk records (FR-005, SC-002)."""

from __future__ import annotations

from pathlib import Path

from score_docs_assistant.domain.snapshots import ChunkerConfig
from score_docs_assistant.ingestion.canonical import canonical_json
from score_docs_assistant.ingestion.chunking import Chunker
from tests.helpers.normalized import normalize_env
from tests.helpers.snapshot_env import make_env


def _records(tmp_path: Path, config: ChunkerConfig) -> list[bytes]:
    env = make_env(tmp_path)
    outcome = normalize_env(env)
    chunks = Chunker(config).chunk_all(outcome.documents, outcome.entities)
    return [canonical_json(c.model_dump(mode="json")) for c in chunks]


def test_same_input_gives_byte_identical_records(tmp_path: Path) -> None:
    first = _records(tmp_path / "a", ChunkerConfig())
    second = _records(tmp_path / "b", ChunkerConfig())
    assert first == second
    assert first


def test_config_change_changes_hashes(tmp_path: Path) -> None:
    base = ChunkerConfig()
    tuned = ChunkerConfig(max_tokens=600)
    assert base.sha256() != tuned.sha256()
    assert _records(tmp_path / "a", base) != _records(tmp_path / "b", tuned)


def test_chunker_version_changes_every_id(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    outcome = normalize_env(env)
    v1 = Chunker(ChunkerConfig()).chunk_all(outcome.documents, outcome.entities)
    v2 = Chunker(ChunkerConfig(chunker_version="2")).chunk_all(outcome.documents, outcome.entities)
    assert not {c.chunk_id for c in v1} & {c.chunk_id for c in v2}
    assert [c.content_hash for c in v1] == [c.content_hash for c in v2]
