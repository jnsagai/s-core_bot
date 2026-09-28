"""`eval retrieval | exact-ids | latency` CLI contract (FR-019–FR-021). Mocked provider."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from score_docs_assistant.cli import runtime_factory
from score_docs_assistant.cli.main import cli_app
from tests.helpers.search import SearchFixture, make_search_fixture

runner = CliRunner()
CASES = {
    "schema_version": 1,
    "review_status": "unreviewed (agent-authored)",
    "written_against": {"alpha": "a" * 40},
    "cases": [
        {
            "id": "c1",
            "category": "requirements_templates",
            "question": "What is MLE.3.BP1 about?",
            "expected": [[{"entity_key": "alpha:MLE.3.BP1"}]],
        }
    ],
}


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> SearchFixture:
    return make_search_fixture(tmp_path_factory.mktemp("cli-eval"))


@pytest.fixture(autouse=True)
def provider(fx: SearchFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime_factory, "build_embedding_provider", lambda config: fx.provider)


def _invoke(fx: SearchFixture, *args: str):  # type: ignore[no-untyped-def]
    config = fx.data.parent / "app.yaml"
    config.write_text(f"schema_version: 1\ndata_dir: {fx.data}\n")
    return runner.invoke(cli_app, ["--config", str(config), *args])


def _cases(tmp_path: Path, data: object = CASES) -> str:
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump(data))
    return str(path)


@pytest.mark.parametrize(
    ("command", "line"),
    [
        (
            "retrieval",
            "Measures retrieval recall@10 against a case file; may use the local embedding "
            "runtime.",
        ),
        (
            "exact-ids",
            "Checks that every requirement ID in a snapshot is found first by exact lookup. "
            "Offline.",
        ),
        (
            "latency",
            "Measures search latency percentiles for keyword-only and hybrid modes; uses the "
            "local embedding runtime.",
        ),
    ],
)
def test_help_lines(command: str, line: str) -> None:
    result = runner.invoke(cli_app, ["eval", command, "--help"])
    assert line in " ".join(result.output.split())


def test_retrieval_text_and_report(fx: SearchFixture, tmp_path: Path) -> None:
    result = _invoke(fx, "eval", "retrieval", "--cases", _cases(tmp_path))
    assert result.exit_code == 0, result.output
    assert "development measurement, not release evidence" in result.stdout
    assert "overall (macro)" in result.stdout and "100.0%" in result.stdout
    assert list((fx.data / "reports").glob("retrieval-*.json"))


def test_retrieval_malformed_exit_2(fx: SearchFixture, tmp_path: Path) -> None:
    result = _invoke(fx, "eval", "retrieval", "--cases", _cases(tmp_path, {"schema_version": 1}))
    assert result.exit_code == 2


def test_exact_ids(fx: SearchFixture) -> None:
    result = _invoke(fx, "eval", "exact-ids", "--json")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["correct_first"] == payload["ids_checked"] == 5


def test_latency(fx: SearchFixture, tmp_path: Path) -> None:
    result = _invoke(
        fx, "eval", "latency", "--cases", _cases(tmp_path), "--queries", "10", "--json"
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["modes"]["lexical"]["status"] == "measured"
    assert payload["modes"]["hybrid"]["queries"] == 10
    assert payload["environment"]["cpu_count"]
