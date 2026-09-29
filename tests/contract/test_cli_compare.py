"""`compare` and `snapshots diff` CLI contracts (FR-012, FR-017). Mocked providers."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from score_docs_assistant.cli import runtime_factory
from score_docs_assistant.cli.main import cli_app
from tests.helpers.comparison_fixtures import (
    ComparisonFixture,
    answer_citing_all,
    make_comparison_fixture,
)
from tests.helpers.fake_generation import FakeGenerationProvider

runner = CliRunner()
EMPTY = json.dumps({"differences": []})


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> ComparisonFixture:
    return make_comparison_fixture(tmp_path_factory.mktemp("cli-compare"))


def _invoke(fx: ComparisonFixture, generator: FakeGenerationProvider, monkeypatch, *args: str):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(runtime_factory, "build_embedding_provider", lambda c: fx.provider)
    monkeypatch.setattr(runtime_factory, "build_generation_provider", lambda c: generator)
    config = fx.data.parent / "app.yaml"
    config.write_text(f"schema_version: 1\ndata_dir: {fx.data}\n")
    return runner.invoke(cli_app, ["--config", str(config), *args])


def _gen() -> FakeGenerationProvider:
    return FakeGenerationProvider(outputs=[answer_citing_all, answer_citing_all, EMPTY])


def test_help_lines() -> None:
    compare = " ".join(runner.invoke(cli_app, ["compare", "--help"]).output.split())
    assert (
        "Compares how two snapshots answer a question with the local model; evidence stays "
        "separate per snapshot (no downloads)." in compare
    )
    diff = " ".join(runner.invoke(cli_app, ["snapshots", "diff", "--help"]).output.split())
    assert (
        "Shows per-source revisions and processing differences of two snapshots (offline, no "
        "model)." in diff
    )


def test_text_output(fx: ComparisonFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _invoke(
        fx,
        _gen(),
        monkeypatch,
        "compare",
        "How many reviewers? feat_req__cmp__edit",
        "--left",
        fx.left_id,
        "--right",
        fx.right_id,
        "--show-evidence",
    )
    assert result.exit_code == 0, result.output
    out = result.stdout
    assert f"left  {fx.left_id}   right {fx.right_id}   model qwen3:4b-instruct" in out
    assert "platform  right only  — → 3333333… (pinned)" in out
    assert "No release label: per-source revisions identify each snapshot." in out
    assert "LEFT (status answered)" in out and "RIGHT (status answered)" in out
    assert "- changed: feat_req__cmp__edit differs" in out
    assert "[L1]" in out and "     | " in out and "evidence:" in out


def test_json_output(fx: ComparisonFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _invoke(
        fx,
        _gen(),
        monkeypatch,
        "compare",
        "reviewers",
        "--left",
        fx.left_id,
        "--right",
        fx.right_id,
        "--json",
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["left"]["snapshot_id"] == fx.left_id and body["snapshots"]["release_label"] is None


@pytest.mark.parametrize(
    ("args", "code", "message"),
    [
        (["--left", "{l}", "--right", "{l}"], 2, "REQUEST_INVALID"),
        (["--left", "bad", "--right", "{r}"], 2, "REQUEST_INVALID"),
        (["--left", "{l}", "--right", "20990101T000000Z-00000000"], 1, "SNAPSHOT_NOT_FOUND"),
    ],
)
def test_errors(
    fx: ComparisonFixture, monkeypatch: pytest.MonkeyPatch, args: list[str], code: int, message: str
) -> None:
    filled = [a.format(l=fx.left_id, r=fx.right_id) for a in args]
    result = _invoke(fx, _gen(), monkeypatch, "compare", "q", *filled)
    assert result.exit_code == code, result.output
    assert message in result.output


def test_generation_unavailable_exit_1(
    fx: ComparisonFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    generator = FakeGenerationProvider(unavailable="runtime_unreachable")
    result = _invoke(
        fx, generator, monkeypatch, "compare", "q", "--left", fx.left_id, "--right", fx.right_id
    )
    assert result.exit_code == 1 and "GENERATION_UNAVAILABLE" in result.output


def test_snapshots_diff(fx: ComparisonFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    generator = FakeGenerationProvider(unavailable="runtime_unreachable")
    text = _invoke(fx, generator, monkeypatch, "snapshots", "diff", fx.left_id, fx.right_id)
    assert text.exit_code == 0, text.output
    assert "proc  different  1111111… (pinned) → 2222222… (pinned)" in text.stdout
    assert "warning: source_only_on_one_side: platform" in text.stdout
    data = _invoke(
        fx, generator, monkeypatch, "snapshots", "diff", fx.left_id, fx.right_id, "--json"
    )
    assert json.loads(data.stdout)["release_label"] is None
    same = _invoke(fx, generator, monkeypatch, "snapshots", "diff", fx.left_id, fx.left_id)
    assert same.exit_code == 2 and "REQUEST_INVALID" in same.output
    assert generator.calls == []
