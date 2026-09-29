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
        4,
    )
    assert config.max_statement_characters == 400
    assert (config.side_max_claims, config.side_max_claim_characters) == (4, 500)
    assert (config.side_output_tokens, config.comparison_output_tokens) == (700, 600)
    assert config.repair == "if_no_valid_difference"


@pytest.mark.parametrize(
    "values",
    [{"deadline_seconds": 0}, {"evidence_items_per_side": 21}, {"max_differences": 0}, {"x": 1}],
)
def test_invalid(values: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        ComparisonConfig(**values)
