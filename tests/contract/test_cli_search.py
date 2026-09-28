"""`lookup` and `search` CLI contract (FR-017). Mocked provider."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from score_docs_assistant.cli.main import cli_app
from tests.helpers.search import SearchFixture, make_search_fixture

runner = CliRunner()


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> SearchFixture:
    return make_search_fixture(tmp_path_factory.mktemp("cli-search"))


def _invoke(fx: SearchFixture, *args: str):  # type: ignore[no-untyped-def]
    config = fx.data.parent / "app.yaml"
    config.write_text(f"schema_version: 1\ndata_dir: {fx.data}\n")
    return runner.invoke(cli_app, ["--config", str(config), *args])


def test_lookup_help() -> None:
    result = runner.invoke(cli_app, ["lookup", "--help"])
    assert "Looks up a requirement ID exactly in one snapshot. Offline." in " ".join(
        result.output.split()
    )


def test_lookup_text_and_relationships(fx: SearchFixture) -> None:
    result = _invoke(fx, "lookup", "feat_req__alpha__short", "--relationships")
    assert result.exit_code == 0, result.output
    assert "[exact] alpha:feat_req__alpha__short" in result.stdout
    assert "(unverified)" in result.stdout  # export copy listed after the git record
    assert "-> satisfies: feat_req__missing (unresolved)" in result.stdout


def test_lookup_json(fx: SearchFixture) -> None:
    result = _invoke(fx, "lookup", "mle-3-bp1", "--json")
    payload = json.loads(result.stdout)
    assert payload["entities"][0]["match"] == "alias"
    assert payload["snapshot_id"] == fx.snapshot_id


def test_lookup_no_match_exit_0(fx: SearchFixture) -> None:
    result = _invoke(fx, "lookup", "nope__nope")
    assert result.exit_code == 0 and 'no exact match for "nope__nope"' in result.stdout


def test_lookup_errors(fx: SearchFixture, tmp_path: Path) -> None:
    assert _invoke(fx, "lookup", "x", "--source", "nope").exit_code == 2
    result = _invoke(fx, "lookup", "x", "--snapshot", "20990101T000000Z-00000000")
    assert result.exit_code == 1 and "SNAPSHOT_NOT_FOUND" in result.stderr
    assert _invoke(fx, "lookup").exit_code == 2


# --- search ---------------------------------------------------------------------------------


@pytest.fixture
def with_provider(fx: SearchFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    from score_docs_assistant.cli import runtime_factory

    monkeypatch.setattr(runtime_factory, "build_embedding_provider", lambda config: fx.provider)


def test_search_help() -> None:
    result = runner.invoke(cli_app, ["search", "--help"])
    assert (
        "Searches one snapshot offline; may use the local embedding runtime (no downloads, "
        "no generation)." in " ".join(result.output.split())
    )


def test_search_text(fx: SearchFixture, with_provider: None) -> None:
    result = _invoke(fx, "search", "What does feat_req__alpha__long require?")
    assert result.exit_code == 0, result.output
    assert f"snapshot {fx.snapshot_id}  mode hybrid" in result.stdout
    assert " 1. [exact" in result.stdout


def test_search_json_filters(fx: SearchFixture, with_provider: None) -> None:
    result = _invoke(
        fx, "search", "watchdog", "--source", "beta", "--kind", "prose", "--limit", "3", "--json"
    )
    payload = json.loads(result.stdout)
    assert payload["results"] and {r["source_id"] for r in payload["results"]} == {"beta"}
    assert len(payload["results"]) <= 3


def test_search_lexical_flag(fx: SearchFixture, with_provider: None) -> None:
    result = _invoke(fx, "search", "watchdog", "--lexical", "--json")
    payload = json.loads(result.stdout)
    assert payload["mode"] == "lexical" and payload["degraded"]["reason"] == "lexical_requested"
    assert "warning" not in result.stderr


def test_search_degraded_warning(fx: SearchFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    from score_docs_assistant.cli import runtime_factory
    from tests.helpers.fake_embedding import FakeEmbeddingProvider

    monkeypatch.setattr(
        runtime_factory,
        "build_embedding_provider",
        lambda config: FakeEmbeddingProvider(mode="unreachable"),
    )
    result = _invoke(fx, "search", "watchdog")
    assert result.exit_code == 0
    assert "warning: semantic search unavailable (embedding_runtime_unavailable)" in result.stderr


def test_search_exit_codes(fx: SearchFixture, with_provider: None) -> None:
    assert _invoke(fx, "search", "   ").exit_code == 2
    assert _invoke(fx, "search", "x", "--kind", "image").exit_code == 2
    assert _invoke(fx, "search", "x", "--source", "nope").exit_code == 2
    assert _invoke(fx, "search", "x", "--limit", "50").exit_code == 2
    result = _invoke(fx, "search", "x", "--snapshot", "20990101T000000Z-00000000")
    assert result.exit_code == 1
    assert _invoke(fx, "search", "xyzzyplugh").exit_code == 0
