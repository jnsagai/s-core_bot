"""F008 CLI contracts: eval suite / freeze / review import (mocked providers)."""

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
from tests.unit.test_harness import GOOD, suite

runner = CliRunner()


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> AnswerFixture:
    return make_answer_fixture(tmp_path_factory.mktemp("cli-qualify"))


def _invoke(fx: AnswerFixture, generator, monkeypatch, *args: str):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(runtime_factory, "build_embedding_provider", lambda c: fx.search.provider)
    monkeypatch.setattr(runtime_factory, "build_generation_provider", lambda c: generator)
    config = fx.data.parent / "app.yaml"
    config.write_text(f"schema_version: 1\ndata_dir: {fx.data}\n")
    return runner.invoke(cli_app, ["--config", str(config), *args])


def _suite_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "suite"
    directory.mkdir()
    for split in ("dev", "heldout"):
        data = suite(split).model_dump(mode="json", exclude_defaults=False)
        (directory / f"{split}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    return directory


def _gen(n: int = 3) -> FakeGenerationProvider:
    return FakeGenerationProvider(outputs=[GOOD, answer("insufficient_evidence"), GOOD] * n)


@pytest.mark.parametrize(
    ("command", "line"),
    [
        (
            ["eval", "suite"],
            "Runs the evaluation suite (retrieval and answers) and writes reports",
        ),
        (
            ["eval", "freeze"],
            "Freezes a suite file by recording its hash; runs refuse a changed frozen file.",
        ),
        (
            ["eval", "review", "import"],
            "Imports a human-filled review sheet and computes support precision",
        ),
    ],
)
def test_help_lines(command: list[str], line: str) -> None:
    assert line in " ".join(runner.invoke(cli_app, [*command, "--help"]).output.split())


def test_dev_run_writes_report_and_sheet(
    fx: AnswerFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directory = _suite_dir(tmp_path)
    result = _invoke(
        fx, _gen(), monkeypatch, "eval", "suite", "--split", "dev", "--suite-dir", str(directory)
    )
    assert result.exit_code == 0, result.output
    assert "run 1: recall@10" in result.stdout and "[development measurement" in result.stdout
    reports = fx.data / "reports"
    assert list(reports.glob("suite-dev-*-run1.json")) and list(
        reports.glob("suite-dev-*-review.yaml")
    )


def test_heldout_refused_until_frozen(
    fx: AnswerFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directory = _suite_dir(tmp_path)
    refused = _invoke(
        fx,
        _gen(),
        monkeypatch,
        "eval",
        "suite",
        "--split",
        "heldout",
        "--suite-dir",
        str(directory),
    )
    assert refused.exit_code == 1 and "HELDOUT_NOT_FROZEN" in refused.output
    no_reason = _invoke(fx, _gen(), monkeypatch, "eval", "freeze", "--suite-dir", str(directory))
    assert no_reason.exit_code == 2
    frozen = _invoke(
        fx, _gen(), monkeypatch, "eval", "freeze", "--suite-dir", str(directory), "--reason", "test"
    )
    assert frozen.exit_code == 0, frozen.output
    ran = _invoke(
        fx,
        _gen(),
        monkeypatch,
        "eval",
        "suite",
        "--split",
        "heldout",
        "--runs",
        "2",
        "--suite-dir",
        str(directory),
    )
    assert ran.exit_code == 0, ran.output
    combined = json.loads(
        next((fx.data / "reports").glob("suite-heldout-*-combined.json")).read_text()
    )
    assert len(combined["runs"]) == 2 and combined["freeze"].startswith("frozen on")


def test_review_import(fx: AnswerFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    directory = _suite_dir(tmp_path)
    _invoke(
        fx, _gen(), monkeypatch, "eval", "suite", "--split", "dev", "--suite-dir", str(directory)
    )
    reports = fx.data / "reports"
    sheet_path = sorted(reports.glob("suite-dev-*-review.yaml"))[-1]
    report_path = sorted(reports.glob("suite-dev-*-run1.json"))[-1]
    unfilled = _invoke(
        fx,
        _gen(),
        monkeypatch,
        "eval",
        "review",
        "import",
        "--sheet",
        str(sheet_path),
        "--report",
        str(report_path),
    )
    assert unfilled.exit_code == 2 and "reviewer and reviewed_on" in unfilled.output
    sheet = yaml.safe_load(sheet_path.read_text())
    sheet["reviewer"], sheet["reviewed_on"] = "owner", "2026-10-01"
    for case in sheet["cases"]:
        for claim in case["claims"]:
            claim["judgement"] = "supported"
    sheet_path.write_text(yaml.safe_dump(sheet, sort_keys=False))
    ok = _invoke(
        fx,
        _gen(),
        monkeypatch,
        "eval",
        "review",
        "import",
        "--sheet",
        str(sheet_path),
        "--report",
        str(report_path),
    )
    assert ok.exit_code == 0, ok.output
    assert "reviewer owner" in ok.stdout and list(reports.glob("human-review-*.json"))
