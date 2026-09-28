"""Retrieval evaluation (FR-019–FR-021, research R8). Mocked provider."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from score_docs_assistant.domain.errors import ConfigError
from score_docs_assistant.domain.retrieval import EvidenceResult
from score_docs_assistant.retrieval.evaluation import (
    Locator,
    evaluate_retrieval,
    exact_id_suite,
    load_case_file,
    measure_latency,
    percentile,
)
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.search import SearchFixture, make_search_fixture


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> SearchFixture:
    return make_search_fixture(tmp_path_factory.mktemp("eval"))


def _write(path: Path, data: object) -> Path:
    path.write_text(yaml.safe_dump(data))
    return path


def _cases(written_against: dict[str, str] | None = None) -> dict:  # type: ignore[type-arg]
    return {
        "schema_version": 1,
        "review_status": "unreviewed (agent-authored)",
        "written_against": written_against or {"alpha": "a" * 40, "beta": "b" * 40},
        "cases": [
            {
                "id": "c1",
                "category": "requirements_templates",
                "question": "What is MLE.3.BP1 about?",
                "expected": [[{"entity_key": "alpha:MLE.3.BP1"}]],
            },
            {
                "id": "c2",
                "category": "onboarding_build",
                "question": "How do I build the documentation locally?",
                "expected": [
                    [{"source_id": "alpha", "path": "docs/build.md"}],
                    [{"source_id": "beta", "path": "docs/nowhere.rst"}],
                ],
            },
        ],
    }


def _result(**kw: object) -> EvidenceResult:
    base = dict(
        rank=1,
        chunk_id="c",
        snapshot_id="s",
        source_id="alpha",
        revision="r",
        revision_status="pinned",
        path="docs/x.rst",
        origin_path="docs/x.rst",
        heading_path=[],
        line_start=10,
        line_end=20,
        kind="prose",
        entity_keys=[],
        excerpt="",
        truncated=False,
        matched_by=["keyword"],
    )
    return EvidenceResult.model_validate({**base, **kw})


def test_locator_matching() -> None:
    assert Locator(source_id="alpha", path="docs/x.rst").satisfied_by(_result())
    assert Locator(source_id="alpha", path="docs/x.rst", line_start=20, line_end=30).satisfied_by(
        _result()
    )
    assert not Locator(
        source_id="alpha", path="docs/x.rst", line_start=21, line_end=30
    ).satisfied_by(_result())
    assert not Locator(source_id="beta", path="docs/x.rst").satisfied_by(_result())
    assert Locator(entity_key="k").satisfied_by(_result(entity_keys=["k"]))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(extra=1),
        lambda d: d["cases"].append(dict(d["cases"][0])),  # duplicate id
        lambda d: d["cases"][0].update(expected=[[]]),
        lambda d: d["cases"][0].update(expected=[[{"source_id": "a"}]]),
        lambda d: d["cases"][0].update(
            expected=[[{"source_id": "a", "path": "p", "line_start": 5, "line_end": 2}]]
        ),
        lambda d: d["cases"][0].update(category="misc"),
        lambda d: d.update(schema_version=2),
    ],
)
def test_malformed_case_files(tmp_path: Path, mutate) -> None:  # type: ignore[no-untyped-def]
    data = _cases()
    mutate(data)
    with pytest.raises(ConfigError):
        load_case_file(_write(tmp_path / "c.yaml", data))
    (tmp_path / "bad.yaml").write_text("{: not yaml")
    with pytest.raises(ConfigError):
        load_case_file(tmp_path / "bad.yaml")


def test_recall_report(fx: SearchFixture, tmp_path: Path) -> None:
    cases, sha = load_case_file(_write(tmp_path / "c.yaml", _cases()))
    report = evaluate_retrieval(fx.service(), cases, sha)
    by_id = {c.id: c for c in report.cases}
    assert by_id["c1"].group_ranks == [1] and by_id["c1"].recall_at_10 == 1.0
    assert by_id["c2"].group_ranks[1] is None and by_id["c2"].recall_at_10 == 0.5
    assert report.macro_recall_at_10 == pytest.approx(0.75)
    assert report.by_category["onboarding_build"].cases == 1
    assert report.labels == ["development measurement", "not release evidence"]
    assert report.case_file_sha256 == sha and report.snapshot_id == fx.snapshot_id
    assert report.warnings == []


def test_written_against_mismatch_warns(fx: SearchFixture, tmp_path: Path) -> None:
    cases, sha = load_case_file(_write(tmp_path / "c.yaml", _cases({"alpha": "f" * 40})))
    report = evaluate_retrieval(fx.service(), cases, sha)
    assert any("written against alpha@ffffffffffff" in w for w in report.warnings)


def test_exact_id_suite(fx: SearchFixture) -> None:
    report = exact_id_suite(fx.service())
    assert report.ids_checked == 5  # MLE.3.BP1, short, long, dup (once), export_only
    assert report.correct_first == report.ids_checked and report.failures == []
    assert report.ambiguous_by_design == []


def test_percentile_nearest_rank() -> None:
    values = [float(v) for v in range(1, 101)]
    assert percentile(values, 0.95) == 95.0
    assert percentile(values, 0.50) == 50.0
    assert percentile([7.0], 0.95) == 7.0


def test_latency_report(fx: SearchFixture) -> None:
    ticks = iter(float(i) / 1000 for i in range(10_000))
    report = measure_latency(
        fx.service(), ["watchdog", "bazel"], queries=4, warmup=1, clock=lambda: next(ticks)
    )
    assert report.modes["lexical"].status == "measured" and report.modes["lexical"].queries == 4
    assert report.modes["hybrid"].status == "measured"
    assert report.embedding_warm is True


def test_latency_hybrid_not_run_without_runtime(fx: SearchFixture) -> None:
    report = measure_latency(
        fx.service(FakeEmbeddingProvider(mode="unreachable")), ["watchdog"], queries=2, warmup=1
    )
    assert report.modes["hybrid"].status == "not run"
    assert report.modes["hybrid"].p95_ms is None
    assert report.modes["hybrid"].reason == "embedding_runtime_unavailable"
