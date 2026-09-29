"""Blocked-egress probe logic against a mocked HTTP transport (F008 FR-011; mocked)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from score_docs_assistant.qualification.offline import QUESTION, main, probe

SNAP, CHUNK, DIGEST = "20260928T140548Z-7c6a05b3", "c" * 64, "0edcdef3" + "0" * 56
ANSWER = {
    "status": "answered",
    "origin": "model",
    "question": QUESTION,
    "snapshot_id": SNAP,
    "claims": [{"text": "Use the devcontainer.", "kind": "documented", "evidence_ids": ["E1"]}],
    "citations": [
        {"evidence_id": "E1", "snapshot_id": SNAP, "chunk_id": CHUNK, "path": "docs/x.rst"}
    ],
    "model": {"name": "qwen3:4b-instruct", "digest": DIGEST},
}


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/health/ready":
        return httpx.Response(
            200, json={"capabilities": {"chat": {"available": True, "reasons": []}}}
        )
    if path == "/":
        return httpx.Response(200, text="<!doctype html><html></html>")
    if path == "/api/v1/chat":
        answer = json.dumps(ANSWER)
        body = f"id: 1\nevent: progress\ndata: {{}}\n\nid: 2\nevent: answer\ndata: {answer}\n\n"
        return httpx.Response(200, text=body)
    if path.startswith("/api/v1/citations/"):
        return httpx.Response(200, json={"text": "The recommended way is the devcontainer."})
    if path == "/api/v1/search":
        return httpx.Response(200, json={"results": [{}], "mode": "hybrid"})
    return httpx.Response(404)


def client() -> httpx.Client:
    return httpx.Client(base_url="http://127.0.0.1:8080", transport=httpx.MockTransport(handler))


def test_pass_when_everything_works() -> None:
    report = probe(client(), lock_digest=DIGEST, egress=lambda: {"dns": True, "tcp": True})
    assert report.status == "pass", report.reason
    assert [s.name for s in report.steps][0] == "external egress blocked"


def test_fail_when_egress_open_or_digest_differs_or_log_leaks() -> None:
    open_net = probe(client(), lock_digest=DIGEST, egress=lambda: {"dns": False, "tcp": True})
    assert open_net.status == "fail" and "external egress blocked" in open_net.reason
    other = probe(client(), lock_digest="9" * 64, egress=lambda: {"dns": True, "tcp": True})
    assert "model matches lock" in other.reason
    leaky = probe(
        client(),
        lock_digest=DIGEST,
        log_text=f"q={QUESTION}",
        egress=lambda: {"dns": True, "tcp": True},
    )
    assert "no question text in server log" in leaky.reason


def test_not_run_report(tmp_path: Path) -> None:
    out = tmp_path / "offline.json"
    assert main(["--out", str(out), "--not-run", "unshare unavailable"]) == 0
    data = json.loads(out.read_text())
    assert data["status"] == "not run" and data["reason"] == "unshare unavailable"
