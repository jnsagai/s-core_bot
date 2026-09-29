"""`eval comparison` CLI contract (FR-020). Mocked providers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from score_docs_assistant.cli.main import cli_app
from tests.contract.test_cli_compare import _invoke
from tests.helpers.comparison_fixtures import (
    ComparisonFixture,
    answer_citing_all,
    make_comparison_fixture,
)
from tests.helpers.fake_generation import FakeGenerationProvider

runner = CliRunner()


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> ComparisonFixture:
    return make_comparison_fixture(tmp_path_factory.mktemp("cli-eval-cmp"))


def _cases(fx: ComparisonFixture, path: Path, with_snapshots: bool = True) -> Path:
    data = {
        "schema_version": 1,
        "review_status": "unreviewed",
        "cases": [
            {
                "id": "a",
                "category": "exact_id",
                "question": "feat_req__cmp__same",
                "expected_type": "unchanged",
            }
        ],
    }
    if with_snapshots:
        data |= {"left_snapshot": fx.left_id, "right_snapshot": fx.right_id}
    path.write_text(yaml.safe_dump(data))
    return path


def test_help() -> None:
    text = " ".join(runner.invoke(cli_app, ["eval", "comparison", "--help"]).output.split())
    assert (
        "Runs comparison cases against the local model and reports difference types, evidence "
        "isolation and deletion claims; development measurement unless reviewed." in text
    )


def test_run_writes_report(
    fx: ComparisonFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    generator = FakeGenerationProvider(
        outputs=[answer_citing_all, answer_citing_all, json.dumps({"differences": []})]
    )
    result = _invoke(
        fx,
        generator,
        monkeypatch,
        "eval",
        "comparison",
        "--cases",
        str(_cases(fx, tmp_path / "c.yaml")),
    )
    assert result.exit_code == 0, result.output
    assert "ok  a" in result.stdout and "type agreement 1/1" in result.stdout
    assert "[development measurement, not release evidence]" in result.stdout
    [report] = (fx.data / "reports").glob("comparison-*.json")
    assert json.loads(report.read_text())["deletion_claims"] == 0


def test_exit_codes(fx: ComparisonFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    down = FakeGenerationProvider(unavailable="runtime_unreachable")
    cases = str(_cases(fx, tmp_path / "c.yaml"))
    assert _invoke(fx, down, monkeypatch, "eval", "comparison", "--cases", cases).exit_code == 1
    bad = tmp_path / "bad.yaml"
    bad.write_text("schema_version: 1\ncases: []\n")
    assert _invoke(fx, down, monkeypatch, "eval", "comparison", "--cases", str(bad)).exit_code == 2
    nosnap = str(_cases(fx, tmp_path / "n.yaml", with_snapshots=False))
    assert _invoke(fx, down, monkeypatch, "eval", "comparison", "--cases", nosnap).exit_code == 2
