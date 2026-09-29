"""Suite harness metrics, runs and privacy scan (F008 FR-007, FR-008, FR-012). Mocked providers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from score_docs_assistant.qualification.harness import combine_runs, run_suite
from score_docs_assistant.qualification.suite import SuiteFile
from tests.helpers.answers import AnswerFixture, make_answer_fixture
from tests.helpers.fake_generation import FakeGenerationProvider, answer


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> AnswerFixture:
    return make_answer_fixture(tmp_path_factory.mktemp("suite"))


def suite(split: str = "dev", review: dict[str, Any] | None = None) -> SuiteFile:
    review = review or {"status": "unreviewed"}
    return SuiteFile.model_validate(
        {
            "schema_version": 1,
            "split": split,
            "review_status": "unreviewed",
            "written_against": {},
            "cases": [
                {
                    "id": "c1",
                    "category": "onboarding_build",
                    "question": "How do I build the documentation locally with bazel?",
                    "expected_status": "answered",
                    "expected_facts": [{"fact": "Run bazel run //:docs."}],
                    "evidence": [[{"source_id": "alpha", "path": "docs/build.md"}]],
                    "forbidden": ["certified", "re:make\\s+docs"],
                    "review": review,
                },
                {
                    "id": "c2",
                    "category": "unsupported",
                    "question": "What is the capital of France?",
                    "expected_status": "safe_handling",
                    "review": review,
                },
                {
                    "id": "c3",
                    "category": "requirements_templates",
                    "question": "What does feat_req__alpha__short explain?",
                    "expected_status": "answered",
                    "expected_facts": [{"fact": "The scheduler handshake."}],
                    "evidence": [[{"entity_key": "alpha:feat_req__alpha__short"}]],
                    "review": review,
                },
            ],
        }
    )


GOOD = answer(
    "answered", ("Run the documentation build with bazel; it is certified.", "documented", ["E1"])
)


def test_metrics_with_denominators(fx: AnswerFixture) -> None:
    generator = FakeGenerationProvider(
        outputs=[GOOD, answer("insufficient_evidence"), answer("insufficient_evidence")]
    )
    service = fx.service(generator)
    report, pairs = asyncio.run(
        run_suite(search=service._search, answers=service, suite=suite(), sha="s", freeze="n/a")  # noqa: SLF001
    )
    m = report.metrics
    assert m["recall_at_10"].denominator == 2 and m["recall_at_10"].value is not None
    assert (m["safe_handling"].numerator, m["safe_handling"].denominator) == (1, 1)
    assert (m["false_abstention"].numerator, m["false_abstention"].denominator) == (1, 2)
    assert m["citation_integrity"].value == 1.0
    assert report.cases[0].forbidden_hits == ["certified"]
    assert m["forbidden_assertions"].numerator == 1
    assert report.labels == ["development measurement", "not release evidence"]
    assert set(report.by_category) == {"onboarding_build", "unsupported", "requirements_templates"}
    assert len(pairs) == 3 and report.snapshot_id == fx.search.snapshot_id


def test_privacy_scan_detects_question_text_in_logs(fx: AnswerFixture) -> None:
    class Leaky(FakeGenerationProvider):
        async def generate(self, messages, **kw):  # type: ignore[no-untyped-def]
            logging.getLogger("leak").warning("question was %s", messages[1]["content"][-200:])
            return await super().generate(messages, **kw)

    service = fx.service(Leaky(outputs=[GOOD, GOOD, GOOD]))
    report, _ = asyncio.run(
        run_suite(search=service._search, answers=service, suite=suite(), sha="s", freeze="n/a")  # noqa: SLF001
    )
    assert report.privacy.question_text_found >= 1
    clean = fx.service(FakeGenerationProvider(outputs=[GOOD, GOOD, GOOD]))
    report, _ = asyncio.run(
        run_suite(search=clean._search, answers=clean, suite=suite(), sha="s", freeze="n/a")  # noqa: SLF001
    )
    assert report.privacy.question_text_found == 0


def test_only_human_reviewed_heldout_is_unlabelled(fx: AnswerFixture) -> None:
    reviewed = {"status": "human_reviewed", "reviewer": "owner", "date": "2026-10-01"}
    service = fx.service(FakeGenerationProvider(outputs=[GOOD] * 6))
    dev, _ = asyncio.run(
        run_suite(
            search=service._search,
            answers=service,
            suite=suite("dev", reviewed),
            sha="s",
            freeze="n/a",
        )  # noqa: SLF001
    )
    held, _ = asyncio.run(
        run_suite(
            search=service._search,
            answers=service,
            suite=suite("heldout", reviewed),
            sha="s",
            freeze="ok",
        )  # noqa: SLF001
    )
    assert dev.labels and held.labels == []


def test_combine_runs_reports_each_run_and_spread(fx: AnswerFixture) -> None:
    service = fx.service(
        FakeGenerationProvider(
            outputs=[GOOD, GOOD, GOOD, GOOD, answer("insufficient_evidence"), GOOD]
        )
    )
    reports = [
        asyncio.run(
            run_suite(
                search=service._search, answers=service, suite=suite(), sha="s", freeze="n/a", run=i
            )  # noqa: SLF001
        )[0]
        for i in (1, 2)
    ]
    combined = combine_runs(reports, ["a.json", "b.json"])
    assert len(combined.runs) == 2 and combined.run_files == ["a.json", "b.json"]
    spread = combined.spread["false_abstention"]
    assert spread["min"] is not None and spread["max"] is not None
    assert spread["range"] == pytest.approx(spread["max"] - spread["min"])
