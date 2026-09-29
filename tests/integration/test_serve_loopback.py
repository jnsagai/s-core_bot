"""`serve` in a real subprocess on a free loopback port with a real (fake) Ollama server:
listens on 127.0.0.1 only, endpoints respond, access log lines are body-free JSON, and readiness
reflects the runtime stopping (FR-010, FR-020, SC-007, constitution VIII)."""

from __future__ import annotations

import http.server
import json
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import psutil
import pytest

_KNOWN_LOG_KEYS = {
    "request_id",
    "method",
    "path",
    "status",
    "duration_ms",
    "event",
    "host",
    "port",
    "app_version",
    "profile",
    "deployment",  # F009: native | container (configuration, never message content)
    "log_file",  # F009: configured log path or null
}


class _FakeOllamaHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:
        if self.path == "/api/version":
            body = json.dumps({"version": "0.34.0"}).encode()
        elif self.path == "/api/tags":
            body = json.dumps({"models": []}).encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def fake_ollama_server() -> Iterator[http.server.ThreadingHTTPServer]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeOllamaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    try:
        server.shutdown()
        server.server_close()
    except OSError:
        pass
    thread.join(timeout=2)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_serve_loopback_only_and_readiness_reflects_runtime(
    tmp_path: Path,
    fake_ollama_server: http.server.ThreadingHTTPServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCORE_ASSISTANT_CONFIG", raising=False)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "model-profiles.yaml").write_text(
        (Path(__file__).parent.parent.parent / "config" / "model-profiles.yaml").read_text()
    )
    fake_port = fake_ollama_server.server_address[1]
    serve_port = _free_port()
    config_file = config_dir / "local.yaml"
    config_file.write_text(
        "schema_version: 1\n"
        "profile: local\n"
        "data_dir: ../data\n"
        "server:\n"
        f"  port: {serve_port}\n"
        "runtime:\n"
        f"  base_url: http://127.0.0.1:{fake_port}\n"
        "diagnostics:\n"
        "  readiness_cache_seconds: 0\n"
    )

    score_assistant = Path(sys.executable).parent / "score-assistant"
    proc = subprocess.Popen(
        [str(score_assistant), "--config", str(config_file), "serve"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base_url = f"http://127.0.0.1:{serve_port}"
        deadline = time.monotonic() + 10
        last_error: Exception | None = None
        ready = False
        while time.monotonic() < deadline:
            try:
                response = httpx.get(f"{base_url}/health/live", timeout=0.5)
                if response.status_code == 200:
                    ready = True
                    break
            except httpx.HTTPError as exc:
                last_error = exc
            time.sleep(0.1)
        assert ready, f"server did not become ready in time: {last_error}"

        live = httpx.get(f"{base_url}/health/live", timeout=2)
        assert live.status_code == 200
        assert live.json() == {"status": "alive"}

        ready_before = httpx.get(f"{base_url}/health/ready", timeout=5).json()

        capabilities = httpx.get(f"{base_url}/api/v1/capabilities", timeout=2)
        assert capabilities.status_code == 200

        proc_handle = psutil.Process(proc.pid)
        listening = {
            (conn.laddr.ip, conn.laddr.port)
            for conn in proc_handle.net_connections(kind="inet")
            if conn.status == psutil.CONN_LISTEN
        }
        assert listening, "expected the server to be listening"
        assert all(ip == "127.0.0.1" for ip, _port in listening)

        fake_ollama_server.shutdown()
        fake_ollama_server.server_close()

        ready_after = httpx.get(f"{base_url}/health/ready", timeout=8).json()
        assert "runtime_unreachable" not in str(ready_before)
        assert "runtime_unreachable" in str(ready_after)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    stderr_output = proc.stderr.read() if proc.stderr else ""
    for line in stderr_output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        assert set(payload) <= _KNOWN_LOG_KEYS, payload
