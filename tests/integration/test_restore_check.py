"""Restore check over a real bundle round trip (F009 FR-007, SC-003, AT-16; mocked provider)."""

from __future__ import annotations

from pathlib import Path

from score_docs_assistant.qualification.restore import compare, main
from score_docs_assistant.storage import bundles
from tests.helpers.build import app_config
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.search import make_search_fixture

ACK = "reviewed for test redistribution"


def _restore(source: Path, snapshot_id: str, tmp_path: Path) -> Path:
    bundle = tmp_path / "b.score-bundle.tar.gz"
    bundles.export_bundle(
        config=app_config(source), snapshot_id=snapshot_id, output=bundle, acknowledgement=ACK
    )
    data = tmp_path / "restored" / "data"
    data.mkdir(parents=True)
    bundles.import_bundle(config=app_config(data), path=bundle)
    from score_docs_assistant.storage import lifecycle

    lifecycle.activate(
        config=app_config(data),
        snapshot_id=snapshot_id,
        runtime=FakeEmbeddingProvider(),
        progress=lambda _m: None,
    )
    return data


def test_restored_corpus_keeps_citations(tmp_path: Path) -> None:
    fx = make_search_fixture(tmp_path / "src")
    restored = _restore(fx.data, fx.snapshot_id, tmp_path)
    report = compare(fx.data, restored, sample=20)
    assert report.status == "pass", report
    assert report.original_snapshot == report.restored_snapshot == fx.snapshot_id
    assert report.chunks_compared > 0 and report.citations_compared > 0


def test_a_different_corpus_is_detected(tmp_path: Path) -> None:
    fx = make_search_fixture(tmp_path / "a")
    other = make_search_fixture(tmp_path / "b")  # same sources, different snapshot ID
    report = compare(fx.data, other.data, sample=10)
    assert report.status == "fail" and report.original_snapshot != report.restored_snapshot


def test_empty_restore_fails_and_cli_writes_report(tmp_path: Path) -> None:
    fx = make_search_fixture(tmp_path / "a")
    empty = tmp_path / "empty"
    empty.mkdir()
    out = tmp_path / "restore.json"
    assert main(["--original", str(fx.data), "--restored", str(empty), "--out", str(out)]) == 1
    assert '"status": "fail"' in out.read_text()
