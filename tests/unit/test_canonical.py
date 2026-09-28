"""Canonical serialization, processing hash and document keys (FR-017, research R9)."""

from __future__ import annotations

import pytest

from score_docs_assistant.ingestion.canonical import (
    CANONICAL_VERSION,
    PARSER_VERSION,
    canonical_hash,
    canonical_json,
    document_key,
    library_versions,
    processing_hash,
)


def test_canonical_bytes_sorted_compact_and_utf8() -> None:
    assert (
        canonical_json({"b": 1, "a": ["ü", None, True]}) == '{"a":["ü",null,true],"b":1}'.encode()
    )


def test_key_order_does_not_change_hash() -> None:
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})


def test_floats_rejected_anywhere() -> None:
    with pytest.raises(TypeError):
        canonical_json({"a": [1, {"b": 1.5}]})


def test_processing_hash_components() -> None:
    versions = library_versions()
    assert set(versions) == {"docutils", "markdown-it-py"}
    base = processing_hash("p" * 64, versions)
    assert processing_hash("p" * 64, versions) == base
    assert processing_hash("q" * 64, versions) != base
    assert processing_hash("p" * 64, {**versions, "docutils": "0.0"}) != base
    assert isinstance(PARSER_VERSION, str) and CANONICAL_VERSION == 1


def test_document_key_depends_on_every_input() -> None:
    args = ("src", "docs/a.rst", "r" * 64, "h" * 64)
    key = document_key(*args)
    assert document_key(*args) == key
    for i in range(4):
        changed = list(args)
        changed[i] = changed[i] + "x"
        assert document_key(*changed) != key
