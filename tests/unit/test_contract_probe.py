"""Contract signature and comparison (F009 FR-008, SC-004)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from score_docs_assistant.qualification.contract import compare, main, probe, shape

SEARCH = {
    "snapshot_id": "S",
    "results": [{"snapshot_id": "S", "chunk_id": "c", "rank": 1}],
    "mode": "hybrid",
}


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    body = {
        "/api/v1/search": SEARCH,
        "/api/v1/snapshots": {
            "active": "S",
            "snapshots": [{"snapshot_id": "S"}, {"snapshot_id": "T"}],
        },
        "/api/v1/chat": {"status": "answered", "citations": [], "timings_ms": {"total": 1.5}},
    }.get(path, {"ok": True})
    return httpx.Response(422 if b'"model"' in request.content else 200, json=body)


def test_shape_ignores_values_and_lengths() -> None:
    assert shape({"a": [1, 2, 3], "b": {"c": "x"}}) == shape({"a": [9], "b": {"c": "y"}})
    assert shape({"a": 1}) != shape({"a": "1"})
    assert shape([{"k": 1}, {"k": 2}]) == [{"k": "int"}]


def test_probe_and_compare(tmp_path: Path) -> None:
    client = httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler))
    sig = probe(client)
    assert {
        "health_live",
        "search",
        "citation",
        "chat_json",
        "chat_invalid",
        "snapshot_diff",
    } <= set(sig)
    assert sig["chat_invalid"]["status"] == 422
    assert compare(sig, sig) == []
    changed = json.loads(json.dumps(sig))
    changed["search"]["shape"]["mode"] = "int"
    del changed["snapshot_diff"]
    assert compare(sig, changed) == ["search: status/shape differs", "snapshot_diff: only in A"]


def test_cli_compare(tmp_path: Path) -> None:
    for name in ("a", "b"):
        (tmp_path / f"{name}.json").write_text(
            json.dumps({"label": name, "signatures": {"x": {"status": 200, "shape": {}}}})
        )
    out = tmp_path / "r.json"
    assert (
        main(["--compare", str(tmp_path / "a.json"), str(tmp_path / "b.json"), "--out", str(out)])
        == 0
    )
    assert json.loads(out.read_text())["equal"] is True
