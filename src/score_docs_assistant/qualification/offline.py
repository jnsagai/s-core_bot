"""Blocked-egress probe (F008 FR-011, AT-01, research R6).

Run by `scripts/offline_check.sh` inside an unprivileged network namespace that has only a
loopback interface, with a private local runtime and `serve` started there. It first proves that
external egress fails, then exercises the application over loopback HTTP and writes a report.

    python -m score_docs_assistant.qualification.offline --out REPORT [--log SERVER_LOG]
    python -m score_docs_assistant.qualification.offline --out REPORT --not-run "reason"
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

QUESTION = "What is the recommended way to set up the development environment?"
SEARCH_QUERY = "devcontainer development environment"
HOST_HEADERS = {"host": "127.0.0.1:8080"}
_FORBID = ConfigDict(extra="forbid", frozen=True)


class Step(BaseModel):
    model_config = _FORBID

    name: str
    ok: bool
    detail: str


class OfflineReport(BaseModel):
    model_config = _FORBID

    status: str  # pass | fail | not run
    created_at: datetime
    reason: str
    egress: dict[str, bool]
    steps: list[Step]


def dns_blocked(host: str = "github.com") -> bool:
    try:
        socket.getaddrinfo(host, 443)
    except OSError:
        return True
    return False


def tcp_blocked(address: tuple[str, int] = ("1.1.1.1", 443), timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection(address, timeout=timeout):
            return False
    except OSError:
        return True


def _sse_answer(text: str) -> dict[str, Any] | None:
    for block in text.split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        if lines.get("event") == "answer":
            data: dict[str, Any] = json.loads(lines["data"])
            return data
    return None


def probe(
    client: httpx.Client,
    *,
    lock_digest: str | None,
    log_text: str = "",
    egress: Callable[[], dict[str, bool]] | None = None,
) -> OfflineReport:
    blocked = (egress or (lambda: {"dns": dns_blocked(), "tcp": tcp_blocked()}))()
    steps: list[Step] = [
        Step(
            name="external egress blocked",
            ok=all(blocked.values()),
            detail=(
                f"DNS lookup failed: {blocked.get('dns')}; "
                f"TCP 1.1.1.1:443 failed: {blocked.get('tcp')}"
            ),
        )
    ]

    def step(name: str, action: Callable[[], tuple[bool, str]]) -> None:
        try:
            ok, detail = action()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        steps.append(Step(name=name, ok=ok, detail=detail))

    def ready() -> tuple[bool, str]:
        body = client.get("/health/ready", headers=HOST_HEADERS).json()
        chat = body["capabilities"]["chat"]
        return bool(chat["available"]), f"chat {chat}"

    def ui() -> tuple[bool, str]:
        response = client.get("/", headers=HOST_HEADERS)
        return response.status_code == 200 and "<html" in response.text.lower(), (
            f"GET / → {response.status_code}"
        )

    answer: dict[str, Any] = {}

    def ask() -> tuple[bool, str]:
        response = client.post(
            "/api/v1/chat",
            json={"question": QUESTION},
            headers={**HOST_HEADERS, "accept": "text/event-stream"},
            timeout=180,
        )
        found = _sse_answer(response.text)
        if found is None:
            return False, f"no answer event (HTTP {response.status_code})"
        answer.update(found)
        cited = len(found.get("citations", []))
        return found.get("status") in ("answered", "partial") and cited > 0, (
            f"status {found.get('status')}, {cited} citation(s), origin {found.get('origin')}"
        )

    def excerpt() -> tuple[bool, str]:
        first = answer["citations"][0]
        response = client.get(
            f"/api/v1/citations/{first['snapshot_id']}/{first['chunk_id']}", headers=HOST_HEADERS
        )
        text = response.json().get("text", "")
        return response.status_code == 200 and bool(
            text
        ), f"{first['path']}: {len(text)} characters"

    def search() -> tuple[bool, str]:
        body = client.post(
            "/api/v1/search", json={"query": SEARCH_QUERY}, headers=HOST_HEADERS
        ).json()
        return len(body["results"]) > 0, f"{len(body['results'])} results, mode {body['mode']}"

    def export() -> tuple[bool, str]:
        required = ("question", "claims", "citations", "snapshot_id", "model")
        missing = [k for k in required if not answer.get(k)]
        return (
            not missing,
            "export fields present (client-side export uses only these)"
            if not missing
            else f"missing {missing}",
        )

    def model() -> tuple[bool, str]:
        digest = (answer.get("model") or {}).get("digest")
        if lock_digest is None:
            return False, "no generation digest in the model lock"
        return (
            digest == lock_digest,
            f"answer model digest {str(digest)[:12]}… vs lock {lock_digest[:12]}…",
        )

    def privacy() -> tuple[bool, str]:
        leaked = QUESTION in log_text
        return (
            not leaked,
            f"question text in server log: {'yes' if leaked else 'no'} "
            f"({len(log_text)} bytes scanned)",
        )

    step("readiness: chat available", ready)
    step("web UI served", ui)
    step("ask: cited answer", ask)
    if answer:
        step("open cited excerpt", excerpt)
    step("search", search)
    if answer:
        step("export fields", export)
        step("model matches lock", model)
    step("no question text in server log", privacy)
    ok = all(s.ok for s in steps)
    return OfflineReport(
        status="pass" if ok else "fail",
        created_at=datetime.now(UTC),
        reason="all steps passed" if ok else "; ".join(s.name for s in steps if not s.ok),
        egress=blocked,
        steps=steps,
    )


def _lock_digest(path: Path) -> str | None:
    try:
        lock = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    for model in lock.get("models", []):
        if model.get("role") == "generation":
            return str(model.get("digest", "")).removeprefix("sha256:")
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--lock", type=Path, default=Path("data/model-lock.json"))
    parser.add_argument("--log", type=Path)
    parser.add_argument("--not-run", dest="not_run")
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.not_run:
        report = OfflineReport(
            status="not run",
            created_at=datetime.now(UTC),
            reason=args.not_run,
            egress={},
            steps=[],
        )
    else:
        log_text = args.log.read_text(errors="replace") if args.log and args.log.exists() else ""
        with httpx.Client(base_url=args.base_url, timeout=30) as client:
            report = probe(client, lock_digest=_lock_digest(args.lock), log_text=log_text)
    args.out.write_text(report.model_dump_json(indent=2) + "\n")
    for s in report.steps:
        print(f"  {'ok  ' if s.ok else 'FAIL'} {s.name}: {s.detail}")
    print(f"offline check: {report.status} — {report.reason}")
    return 0 if report.status != "fail" else 1


if __name__ == "__main__":
    sys.exit(main())
