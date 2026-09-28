"""doctor against a real loopback port that accepts but never responds: RUNTIME_TIMEOUT within
10 s wall time (SC-002)."""

from __future__ import annotations

import contextlib
import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from score_docs_assistant.cli.main import cli_app

runner = CliRunner()


@pytest.fixture
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SCORE_ASSISTANT_CONFIG", raising=False)
    return tmp_path


@pytest.fixture
def silent_loopback_port() -> Iterator[int]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(0.2)
    port = server.getsockname()[1]
    stop = threading.Event()

    def _accept_and_ignore() -> None:
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with contextlib.suppress(OSError):
                conn.recv(1)

    thread = threading.Thread(target=_accept_and_ignore, daemon=True)
    thread.start()
    yield port
    stop.set()
    server.close()
    thread.join(timeout=1)


def test_doctor_reports_runtime_timeout_within_10s(
    isolated_cwd: Path, silent_loopback_port: int
) -> None:
    config_dir = isolated_cwd / "config"
    config_dir.mkdir()
    (config_dir / "model-profiles.yaml").write_text(
        (Path(__file__).parent.parent.parent / "config" / "model-profiles.yaml").read_text()
    )
    config_file = config_dir / "local.yaml"
    config_file.write_text(
        "schema_version: 1\n"
        "profile: local\n"
        "data_dir: ../data\n"
        "runtime:\n"
        f"  base_url: http://127.0.0.1:{silent_loopback_port}\n"
        "diagnostics:\n"
        "  runtime_connect_timeout_seconds: 1.0\n"
        "  runtime_read_timeout_seconds: 1.0\n"
    )

    started = time.monotonic()
    result = runner.invoke(cli_app, ["--config", str(config_file), "doctor", "--json"])
    elapsed = time.monotonic() - started

    assert elapsed < 10, f"doctor took {elapsed:.1f}s"
    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    reachable = next(c for c in payload["checks"] if c["id"] == "runtime.reachable")
    assert reachable["code"] == "RUNTIME_TIMEOUT"
    assert reachable["next_action"]
