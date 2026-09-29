"""Compose and image policy (F009 FR-001–FR-003, SC-001): committed files must keep the runtime
private, publish the app on loopback only, and keep the hardening."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).parent.parent.parent
COMPOSE: dict[str, Any] = yaml.safe_load((REPO / "compose.yaml").read_text())
SERVICES: dict[str, Any] = COMPOSE["services"]


def test_runtime_has_no_host_port_and_only_the_internal_network() -> None:
    ollama = SERVICES["ollama"]
    assert "ports" not in ollama and "network_mode" not in ollama
    assert ollama["networks"] == ["internal"]
    assert COMPOSE["networks"]["internal"]["internal"] is True
    assert any(v.endswith(":/models:ro") for v in ollama["volumes"])
    assert ollama["environment"]["OLLAMA_NOPRUNE"] == "1"
    assert "@sha256:" in ollama["image"]


def test_app_publishes_on_loopback_only() -> None:
    for name, service in SERVICES.items():
        for port in service.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), f"{name} publishes {port} beyond loopback"
    assert SERVICES["app"]["ports"] == ["127.0.0.1:${SCORE_PORT:-8080}:8080"]


@pytest.mark.parametrize("name", ["app", "app-host"])
def test_app_hardening(name: str) -> None:
    app = SERVICES[name]
    assert app["read_only"] is True and app["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in app["security_opt"]
    assert app["mem_limit"] and app["cpus"] and app["pids_limit"]
    assert app["logging"]["options"]["max-file"] == "7"
    assert not str(app["user"]).startswith("0")


def test_host_runtime_profile_uses_native_loopback_config() -> None:
    app = SERVICES["app-host"]
    assert app["network_mode"] == "host" and "ports" not in app
    config = yaml.safe_load((REPO / "config" / "host-runtime.yaml").read_text())
    assert config["server"]["host"] == "127.0.0.1" and config["deployment"]["mode"] == "native"
    assert config["runtime"]["base_url"] == "http://127.0.0.1:11434"


def test_dockerfile_policy() -> None:
    text = (REPO / "Dockerfile").read_text()
    froms = re.findall(r"^FROM (\S+)", text, re.M)
    assert froms and all("@sha256:" in f for f in froms)
    assert "USER 10001:10001" in text and "SCORE_ASSISTANT_CONTAINER=1" in text
    assert "uv sync --frozen --no-dev" in text and "HEALTHCHECK" in text
    ignore = (REPO / ".dockerignore").read_text().split()
    assert {"data", ".venv", ".git", "frontend/node_modules"} <= set(ignore)
