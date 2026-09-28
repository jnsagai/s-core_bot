"""Shared test fixtures: the network guard, fake Ollama runtime, and tmp config/data dirs.

See specs/001-foundation/research.md R12 for the isolation rationale.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex


def _is_loopback_address(address: Any) -> bool:
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _guarded_connect(self: socket.socket, address: Any) -> Any:
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback_address(address):
        raise OSError(f"network guard: non-loopback connect blocked: {address!r}")
    return _ORIGINAL_CONNECT(self, address)


def _guarded_connect_ex(self: socket.socket, address: Any) -> Any:
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback_address(address):
        raise OSError(f"network guard: non-loopback connect blocked: {address!r}")
    return _ORIGINAL_CONNECT_EX(self, address)


@pytest.fixture(autouse=True)
def _network_guard(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    # The guard is lifted only for tests explicitly marked `real_network` *and* opted in.
    opted_in = os.environ.get("SCORE_ASSISTANT_REAL_NETWORK") == "1"
    if opted_in and request.node.get_closest_marker("real_network") is not None:
        return
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_connect_ex)


_OPT_IN = {
    "real_runtime": ("SCORE_ASSISTANT_REAL_RUNTIME", "requires a real Ollama runtime"),
    "real_network": ("SCORE_ASSISTANT_REAL_NETWORK", "contacts GitHub"),
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for marker, (variable, why) in _OPT_IN.items():
        if os.environ.get(variable) == "1":
            continue
        skip = pytest.mark.skip(reason=f"{why} ({variable}=1); not run")
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    d = tmp_path / "config"
    d.mkdir()
    return d


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


FakeRuntimeScenario = dict[str, dict[str, Any]]


def _make_fake_transport(scenario: FakeRuntimeScenario) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            behavior = scenario.get("version", {"json": {"version": "0.34.0"}})
        elif request.url.path == "/api/tags":
            behavior = scenario.get("tags", {"json": {"models": []}})
        elif request.url.path == "/api/pull":
            behavior = scenario.get("pull", {"json": {"status": "success"}})
        else:
            return httpx.Response(404, json={"error": "not found"})
        if "raise" in behavior:
            raise behavior["raise"]
        kwargs = {k: v for k, v in behavior.items() if k != "status_code"}
        return httpx.Response(behavior.get("status_code", 200), **kwargs)

    return httpx.MockTransport(handler)


@pytest.fixture
def fake_runtime() -> Callable[[FakeRuntimeScenario | None], httpx.Client]:
    """Factory: `fake_runtime({"version": {...}, "tags": {...}, "pull": {...}})` -> httpx.Client."""

    def _build(scenario: FakeRuntimeScenario | None = None) -> httpx.Client:
        transport = _make_fake_transport(scenario or {})
        return httpx.Client(transport=transport, base_url="http://127.0.0.1:11434")

    return _build
