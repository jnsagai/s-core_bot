"""Comparison evaluation metrics and case files (FR-020, research R10). Mocked providers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from score_docs_assistant.comparison.evaluation import (
    ComparisonCase,
    ComparisonCaseFile,
    evaluate_comparisons,
    load_comparison_cases,
)
from score_docs_assistant.domain.errors import ConfigError, GenerationError
from tests.helpers.comparison_fixtures import (
    ComparisonFixture,
    answer_citing_all,
    make_comparison_fixture,
)
from tests.helpers.fake_generation import FakeGenerationProvider

REPO = Path(__file__).parent.parent.parent
EMPTY = json.dumps({"differences": []})


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> ComparisonFixture:
    return make_comparison_fixture(tmp_path_factory.mktemp("eval"))


def _file(*cases: ComparisonCase, reviewed: bool = False) -> ComparisonCaseFile:
    return ComparisonCaseFile(
        schema_version=1,
        review_status="reviewed by owner" if reviewed else "unreviewed",
        cases=list(cases),
    )


def test_metrics(fx: ComparisonFixture) -> None:
    cases = _file(
        ComparisonCase(
            id="a", category="exact_id", question="feat_req__cmp__same", expected_type="unchanged"
        ),
        ComparisonCase(
            id="b",
            category="missing_coverage",
            question="feat_req__cmp__plat",
            expected_type="not_established",
        ),
        ComparisonCase(
            id="c", category="changed", question="feat_req__cmp__same", expected_type="changed"
        ),
    )
    generator = FakeGenerationProvider(outputs=[answer_citing_all, answer_citing_all, EMPTY] * 3)
    report = asyncio.run(
        evaluate_comparisons(
            fx.service(generator), cases, "sha", left=fx.left_id, right=fx.right_id
        )
    )
    assert [c.type_ok for c in report.cases] == [True, True, False]
    assert report.type_agreement.ok == 2 and report.type_agreement.total == 3
    assert report.isolation_violations == 0 and report.deletion_claims == 0
    assert report.citation_integrity.ok == report.citation_integrity.total == 3
    assert report.labels == ["development measurement", "not release evidence"]
    assert report.by_category["exact_id"].ok == 1
    assert report.latency_ms["p50"] > 0


def test_reviewed_file_has_no_labels(fx: ComparisonFixture) -> None:
    case = ComparisonCase(id="a", category="unchanged", question="q", expected_type="unchanged")
    generator = FakeGenerationProvider(outputs=[answer_citing_all, answer_citing_all, EMPTY])
    report = asyncio.run(
        evaluate_comparisons(
            fx.service(generator),
            _file(case, reviewed=True),
            "s",
            left=fx.left_id,
            right=fx.right_id,
        )
    )
    assert report.labels == []


def test_generation_unavailable_raises(fx: ComparisonFixture) -> None:
    case = ComparisonCase(id="a", category="unchanged", question="q", expected_type="unchanged")
    with pytest.raises(GenerationError):
        asyncio.run(
            evaluate_comparisons(
                fx.service(FakeGenerationProvider(unavailable="runtime_unreachable")),
                _file(case),
                "s",
                left=fx.left_id,
                right=fx.right_id,
            )
        )


def test_malformed_case_file(tmp_path: Path) -> None:
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "review_status": "x", "cases": [{}]}))
    with pytest.raises(ConfigError):
        load_comparison_cases(path)


def test_committed_benchmark_meets_minimums() -> None:
    case_file, _ = load_comparison_cases(REPO / "eval" / "comparison-dev.yaml")
    assert case_file.composition_problems() == []
    assert not case_file.reviewed  # agent-authored; the owner has not reviewed it
