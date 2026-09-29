"""Container deployment check (F009 FR-001–FR-003, SC-001).

Reads `docker inspect` of the running Compose services and probes the published app:
- every published host port must be bound to 127.0.0.1;
- the runtime must publish none and sit on an internal network;
- the app must run hardened;
- a cited answer must come back through the stack.

    python -m score_docs_assistant.qualification.container --project NAME --out REPORT
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

HOST = {"host": "127.0.0.1:8080"}
_FORBID = ConfigDict(extra="forbid", frozen=True)


class ContainerReport(BaseModel):
    model_config = _FORBID

    created_at: datetime
    status: str
    reason: str
    published_ports: dict[str, list[str]]
    runtime_networks_internal: bool | None
    app_security: dict[str, Any]
    probe: dict[str, Any]


def published(inspect: dict[str, Any]) -> list[str]:
    ports = (inspect.get("NetworkSettings") or {}).get("Ports") or {}
    return [
        f"{b.get('HostIp')}:{b.get('HostPort')}->{port}"
        for port, bindings in ports.items()
        for b in (bindings or [])
    ]


def security(inspect: dict[str, Any]) -> dict[str, Any]:
    host = inspect.get("HostConfig") or {}
    return {
        "user": (inspect.get("Config") or {}).get("User"),
        "read_only": host.get("ReadonlyRootfs"),
        "cap_drop": host.get("CapDrop"),
        "security_opt": host.get("SecurityOpt"),
        "memory": host.get("Memory"),
        "nano_cpus": host.get("NanoCpus"),
        "pids_limit": host.get("PidsLimit"),
    }


def evaluate(
    app: dict[str, Any],
    runtime: dict[str, Any],
    networks: dict[str, bool],
    probe: dict[str, Any],
) -> ContainerReport:
    ports = {"app": published(app), "runtime": published(runtime)}
    sec = security(app)
    problems: list[str] = []
    if not ports["app"] or not all(p.startswith("127.0.0.1:") for p in ports["app"]):
        problems.append(f"app ports not loopback-only: {ports['app']}")
    if ports["runtime"]:
        problems.append(f"runtime publishes {ports['runtime']}")
    runtime_nets = list(((runtime.get("NetworkSettings") or {}).get("Networks") or {}).keys())
    internal = bool(runtime_nets) and all(networks.get(n, False) for n in runtime_nets)
    if not internal:
        problems.append(f"runtime networks not all internal: {runtime_nets}")
    if not (
        sec["read_only"] and sec["cap_drop"] == ["ALL"] and sec["memory"] and sec["pids_limit"]
    ):
        problems.append("app hardening incomplete")
    if str(sec["user"]).split(":")[0] in ("", "0", "root"):
        problems.append("app runs as root")
    if not probe.get("ok"):
        problems.append(f"probe failed: {probe.get('detail')}")
    return ContainerReport(
        created_at=datetime.now(UTC),
        status="pass" if not problems else "fail",
        reason="; ".join(problems)
        or "loopback-only app port, private runtime, hardened, cited answer",
        published_ports=ports,
        runtime_networks_internal=internal,
        app_security=sec,
        probe=probe,
    )


def probe_app(
    base_url: str, client_factory: Callable[[], httpx.Client] | None = None
) -> dict[str, Any]:
    factory = client_factory or (lambda: httpx.Client(base_url=base_url, timeout=300))
    with factory() as client:
        ready = client.get("/health/ready", headers=HOST).json()
        search = client.post("/api/v1/search", json={"query": "devcontainer"}, headers=HOST).json()
        answer = client.post(
            "/api/v1/chat",
            json={"question": "What is the recommended way to set up the development environment?"},
            headers=HOST,
        )
        body = answer.json()
    cited = len(body.get("citations", [])) if answer.status_code == 200 else 0
    ok = (
        bool(ready["capabilities"]["chat"]["available"])
        and bool(search.get("results"))
        and cited > 0
    )
    return {
        "ok": ok,
        "detail": (
            f"chat ready {ready['capabilities']['chat']}, "
            f"search {len(search.get('results', []))} results, answer HTTP {answer.status_code} "
            f"status {body.get('status')} with {cited} citation(s)"
        ),
        "answer_model_digest": (body.get("model") or {}).get("digest"),
        "latency_ms": (body.get("timings_ms") or {}).get("total"),
    }


def _docker(*args: str) -> Any:
    out = subprocess.run(["docker", *args], capture_output=True, text=True, check=True)  # noqa: S603, S607
    return json.loads(out.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    args = parser.parse_args(argv)
    app = _docker("inspect", f"{args.project}-app-1")[0]
    runtime = _docker("inspect", f"{args.project}-ollama-1")[0]
    names = list(((runtime.get("NetworkSettings") or {}).get("Networks") or {}).keys())
    networks = {n: bool(_docker("network", "inspect", n)[0].get("Internal")) for n in names}
    try:
        probe = probe_app(args.base_url)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        probe = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
    report = evaluate(app, runtime, networks, probe)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report.model_dump_json(indent=2) + "\n")
    print(f"container check: {report.status} — {report.reason}")
    print(f"ports {report.published_ports}  probe: {report.probe.get('detail')}")
    return 0 if report.status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
