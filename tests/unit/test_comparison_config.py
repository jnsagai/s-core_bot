"""ComparisonConfig (specs/007-version-comparison/data-model.md)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from score_docs_assistant.config.schema import AppConfig, ComparisonConfig


def test_defaults() -> None:
    config = AppConfig().comparison
    assert (config.deadline_seconds, config.evidence_items_per_side, config.max_differences) == (
        240,
        5,
        5,
    )
    assert config.max_statement_characters == 600


@pytest.mark.parametrize(
    "values",
    [{"deadline_seconds": 0}, {"evidence_items_per_side": 21}, {"max_differences": 0}, {"x": 1}],
)
def test_invalid(values: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        ComparisonConfig(**values)
