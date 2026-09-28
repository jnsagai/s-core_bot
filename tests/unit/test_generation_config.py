"""GenerationConfig (specs/005-grounded-chat/data-model.md)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from score_docs_assistant.config.loader import load_config
from score_docs_assistant.config.schema import AppConfig, GenerationConfig

REPO_ROOT = Path(__file__).parent.parent.parent


def test_defaults() -> None:
    config = GenerationConfig()
    assert config.temperature == 0.1 and config.history_turns == 10
    assert (config.history_tokens, config.evidence_tokens, config.evidence_items) == (1000, 4500, 8)
    assert (config.max_claims, config.max_claim_characters) == (12, 1200)
    assert config.repair_attempts == 1 and config.fallback_excerpts == 3
    assert config.repair_min_seconds == 15.0


@pytest.mark.parametrize(
    "values",
    [{"repair_attempts": 2}, {"temperature": 1.5}, {"history_turns": 51}, {"evidence_items": 0}],
)
def test_invalid(values: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        GenerationConfig(**values)


def test_evidence_items_bounded_by_search_limit() -> None:
    with pytest.raises(ValidationError):
        AppConfig(generation={"evidence_items": 30})  # type: ignore[arg-type]


def test_local_config_loads() -> None:
    config = load_config(
        config_path=REPO_ROOT / "config" / "local.yaml", env={}, cwd=REPO_ROOT / "config"
    ).config
    assert config.generation == GenerationConfig()
