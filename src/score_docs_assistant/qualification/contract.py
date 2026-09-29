"""API contract parity between deployments (F009 FR-008, SC-004).

Probes one base URL and records, per endpoint, the status code and the key/type tree of the
response. Values (IDs, timings, text) are not compared; list lengths are ignored.

    python -m score_docs_assistant.qualification.contract --base-url URL --out SIGNATURE
    python -m score_docs_assistant.qualification.contract --compare A B [--out REPORT]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

HOST = {"host": "127.0.0.1:8080"}
QUESTION = "What is the recommended way to set up the development environment?"


def shape(value: Any) -> Any:
    """Key/type tree; lists collapse to the union of their item shapes."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        items = [shape(v) for v in value]
        merged: list[Any] = []
        for item in items:
            if item not in merged:
                merged.append(item)
        return merged[:1] if all(isinstance(i, dict) for i in merged) else sorted(map(str, merged))
    if value is None:
        return "null"
    return type(value).__name__


def probe(client: httpx.Client) -> dict[str, Any]:
    def call(method: str, path: str, **kw: Any) -> tuple[int, Any]:
        response = client.request(method, path, headers=HOST, **kw)
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, response.text[:0]

    signatures: dict[str, Any] = {}

    def record(name: str, method: str, path: str, **kw: Any) -> Any:
        status, body = call(method, path, **kw)
        signatures[name] = {"status": status, "shape": shape(body)}
        return body

    record("health_live", "GET", "/health/live")
    record("health_ready", "GET", "/health/ready")
    record("capabilities", "GET", "/api/v1/capabilities")
    snapshots = record("snapshots", "GET", "/api/v1/snapshots")
    search = record("search", "POST", "/api/v1/search", json={"query": "devcontainer"})
    first = (search.get("results") or [{}])[0]
    record(
        "citation", "GET", f"/api/v1/citations/{first.get('snapshot_id')}/{first.get('chunk_id')}"
    )
    record("entities", "GET", "/api/v1/entities", params={"id": "feat_req__com__interfaces"})
    record("chat_json", "POST", "/api/v1/chat", json={"question": QUESTION}, timeout=600)
    record("chat_invalid", "POST", "/api/v1/chat", json={"question": "q", "model": "x"})
    ids = [s["snapshot_id"] for s in snapshots.get("snapshots", [])]
    if len(ids) >= 2:
        record(
            "snapshot_diff",
            "GET",
            "/api/v1/snapshots/diff",
            params={"left": ids[1], "right": ids[0]},
        )
    return signatures


def compare(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    differences = []
    for name in sorted(a.keys() | b.keys()):
        if name not in a or name not in b:
            differences.append(f"{name}: only in {'A' if name in a else 'B'}")
        elif a[name] != b[name]:
            differences.append(f"{name}: status/shape differs")
    return differences


def main(
    argv: list[str] | None = None, client_factory: Callable[[str], httpx.Client] | None = None
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--compare", nargs=2, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.compare:
        left, right = (json.loads(p.read_text()) for p in args.compare)
        differences = compare(left["signatures"], right["signatures"])
        report = {
            "created_at": datetime.now(UTC).isoformat(),
            "left": {"file": args.compare[0].name, "label": left.get("label")},
            "right": {"file": args.compare[1].name, "label": right.get("label")},
            "endpoints": len(left["signatures"]),
            "equal": not differences,
            "differences": differences,
            "status": "pass" if not differences else "fail",
        }
        if args.out:
            args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(
            f"contract parity: {report['status']} ({report['endpoints']} endpoints) {differences}"
        )
        return 0 if not differences else 1
    factory = client_factory or (lambda url: httpx.Client(base_url=url, timeout=60))
    with factory(args.base_url) as client:
        signatures = probe(client)
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "label": args.base_url,
        "signatures": signatures,
    }
    assert args.out is not None
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"signature: {len(signatures)} endpoints → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
