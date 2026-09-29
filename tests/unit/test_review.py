"""Review sheets and human-review import (F008 FR-004–FR-006, SC-002). Mocked providers."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from score_docs_assistant.domain.errors import ConfigError
from score_docs_assistant.qualification.harness import as_json, run_suite
from score_docs_assistant.qualification.review import build_sheet, import_review
from tests.helpers.answers import AnswerFixture, make_answer_fixture
from tests.helpers.fake_generation import FakeGenerationProvider, answer
from tests.unit.test_harness import GOOD, suite


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> AnswerFixture:
    return make_answer_fixture(tmp_path_factory.mktemp("review"))


def _run(fx: AnswerFixture, tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    service = fx.service(
        FakeGenerationProvider(outputs=[GOOD, answer("insufficient_evidence"), GOOD])
    )
    report, pairs = asyncio.run(
        run_suite(search=service._search, answers=service, suite=suite(), sha="s", freeze="n/a")  # noqa: SLF001
    )
    path = tmp_path / "run.json"
    payload = as_json(report)
    path.write_text(payload)
    sheet = build_sheet(path.name, hashlib.sha256(payload.encode()).hexdigest(), pairs)
    return path, sheet


def _save(tmp_path: Path, sheet: dict[str, Any]) -> Path:
    path = tmp_path / "sheet.yaml"
    path.write_text(yaml.safe_dump(sheet, sort_keys=False))
    return path


def test_sheet_has_empty_judgements_and_reviewer(fx: AnswerFixture, tmp_path: Path) -> None:
    _, sheet = _run(fx, tmp_path)
    assert sheet["reviewer"] is None and sheet["reviewed_on"] is None
    first = sheet["cases"][0]
    assert first["forbidden_hits_automated"] == ["certified"]
    assert first["facts"][0]["judgement"] is None
    assert first["claims"][0]["judgement"] is None and first["claims"][0]["citations"]
    assert "A citation alone does not make" in sheet["instructions"]
    assert sheet["cases"][1]["facts"] == []  # unsupported case: no facts to judge


def test_unfilled_sheet_is_rejected(fx: AnswerFixture, tmp_path: Path) -> None:
    report, sheet = _run(fx, tmp_path)
    with pytest.raises(ConfigError, match="reviewer and reviewed_on"):
        import_review(_save(tmp_path, sheet), report)


def _fill(sheet: dict[str, Any], claim: str, fact: str) -> dict[str, Any]:
    sheet["reviewer"], sheet["reviewed_on"] = "project owner", "2026-10-01"
    for case in sheet["cases"]:
        for c in case["claims"]:
            c["judgement"] = claim
        for f in case["facts"]:
            f["judgement"] = fact
    return sheet


def test_filled_sheet_computes_metrics_with_denominators(fx: AnswerFixture, tmp_path: Path) -> None:
    report, sheet = _run(fx, tmp_path)
    sheet = _fill(sheet, "supported", "partly")
    sheet["cases"][0]["claims"][0]["judgement"] = "unsupported"
    review = import_review(_save(tmp_path, sheet), report)
    assert review.reviewer == "project owner"
    assert review.support_precision.denominator == 2 and review.support_precision.numerator == 1
    assert review.required_fact_coverage.value == 0.5
    assert review.unreviewed_claims == 0
    assert set(review.support_precision_by_category) == {
        "onboarding_build",
        "requirements_templates",
    }


def test_partial_review_counts_unreviewed(fx: AnswerFixture, tmp_path: Path) -> None:
    report, sheet = _run(fx, tmp_path)
    sheet["reviewer"], sheet["reviewed_on"] = "owner", "2026-10-01"
    sheet["cases"][0]["claims"][0]["judgement"] = "supported"
    review = import_review(_save(tmp_path, sheet), report)
    assert review.support_precision.denominator == 1
    assert review.unreviewed_claims >= 1 and review.unreviewed_facts >= 1


@pytest.mark.parametrize("tamper", ["report", "claim_text", "case", "judgement"])
def test_mismatches_are_rejected(fx: AnswerFixture, tmp_path: Path, tamper: str) -> None:
    report, sheet = _run(fx, tmp_path)
    sheet = _fill(sheet, "supported", "covered")
    if tamper == "report":
        report.write_text(report.read_text() + " ")
    elif tamper == "claim_text":
        sheet["cases"][0]["claims"][0]["text"] += " edited"
    elif tamper == "case":
        sheet["cases"][0]["id"] = "zzz"
    else:
        sheet["cases"][0]["claims"][0]["judgement"] = "looks fine"
    with pytest.raises(ConfigError):
        import_review(_save(tmp_path, sheet), report)
