"""corpus.sqlite schema, content and FTS (FR-006, research R4)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.snapshots import ChunkerConfig
from score_docs_assistant.ingestion.chunking import Chunker
from score_docs_assistant.storage.corpus_db import (
    expected_schema_objects,
    open_corpus_readonly,
    schema_objects,
    write_corpus,
)
from tests.helpers.normalized import normalize_env
from tests.helpers.snapshot_env import make_env


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, int], int]:
    tmp = tmp_path_factory.mktemp("corpus")
    env = make_env(tmp)
    outcome = normalize_env(env)
    chunks = Chunker(ChunkerConfig()).chunk_all(outcome.documents, outcome.entities)
    path = tmp / "corpus.sqlite"
    counts = write_corpus(
        path,
        snapshot_id="s1",
        documents=outcome.documents,
        entities=outcome.entities,
        chunks=chunks,
    )
    links = sum(len(e.links) for e in outcome.entities)
    return path, counts, links


def test_schema_version_journal_and_no_sidecars(corpus: tuple[Path, dict[str, int], int]) -> None:
    path, _, _ = corpus
    conn = open_corpus_readonly(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert schema_objects(conn) == expected_schema_objects()
    conn.close()
    assert sorted(p.name for p in path.parent.glob("corpus.sqlite*")) == ["corpus.sqlite"]


def test_counts_and_relations(corpus: tuple[Path, dict[str, int], int]) -> None:
    path, counts, links = corpus
    conn = open_corpus_readonly(path)
    assert counts["relations"] == links
    assert counts["chunks"] > 10
    rows = conn.execute("SELECT resolution FROM relations").fetchall()
    assert {r[0] for r in rows} <= {"resolved", "ambiguous", "unresolved", "malformed"}
    rowids = [r[0] for r in conn.execute("SELECT rowid FROM chunks ORDER BY rowid")]
    assert rowids == list(range(1, counts["chunks"] + 1))


@pytest.mark.parametrize(
    "query", ['"feat_req__alpha__short"', "need_ids:std_req__beta__one", '"MLE.3.BP1"', "watchdog"]
)
def test_fts_keeps_ids_as_tokens(corpus: tuple[Path, dict[str, int], int], query: str) -> None:
    path, _, _ = corpus
    conn = open_corpus_readonly(path)
    hits = conn.execute("SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH ?", (query,))
    count = hits.fetchone()[0]
    conn.close()
    if query == '"MLE.3.BP1"':
        assert count == 0  # absent from fixtures; must parse as one token without error
    else:
        assert count >= 1


def test_export_entities_stored_unverified(tmp_path: Path) -> None:
    from score_docs_assistant.domain.ingestion import Entity
    from tests.helpers.normalized import block, document

    entity = Entity(
        key="exp:x",
        need_id="x",
        type="feat_req",
        title="X",
        options={},
        links=[],
        source_id="exp",
        document_key="doc-key",
        path="needs.json",
        line_start=None,
        line_end=None,
        origin="needs-export",
        revision_status="unverified",
    )
    path = tmp_path / "c.sqlite"
    write_corpus(
        path,
        snapshot_id="s",
        documents=[document([block("paragraph", "p")])],
        entities=[entity],
        chunks=[],
    )
    conn = open_corpus_readonly(path)
    assert conn.execute("SELECT revision_status FROM entities").fetchone()[0] == "unverified"


def test_newer_schema_refused(tmp_path: Path) -> None:
    path = tmp_path / "c.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 2")
    conn.close()
    with pytest.raises(SnapshotError) as exc_info:
        open_corpus_readonly(path)
    assert exc_info.value.code == "SCHEMA_UNSUPPORTED"


def test_refuses_to_overwrite(corpus: tuple[Path, dict[str, int], int]) -> None:
    path, _, _ = corpus
    with pytest.raises(FileExistsError):
        write_corpus(path, snapshot_id="x", documents=[], entities=[], chunks=[])
