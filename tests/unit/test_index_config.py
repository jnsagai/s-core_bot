"""IndexConfig / BundleConfig defaults and constraints (specs/003-snapshot-index/data-model.md)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from score_docs_assistant.config.loader import load_config
from score_docs_assistant.config.schema import AppConfig, BundleConfig, IndexConfig

REPO_ROOT = Path(__file__).parent.parent.parent


def test_defaults_match_data_model() -> None:
    index = IndexConfig()
    assert (index.chunk_min_tokens, index.chunk_max_tokens, index.chunk_overlap_tokens) == (
        350,
        700,
        75,
    )
    assert index.embedding_max_input_tokens == 1800
    assert index.embedding_batch_size == 32
    assert index.embedding_timeout_seconds == 120
    assert index.retention_count == 2
    bundles = BundleConfig()
    assert bundles.max_total_bytes == 2 * 1024**3
    assert bundles.max_entries == 10_000
    assert bundles.disk_margin_bytes == 1024**3


def test_committed_local_config_still_loads_without_new_sections() -> None:
    config = load_config(
        config_path=REPO_ROOT / "config" / "local.yaml", env={}, cwd=REPO_ROOT / "config"
    ).config
    # Only retention is overridden, to keep a comparison baseline under `refresh` (F011 runbook).
    assert config.index == IndexConfig(retention_count=4)
    assert config.bundles == BundleConfig()


def test_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError):
        AppConfig(index={"chunk_max_tokenz": 5})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "values",
    [
        {"retention_count": 1},
        {"chunk_overlap_tokens": 49},
        {"chunk_overlap_tokens": 101},
        {"chunk_min_tokens": 800, "chunk_max_tokens": 700},
        {"chunk_max_tokens": 1700, "embedding_max_input_tokens": 1800},
        {"embedding_batch_size": 0},
        {"embedding_timeout_seconds": 0},
    ],
)
def test_invalid_index_values_rejected(values: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        IndexConfig(**values)


@pytest.mark.parametrize(
    "values", [{"max_total_bytes": 0}, {"max_entries": 0}, {"disk_margin_bytes": -1}]
)
def test_invalid_bundle_values_rejected(values: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        BundleConfig(**values)
