"""`eval answers` CLI contract (FR-025). Mocked providers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from score_docs_assistant.cli import runtime_factory
from score_docs_assistant.cli.main import cli_app
from tests.helpers.answers import AnswerFixture, make_answer_fixture
from tests.helpers.fake_generation import FakeGenerationProvider, answer

runner = CliRunner()
CASES = {
    "schema_version": 1,
    "review_status": "unreviewed (agent-authored)",
    "written_against": {"alpha": "a" * 40},
    "cases": [
        {
            "id": "c1",
            "category": "unanswerable",
            "question": "capital of France",
            "expected_status": "safe_handling",
        }
    ],
}


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> AnswerFixture:
    return make_answer_fixture(tmp_path_factory.mktemp("cli-eval-answers"))


def _invoke(
    fx: AnswerFixture,
    generator: FakeGenerationProvider,
    monkeypatch,
    tmp_path: Path,
    data: object = CASES,
    *extra: str,
):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(runtime_factory, "build_embedding_provider", lambda c: fx.search.provider)
    monkeypatch.setattr(runtime_factory, "build_generation_provider", lambda c: generator)
    cases = tmp_path / "cases.yaml"
    cases.write_text(yaml.safe_dump(data))
    config = fx.data.parent / "app.yaml"
    config.write_text(f"schema_version: 1\ndata_dir: {fx.data}\n")
    return runner.invoke(
        cli_app, ["--config", str(config), "eval", "answers", "--cases", str(cases), *extra]
    )


def test_help() -> None:
    result = runner.invoke(cli_app, ["eval", "answers", "--help"])
    assert (
        "Runs answer cases against the local model and reports status, citation integrity"
        in " ".join(result.output.split())
    )


def test_run_writes_report_and_sheet(
    fx: AnswerFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    generator = FakeGenerationProvider(outputs=[answer("insufficient_evidence")])
    result = _invoke(fx, generator, monkeypatch, tmp_path)
    assert result.exit_code == 0, result.output
    assert "safe handling of unanswerable 1/1" in result.stdout
    assert "factual support precision: not run" in result.stdout
    assert list((fx.data / "reports").glob("answers-review-*.yaml"))


def test_json(fx: AnswerFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result = _invoke(
        fx,
        FakeGenerationProvider(outputs=[answer("insufficient_evidence")]),
        monkeypatch,
        tmp_path,
        CASES,
        "--json",
    )
    assert json.loads(result.stdout)["safe_handling"] == {"ok": 1, "total": 1}


def test_exit_codes(fx: AnswerFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    down = FakeGenerationProvider(unavailable="runtime_unreachable")
    assert _invoke(fx, down, monkeypatch, tmp_path).exit_code == 1
    assert (
        _invoke(
            fx, FakeGenerationProvider(), monkeypatch, tmp_path, {"schema_version": 1}
        ).exit_code
        == 2
    )
    injection = {**CASES, "snapshot_fixture": "injection"}
    assert _invoke(fx, FakeGenerationProvider(), monkeypatch, tmp_path, injection).exit_code == 2
