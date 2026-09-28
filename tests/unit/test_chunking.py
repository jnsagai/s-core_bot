"""Chunking golden rules (FR-001–FR-004, research R3)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.snapshots import Chunk, ChunkerConfig
from score_docs_assistant.ingestion.chunking import Chunker
from score_docs_assistant.ingestion.tokens import estimate_tokens
from tests.helpers.normalized import block, document, normalize_env
from tests.helpers.snapshot_env import SHARED_PARAGRAPH, make_env

CONFIG = ChunkerConfig()


@pytest.fixture(scope="module")
def fixture_chunks(tmp_path_factory: pytest.TempPathFactory) -> list[Chunk]:
    env = make_env(tmp_path_factory.mktemp("chunks"))
    outcome = normalize_env(env)
    return Chunker(CONFIG).chunk_all(outcome.documents, outcome.entities)


def _by_heading(chunks: list[Chunk], heading: str) -> list[Chunk]:
    return [c for c in chunks if c.heading_path and c.heading_path[-1] == heading]


def test_short_need_is_one_chunk_with_key_and_options(fixture_chunks: list[Chunk]) -> None:
    [short] = [c for c in fixture_chunks if c.entity_keys == ["alpha:feat_req__alpha__short"]]
    assert short.kind == "need"
    assert short.continuation is None
    assert short.need_ids == ["feat_req__alpha__short"]
    assert ":status: valid" in short.text
    assert ":satisfies: feat_req__alpha__long" in short.text
    assert "The short requirement fits in one chunk." in short.text


def test_long_need_splits_into_keyed_continuations(fixture_chunks: list[Chunk]) -> None:
    parts = [c for c in fixture_chunks if c.entity_keys == ["alpha:feat_req__alpha__long"]]
    assert len(parts) > 1
    assert [p.continuation for p in parts] == [
        f"{i}/{len(parts)}" for i in range(1, len(parts) + 1)
    ]
    assert all(p.kind == "need" and p.token_estimate <= CONFIG.max_tokens for p in parts)
    joined = "\n\n".join(p.text for p in parts)
    for part_no in range(1, 9):
        assert f"component part {part_no} behaves" in joined


def test_prose_never_crosses_sections_and_small_sections_stay_separate(
    fixture_chunks: list[Chunk],
) -> None:
    [a] = _by_heading(fixture_chunks, "Small Section A")
    [b] = _by_heading(fixture_chunks, "Small Section B")
    assert a.text == "Only a little text in section A."
    assert b.text == "Only a little text in section B."
    assert all(len({tuple(c.heading_path)}) == 1 for c in fixture_chunks)


def test_table_pieces_repeat_header_and_record_rows(fixture_chunks: list[Chunk]) -> None:
    tables = [c for c in fixture_chunks if c.kind == "table"]
    assert len(tables) > 1
    assert all(t.text.startswith("Signal | Description\n") for t in tables)
    ranges = [t.table_rows for t in tables]
    assert ranges[0] is not None and ranges[0][0] == 0
    assert ranges[-1] is not None and ranges[-1][1] == 59
    for prev, nxt in zip(ranges, ranges[1:], strict=False):
        assert prev is not None and nxt is not None and nxt[0] == prev[1] + 1
    body_rows = sum(len(t.text.split("\n")) - 1 for t in tables)
    assert body_rows == 60


def test_code_split_only_at_line_boundaries(fixture_chunks: list[Chunk]) -> None:
    code = [c for c in fixture_chunks if c.kind == "code"]
    assert len(code) > 1
    lines = [line for c in code for line in c.text.split("\n")]
    assert lines == [f"int value_{i} = compute({i}); // step {i}" for i in range(200)]
    assert code[-1].continuation == f"{len(code)}/{len(code)}"


def test_long_paragraph_sentence_split_with_overlap(fixture_chunks: list[Chunk]) -> None:
    parts = _by_heading(fixture_chunks, "Long Prose")
    assert len(parts) > 1
    for prev, nxt in zip(parts, parts[1:], strict=False):
        prev_sentences = re.split(r"(?<=\.)\s+", prev.text)
        overlap = [s for s in re.split(r"(?<=\.)\s+", nxt.text) if s in prev_sentences]
        overlap_tokens = sum(estimate_tokens(s) - 2 for s in overlap)
        assert 50 <= overlap_tokens <= 100
        assert nxt.text.startswith(overlap[0])


def test_excluded_and_dynamic_content_contribute_no_text(fixture_chunks: list[Chunk]) -> None:
    text = "\n".join(c.text for c in fixture_chunks)
    assert "<script>" not in text
    assert "alert(" not in text
    assert ":types: feat_req" not in text


def test_display_text_is_verbatim_and_prefix_only_in_embedding_input(
    fixture_chunks: list[Chunk],
) -> None:
    for chunk in fixture_chunks:
        assert not chunk.text.startswith(("search_document:", "Title:"))
        assert chunk.embedding_input.startswith("search_document: Title: ")
        assert chunk.embedding_input.endswith("\n\n" + chunk.text)
        assert chunk.embedding_token_estimate <= CONFIG.embedding_max_input_tokens
    [short] = [c for c in fixture_chunks if c.entity_keys == ["alpha:feat_req__alpha__short"]]
    assert "IDs: feat_req__alpha__short" in short.embedding_input
    assert "Source: alpha (rst)" in short.embedding_input


def test_identical_text_in_two_sources(fixture_chunks: list[Chunk]) -> None:
    shared = [c for c in fixture_chunks if c.text == SHARED_PARAGRAPH]
    assert {c.source_id for c in shared} == {"alpha", "beta"}
    assert len({c.content_hash for c in shared}) == 1
    assert len({c.chunk_id for c in shared}) == 2


def test_no_text_lost(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    outcome = normalize_env(env)
    chunks = Chunker(CONFIG).chunk_all(outcome.documents, outcome.entities)
    for doc in outcome.documents:
        combined = "\n".join(c.text for c in chunks if c.document_key == doc.document_key)

        def check(blocks: list, doc_path: str = doc.path, combined: str = combined) -> None:
            for b in blocks:
                if b.kind in ("dynamic_view", "raw_excluded"):
                    continue
                if b.kind in ("paragraph", "code", "literal", "diagram"):
                    for sentence in b.text.split(". "):
                        assert sentence in combined, (doc_path, sentence[:60])
                check(b.children, doc_path, combined)

        check(doc.blocks)


def test_export_documents_yield_no_chunks() -> None:
    doc = document([]).model_copy(update={"format": "needs-export"})
    assert Chunker(CONFIG).chunk_document(doc, {}) == []


def test_oversize_word_within_cap_is_kept_whole() -> None:
    word = "x" * 1600  # 800 estimated tokens: over max_tokens, under the cap
    [chunk] = Chunker(CONFIG).chunk_document(document([block("paragraph", word)]), {})
    assert chunk.text == word


def test_unsplittable_over_cap_fails_naming_location() -> None:
    word = "x" * 4000
    with pytest.raises(SnapshotError) as exc_info:
        Chunker(CONFIG).chunk_document(document([block("paragraph", word)]), {})
    assert exc_info.value.code == "CHUNK_UNSPLITTABLE"
    assert "docs/x.rst:1" in exc_info.value.message


def test_code_line_over_cap_fails() -> None:
    code = "short line\n" + ("y" * 4000)
    with pytest.raises(SnapshotError) as exc_info:
        Chunker(CONFIG).chunk_document(document([block("code", code)]), {})
    assert exc_info.value.code == "CHUNK_UNSPLITTABLE"


def test_prefix_is_elided_to_its_budget() -> None:
    heading = [f"Heading level {i} with a fairly long descriptive title" for i in range(30)]
    [chunk] = Chunker(CONFIG).chunk_document(
        document([block("paragraph", "Body text.", heading=heading)]), {}
    )
    prefix = chunk.embedding_input[len(CONFIG.document_prefix) : -len("\n\nBody text.")]
    assert estimate_tokens(prefix) <= CONFIG.prefix_max_tokens
    assert "…" in prefix
    assert chunk.heading_path == heading


def test_nested_need_inside_need_is_its_own_chunk() -> None:
    inner = block("need", "Inner", entity_key="s:inner", attrs={"options": {"id": "inner"}})
    outer = block(
        "need",
        "Outer",
        entity_key="s:outer",
        attrs={"options": {"id": "outer"}},
        children=[block("paragraph", "Outer body."), inner],
    )
    chunks = Chunker(CONFIG).chunk_document(document([outer]), {"s:inner": "inner"})
    assert [c.entity_keys for c in chunks] == [["s:outer"], ["s:inner"]]
    assert "Inner" not in chunks[0].text
    assert chunks[1].need_ids == ["inner"]
