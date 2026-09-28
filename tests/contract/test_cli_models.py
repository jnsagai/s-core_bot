"""`score-assistant models inspect|pull` (contracts/cli.md, US3 AS1-AS5)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import score_docs_assistant.cli.models as models_module
from score_docs_assistant.cli.main import cli_app
from score_docs_assistant.models.ollama import OllamaRuntime

runner = CliRunner()


@pytest.fixture
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SCORE_ASSISTANT_CONFIG", raising=False)
    return tmp_path


def _write_local_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "model-profiles.yaml").write_text(
        (Path(__file__).parent.parent.parent / "config" / "model-profiles.yaml").read_text()
    )
    config_file = config_dir / "local.yaml"
    config_file.write_text("schema_version: 1\nprofile: local\ndata_dir: ../data\n")
    return config_file


def _fake_ollama(
    fake_runtime: Callable[[dict | None], httpx.Client], scenario: dict
) -> OllamaRuntime:
    return OllamaRuntime("http://127.0.0.1:11434", client=fake_runtime(scenario))


def test_inspect_lists_roles_and_never_pulls(
    isolated_cwd: Path,
    fake_runtime: Callable[[dict | None], httpx.Client],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = _write_local_config(isolated_cwd)

    def _fail_pull(self: OllamaRuntime, tag: str) -> None:
        raise AssertionError("inspect must never call pull")

    monkeypatch.setattr(OllamaRuntime, "pull", _fail_pull)
    monkeypatch.setattr(
        models_module,
        "build_runtime",
        lambda config: _fake_ollama(
            fake_runtime,
            {
                "tags": {
                    "json": {
                        "models": [{"name": "qwen3:4b-instruct", "digest": "sha256:gen", "size": 1}]
                    }
                }
            },
        ),
    )

    result = runner.invoke(cli_app, ["--config", str(config_file), "models", "inspect", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    roles = {row["role"]: row for row in payload["models"]}
    assert roles["generation"]["present"] is True
    assert roles["generation"]["digest"] == "sha256:gen"
    assert roles["embedding"]["present"] is False
    assert roles["embedding"]["lock_status"] == "not_locked"


def test_inspect_runtime_unreachable_exits_1(
    isolated_cwd: Path,
    fake_runtime: Callable[[dict | None], httpx.Client],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = _write_local_config(isolated_cwd)
    monkeypatch.setattr(
        models_module,
        "build_runtime",
        lambda config: _fake_ollama(
            fake_runtime, {"tags": {"raise": httpx.ConnectError("refused")}}
        ),
    )
    result = runner.invoke(cli_app, ["--config", str(config_file), "models", "inspect"])
    assert result.exit_code == 1, result.output


def test_pull_help_first_line_states_network_use(isolated_cwd: Path) -> None:
    result = runner.invoke(cli_app, ["models", "pull", "--help"])
    assert result.exit_code == 0, result.output
    description_lines = [line.strip() for line in result.output.splitlines() if line.strip()]
    # First line is always "Usage: ..."; the command description follows immediately after.
    assert description_lines[1] == "Uses the network: downloads models via the local runtime."


def test_pull_unknown_profile_exits_2(
    isolated_cwd: Path,
    fake_runtime: Callable[[dict | None], httpx.Client],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = _write_local_config(isolated_cwd)
    monkeypatch.setattr(
        models_module, "build_runtime", lambda config: _fake_ollama(fake_runtime, {})
    )
    result = runner.invoke(
        cli_app, ["--config", str(config_file), "models", "pull", "--profile", "does-not-exist"]
    )
    assert result.exit_code == 2, result.output


def test_pull_disk_shortfall_exits_1_no_pull_sent(
    isolated_cwd: Path,
    fake_runtime: Callable[[dict | None], httpx.Client],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = _write_local_config(isolated_cwd)

    def _fail_pull(self: OllamaRuntime, tag: str) -> None:
        raise AssertionError("disk-insufficient must never call pull")

    monkeypatch.setattr(OllamaRuntime, "pull", _fail_pull)
    monkeypatch.setattr(
        models_module, "build_runtime", lambda config: _fake_ollama(fake_runtime, {})
    )
    monkeypatch.setattr(
        models_module.shutil, "disk_usage", lambda path: type("S", (), {"free": 1, "total": 1})()
    )

    result = runner.invoke(
        cli_app, ["--config", str(config_file), "models", "pull", "--profile", "local-small"]
    )
    assert result.exit_code == 1, result.output
    assert "DISK_INSUFFICIENT" in result.output


def test_pull_unknown_size_requires_override(
    isolated_cwd: Path,
    fake_runtime: Callable[[dict | None], httpx.Client],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = isolated_cwd / "config"
    config_dir.mkdir()
    (config_dir / "model-profiles.yaml").write_text(
        "schema_version: 1\n"
        "profiles:\n"
        "  local-small:\n"
        "    models:\n"
        "      - role: generation\n"
        "        tag: gen:latest\n"
        "        size_source: unknown\n"
        "      - role: embedding\n"
        "        tag: emb:latest\n"
        "        size_source: unknown\n"
    )
    config_file = config_dir / "local.yaml"
    config_file.write_text("schema_version: 1\nprofile: local\ndata_dir: ../data\n")

    def _fail_pull(self: OllamaRuntime, tag: str) -> None:
        raise AssertionError("must not pull before the size override is given")

    monkeypatch.setattr(OllamaRuntime, "pull", _fail_pull)
    monkeypatch.setattr(
        models_module, "build_runtime", lambda config: _fake_ollama(fake_runtime, {})
    )

    result = runner.invoke(
        cli_app, ["--config", str(config_file), "models", "pull", "--profile", "local-small"]
    )
    assert result.exit_code == 2, result.output


def _plenty_of_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keeps these tests independent of the machine's real free space (they failed on the
    # workstation once the models disk dropped below the profile size).
    monkeypatch.setattr(
        models_module.shutil,
        "disk_usage",
        lambda path: type("S", (), {"free": 10**15, "total": 10**15})(),
    )


def test_pull_writes_lock_and_second_run_is_already_present(
    isolated_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plenty_of_disk(monkeypatch)
    config_file = _write_local_config(isolated_cwd)
    state = {"pulled_gen": False, "pulled_emb": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.34.0"})
        if request.url.path == "/api/tags":
            models = []
            if state["pulled_gen"]:
                models.append({"name": "qwen3:4b-instruct", "digest": "sha256:gen", "size": 10})
            if state["pulled_emb"]:
                models.append(
                    {"name": "nomic-embed-text:latest", "digest": "sha256:emb", "size": 5}
                )
            return httpx.Response(200, json={"models": models})
        if request.url.path == "/api/pull":
            body = request.content
            payload = json.loads(body)
            if "qwen3" in payload["name"]:
                state["pulled_gen"] = True
            else:
                state["pulled_emb"] = True
            return httpx.Response(200, content=b'{"status": "success"}\n')
        return httpx.Response(404)

    def _build_runtime(config: object) -> OllamaRuntime:
        return OllamaRuntime(
            "http://127.0.0.1:11434",
            client=httpx.Client(
                transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:11434"
            ),
        )

    monkeypatch.setattr(models_module, "build_runtime", _build_runtime)

    first = runner.invoke(
        cli_app,
        ["--config", str(config_file), "models", "pull", "--profile", "local-small", "--json"],
    )
    assert first.exit_code == 0, first.output
    # stderr (pull progress lines) and stdout (the final JSON result) are mixed in `.output` by
    # default; the JSON result is always echoed last.
    first_payload = json.loads(first.output.strip().splitlines()[-1])
    actions = {row["tag"]: row["action"] for row in first_payload["models"]}
    assert actions["qwen3:4b-instruct"] == "pulled"
    assert actions["nomic-embed-text:latest"] == "pulled"

    lock_path = Path(first_payload["lock_path"])
    assert lock_path.exists()
    lock_data = json.loads(lock_path.read_text())
    digests = {m["tag"]: m["digest"] for m in lock_data["models"]}
    assert digests["qwen3:4b-instruct"] == "sha256:gen"

    second = runner.invoke(
        cli_app,
        ["--config", str(config_file), "models", "pull", "--profile", "local-small", "--json"],
    )
    assert second.exit_code == 0, second.output
    second_payload = json.loads(second.output.strip().splitlines()[-1])
    second_actions = {row["tag"]: row["action"] for row in second_payload["models"]}
    assert second_actions["qwen3:4b-instruct"] == "already_present"
    assert second_actions["nomic-embed-text:latest"] == "already_present"


def test_pull_refuses_remote_model(
    isolated_cwd: Path,
    fake_runtime: Callable[[dict | None], httpx.Client],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _plenty_of_disk(monkeypatch)
    config_file = _write_local_config(isolated_cwd)
    monkeypatch.setattr(
        models_module,
        "build_runtime",
        lambda config: _fake_ollama(
            fake_runtime,
            {
                "tags": {
                    "json": {
                        "models": [
                            {
                                "name": "qwen3:4b-instruct",
                                "digest": "sha256:gen",
                                "size": 1,
                                "remote_model": "cloud/qwen3",
                            }
                        ]
                    }
                }
            },
        ),
    )
    result = runner.invoke(
        cli_app, ["--config", str(config_file), "models", "pull", "--profile", "local-small"]
    )
    assert result.exit_code == 1, result.output
    assert "MODEL_REMOTE" in result.output
