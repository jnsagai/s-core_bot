"""RetrievalConfig additions (specs/004-hybrid-search/data-model.md)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from score_docs_assistant.config.loader import load_config
from score_docs_assistant.config.schema import RetrievalConfig

REPO_ROOT = Path(__file__).parent.parent.parent


def test_defaults() -> None:
    config = RetrievalConfig()
    assert (config.lexical_candidates, config.semantic_candidates) == (30, 30)
    assert (config.evidence_chunks, config.fusion_constant) == (8, 60)
    assert config.max_limit == 20
    assert config.max_per_document == 3
    assert config.excerpt_characters == 1200
    assert config.max_concurrent_searches == 4
    assert config.semantic_status_ttl_seconds == 30


@pytest.mark.parametrize(
    "values",
    [
        {"max_limit": 5},  # below evidence_chunks (8)
        {"max_per_document": 0},
        {"excerpt_characters": 199},
        {"excerpt_characters": 10001},
        {"max_concurrent_searches": 0},
        {"max_concurrent_searches": 65},
        {"semantic_status_ttl_seconds": -1},
        {"semantic_status_ttl_seconds": 3601},
    ],
)
def test_invalid(values: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        RetrievalConfig(**values)


def test_local_config_loads() -> None:
    config = load_config(
        config_path=REPO_ROOT / "config" / "local.yaml", env={}, cwd=REPO_ROOT / "config"
    ).config
    assert config.retrieval.max_limit == 20
