"""An explicitly requested but missing config file stops every command with exit 2 (A-061).

Before, the loader fell back to the defaults (`data_dir: data`), so a mistyped `--config` made
`snapshots rollback` or `refresh` act on the real ./data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from score_docs_assistant.cli.main import cli_app

runner = CliRunner()

COMMANDS = [
    ["doctor"],
    ["snapshots", "list"],
    ["snapshots", "rollback"],
    ["snapshots", "activate", "20260101T000000Z-00000000"],
    ["index", "build"],
    ["refresh"],
    ["search", "watchdog"],
    ["serve"],
]


@pytest.mark.parametrize("args", COMMANDS, ids=lambda a: " ".join(a))
def test_missing_config_exits_2_and_touches_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SCORE_ASSISTANT_CONFIG", raising=False)
    result = runner.invoke(cli_app, ["--config", "/refresh.yaml", *args])
    assert result.exit_code == 2, result.output
    assert "config file not found: /refresh.yaml" in result.output
    assert not (tmp_path / "data").exists()
