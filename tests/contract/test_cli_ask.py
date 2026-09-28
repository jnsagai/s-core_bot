"""`ask` CLI contract (FR-024). Mocked providers."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from score_docs_assistant.cli import runtime_factory
from score_docs_assistant.cli.main import cli_app
from tests.helpers.answers import AnswerFixture, make_answer_fixture
from tests.helpers.fake_generation import FakeGenerationProvider, answer

runner = CliRunner()


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> AnswerFixture:
    return make_answer_fixture(tmp_path_factory.mktemp("cli-ask"))


def _invoke(fx: AnswerFixture, generator: FakeGenerationProvider, monkeypatch, *args: str):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(runtime_factory, "build_embedding_provider", lambda c: fx.search.provider)
    monkeypatch.setattr(runtime_factory, "build_generation_provider", lambda c: generator)
    config = fx.data.parent / "app.yaml"
    config.write_text(f"schema_version: 1\ndata_dir: {fx.data}\n")
    return runner.invoke(cli_app, ["--config", str(config), *args])


def test_help() -> None:
    result = runner.invoke(cli_app, ["ask", "--help"])
    assert (
        "Answers a question from one snapshot with the local model; cites stored evidence "
        "(no downloads)." in " ".join(result.output.split())
    )


def test_text_output(fx: AnswerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    generator = FakeGenerationProvider(
        outputs=[
            answer(
                "partial",
                ("The watchdog supervises task deadlines.", "documented", ["E1"]),
                ("Nothing about components.", "limitation", []),
            )
        ]
    )
    result = _invoke(fx, generator, monkeypatch, "ask", "watchdog", "--show-evidence")
    assert result.exit_code == 0, result.output
    assert (
        f"snapshot {fx.search.snapshot_id}  status partial  model qwen3:4b-instruct"
        in result.stdout
    )
    assert "- The watchdog supervises task deadlines. [E1]" in result.stdout
    assert "limitations:" in result.stdout and "citations:" in result.stdout
    assert "     | " in result.stdout


def test_json_and_fallback_warning(fx: AnswerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    generator = FakeGenerationProvider(outputs=["bad", "bad"])
    result = _invoke(fx, generator, monkeypatch, "ask", "watchdog", "--json")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["origin"] == "extractive_fallback"
    assert "warning: model_output_invalid" in result.stderr


def test_exit_codes(fx: AnswerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    down = FakeGenerationProvider(unavailable="runtime_unreachable")
    result = _invoke(fx, down, monkeypatch, "ask", "watchdog")
    assert result.exit_code == 1 and "GENERATION_UNAVAILABLE" in result.stderr
    assert _invoke(fx, FakeGenerationProvider(), monkeypatch, "ask", "x" * 4001).exit_code == 2
    result = _invoke(
        fx,
        FakeGenerationProvider(),
        monkeypatch,
        "ask",
        "q",
        "--snapshot",
        "20990101T000000Z-00000000",
    )
    assert result.exit_code == 1 and "SNAPSHOT_NOT_FOUND" in result.stderr
