"""Container check evaluation from docker-inspect data (F009 FR-001–FR-003, SC-001)."""

from __future__ import annotations

from typing import Any

from score_docs_assistant.qualification.container import evaluate

APP: dict[str, Any] = {
    "Config": {"User": "1000:1000"},
    "HostConfig": {
        "ReadonlyRootfs": True,
        "CapDrop": ["ALL"],
        "SecurityOpt": ["no-new-privileges:true"],
        "Memory": 2 << 30,
        "NanoCpus": 2_000_000_000,
        "PidsLimit": 256,
    },
    "NetworkSettings": {"Ports": {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8080"}]}},
}
RUNTIME: dict[str, Any] = {
    "NetworkSettings": {"Ports": {"11434/tcp": None}, "Networks": {"p_internal": {}}}
}
OK = {"ok": True, "detail": "cited"}


def test_pass() -> None:
    report = evaluate(APP, RUNTIME, {"p_internal": True}, OK)
    assert report.status == "pass" and report.published_ports["runtime"] == []


def test_failures_are_named() -> None:
    public = {
        **APP,
        "NetworkSettings": {"Ports": {"8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}},
    }
    assert "not loopback-only" in evaluate(public, RUNTIME, {"p_internal": True}, OK).reason
    exposed = {
        "NetworkSettings": {
            "Ports": {"11434/tcp": [{"HostIp": "127.0.0.1", "HostPort": "11434"}]},
            "Networks": {"p_internal": {}},
        }
    }
    assert "runtime publishes" in evaluate(APP, exposed, {"p_internal": True}, OK).reason
    assert "not all internal" in evaluate(APP, RUNTIME, {"p_internal": False}, OK).reason
    root = {**APP, "Config": {"User": ""}}
    assert "root" in evaluate(root, RUNTIME, {"p_internal": True}, OK).reason
    assert "probe failed" in evaluate(APP, RUNTIME, {"p_internal": True}, {"ok": False}).reason
