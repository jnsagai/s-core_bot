"""Performance harness and budgets (F008 FR-013, FR-014). Mocked providers."""

from __future__ import annotations

import asyncio

import pytest

from score_docs_assistant.qualification.performance import (
    Distribution,
    evaluate_budgets,
    measure,
    percentile,
)
from tests.helpers.answers import AnswerFixture, make_answer_fixture
from tests.helpers.fake_generation import FakeGenerationProvider, answer

GOOD = answer("answered", ("The watchdog supervises task deadlines.", "documented", ["E1"]))


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> AnswerFixture:
    return make_answer_fixture(tmp_path_factory.mktemp("perf"))


def test_percentiles() -> None:
    assert percentile([], 0.95) is None
    assert percentile([1, 2, 3, 4, 100], 0.5) == 3
    assert percentile(list(range(1, 101)), 0.95) == 95


def test_budgets_pass_fail_and_insufficient_sample() -> None:
    ok = Distribution(samples=60, p50=10, p95=100, max=200)
    few = Distribution(samples=10, p50=10, p95=100, max=200)
    slow = Distribution(samples=60, p50=10, p95=900, max=990)
    budgets = {
        b.name: b.status
        for b in evaluate_budgets(
            {
                "lexical_retrieval": slow,
                "hybrid_retrieval_warm": ok,
                "first_progress_warm": few,
                "cancellation_release": Distribution(samples=3, p50=5, p95=6, max=7),
            }
        )
    }
    assert budgets["lexical_retrieval"] == "fail"
    assert budgets["hybrid_retrieval_warm"] == "pass"
    assert budgets["first_progress_warm"] == "fail (insufficient sample)"
    assert budgets["answer_warm"] == "not run"
    assert budgets["cancellation_release"] == "pass"  # 3 samples are enough for cancellation


def test_measure_with_fakes(fx: AnswerFixture) -> None:
    generator = FakeGenerationProvider(outputs=[GOOD] * 40, delay=0.01)
    service = fx.service(generator)
    unloads: list[int] = []
    report = asyncio.run(
        measure(
            search=service._search,  # noqa: SLF001
            answers=service,
            questions=[f"watchdog deadlines question {i}" for i in range(12)],
            answers_n=5,
            warmup=1,
            cold_samples=2,
            cancel_samples=2,
            unload=lambda: unloads.append(1) is None,
            loaded=lambda: [{"name": "fake", "size_vram": 1}],
            gpu=lambda: {"gpu": "fake", "used_mib": 100, "total_mib": 1000},
        )
    )
    d = report.distributions
    assert d["lexical_retrieval"].samples == 12 and d["answer_warm"].samples == 5
    assert d["answer_cold"].samples == 2 and len(unloads) == 4 and report.cold_unload_verified
    assert d["cancellation_release"].samples == 2 and d["cancellation_release"].max < 2000
    budgets = {b.name: b.status for b in report.budgets}
    assert budgets["answer_warm"] == "fail (insufficient sample)"  # only 5 < 50 samples
    assert report.memory["gpu_peak"]["used_mib"] == 100 and report.chunks and report.chunks > 0
