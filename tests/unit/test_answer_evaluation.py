"""Answer evaluation (FR-025). Mocked providers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml

from score_docs_assistant.answers.evaluation import (
    apply_review,
    evaluate_answers,
    load_answer_cases,
)
from score_docs_assistant.domain.errors import ConfigError
from tests.helpers.answers import AnswerFixture, make_answer_fixture
from tests.helpers.fake_generation import FakeGenerationProvider, answer

CASES = {
    "schema_version": 1,
    "review_status": "unreviewed (agent-authored)",
    "written_against": {"alpha": "a" * 40},
    "cases": [
        {
            "id": "c1",
            "category": "requirements_templates",
            "question": "What does feat_req__alpha__long require?",
            "expected_status": "answered",
            "expected": [[{"entity_key": "alpha:feat_req__alpha__long"}]],
        },
        {
            "id": "c2",
            "category": "unanswerable",
            "question": "capital of France",
            "expected_status": "safe_handling",
        },
    ],
}


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> AnswerFixture:
    return make_answer_fixture(tmp_path_factory.mktemp("answer-eval"))


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_report_and_sheet(fx: AnswerFixture, tmp_path: Path) -> None:
    cases, sha = load_answer_cases(_write(tmp_path, CASES))
    generator = FakeGenerationProvider(
        outputs=[
            answer(
                "answered",
                (
                    "The long requirement describes persistence of configuration.",
                    "documented",
                    ["E1"],
                ),
            ),
            answer("answered", ("Paris is the capital.", "documented", ["E1"])),  # wrong: not safe
        ]
    )
    service = fx.service(generator)
    report, sheet = asyncio.run(evaluate_answers(service, service._search, cases, sha))  # noqa: SLF001
    c1, c2 = report.cases
    assert c1.status_ok and c1.citation_integrity and c1.evidence_overlap == 1.0
    assert not c2.status_ok and c2.status == "answered"
    assert report.safe_handling.model_dump() == {"ok": 0, "total": 1}
    assert report.status_agreement.model_dump() == {"ok": 1, "total": 2}
    assert report.citation_integrity.model_dump() == {"ok": 2, "total": 2}
    assert report.labels == ["development measurement", "not release evidence"]
    assert report.human_review.support_precision.startswith("not run")
    claims = sheet["cases"][0]["claims"]  # type: ignore[index]
    assert claims[0]["supported"] is None and claims[0]["reviewer"] is None
    assert claims[0]["citations"][0]["excerpt"]

    # A human fills in the sheet → precision is computed from it.
    sheet["cases"][0]["claims"][0].update(supported=True, reviewer="maintainer 2026-09-29")  # type: ignore[index]
    sheet["cases"][1]["claims"][0].update(supported=False, reviewer="maintainer 2026-09-29")  # type: ignore[index]
    sheet_path = tmp_path / "sheet.yaml"
    sheet_path.write_text(yaml.safe_dump(sheet))
    reviewed = apply_review(report, sheet_path)
    assert reviewed.human_review.support_precision == "50.0% of 2 human-reviewed claims"


def test_sheet_from_other_case_file_rejected(fx: AnswerFixture, tmp_path: Path) -> None:
    cases, sha = load_answer_cases(_write(tmp_path, CASES))
    service = fx.service(FakeGenerationProvider(outputs=[answer("insufficient_evidence")] * 2))
    report, sheet = asyncio.run(evaluate_answers(service, service._search, cases, sha))  # noqa: SLF001
    sheet["case_file_sha256"] = "0" * 64
    path = tmp_path / "sheet.yaml"
    path.write_text(yaml.safe_dump(sheet))
    with pytest.raises(ConfigError):
        apply_review(report, path)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["cases"][0].update(expected_status="maybe"),
        lambda d: d["cases"].append(dict(d["cases"][0])),
        lambda d: d.update(snapshot_fixture="other"),
    ],
)
def test_malformed(tmp_path: Path, mutate) -> None:  # type: ignore[no-untyped-def]
    import copy

    data = copy.deepcopy(CASES)
    mutate(data)
    with pytest.raises(ConfigError):
        load_answer_cases(_write(tmp_path, data))
