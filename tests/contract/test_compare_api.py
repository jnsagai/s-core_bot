"""`POST /api/v1/compare` and `GET /api/v1/snapshots/diff` contracts (FR-001, FR-012–FR-016).

Mocked providers over two fixture snapshots.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest
from starlette.testclient import TestClient

from score_docs_assistant.api.app import create_app, create_fastapi_app
from score_docs_assistant.domain.answers import ChatRequest
from score_docs_assistant.domain.models import ModelProfile, ProfileModel
from score_docs_assistant.readiness import ReadinessService
from score_docs_assistant.storage.corpus_probe import FileCorpusProbe
from tests.contract.test_chat_api import _Runtime
from tests.helpers.comparison_fixtures import (
    ComparisonFixture,
    answer_citing_all,
    make_comparison_fixture,
)
from tests.helpers.fake_generation import LOCKED_GENERATION_DIGEST, FakeGenerationProvider
from tests.integration.test_chat_admission import _asgi_call

HOST = {"host": "127.0.0.1:8080"}
EMPTY = json.dumps({"differences": []})
QUESTION = "How many reviewers perform inspections?"


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> ComparisonFixture:
    return make_comparison_fixture(tmp_path_factory.mktemp("compare-api"))


def _client(fx: ComparisonFixture, generator: FakeGenerationProvider, **config: Any) -> TestClient:
    service = fx.service(generator, **config)
    readiness = ReadinessService(
        config=fx.config(**config),
        runtime=_Runtime(LOCKED_GENERATION_DIGEST),  # type: ignore[arg-type]
        corpus_probe=FileCorpusProbe(fx.data),
        profile=ModelProfile(
            name="p",
            models=[ProfileModel(role="generation", tag="qwen3:4b-instruct", size_source="t")],
        ),
        cache_seconds=0,
    )
    app = create_app(
        config=fx.config(**config),
        readiness_service=readiness,
        search_service=service._search,  # noqa: SLF001
        answer_service=service._answers,  # noqa: SLF001
    )
    return TestClient(app, base_url="http://127.0.0.1:8080")


def _body(fx: ComparisonFixture, **overrides: Any) -> dict[str, Any]:
    return {
        "question": QUESTION,
        "left_snapshot_id": fx.left_id,
        "right_snapshot_id": fx.right_id,
        **overrides,
    }


def _generator() -> FakeGenerationProvider:
    return FakeGenerationProvider(outputs=[answer_citing_all, answer_citing_all, EMPTY])


def _events(text: str) -> list[tuple[int, str, dict[str, Any]]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((int(lines["id"]), lines["event"], json.loads(lines["data"])))
    return events


def test_json_comparison(fx: ComparisonFixture) -> None:
    response = _client(fx, _generator()).post("/api/v1/compare", json=_body(fx), headers=HOST)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == 1
    assert body["left"]["snapshot_id"] == fx.left_id and body["right"]["snapshot_id"] == fx.right_id
    assert body["snapshots"]["release_label"] is None
    assert {c["snapshot_id"] for c in body["evidence"]["left"]} == {fx.left_id}
    assert response.headers["cache-control"] == "no-store"


def test_sse_order_sides_and_no_early_text(fx: ComparisonFixture) -> None:
    response = _client(fx, _generator()).post(
        "/api/v1/compare", json=_body(fx), headers={**HOST, "accept": "text/event-stream"}
    )
    events = _events(response.text)
    ids = [e[0] for e in events]
    assert ids == list(range(1, len(ids) + 1))
    names = [e[1] for e in events]
    assert names[-2:] == ["comparison", "done"] and names.count("comparison") == 1
    progress = [e[2] for e in events if e[1] == "progress"]
    assert progress[0] == {"stage": "searching", "side": "left"}
    sides = [p.get("side") for p in progress if p["stage"] != "comparing"]
    assert sides.index("right") > max(i for i, s in enumerate(sides) if s == "left")
    assert progress[-1] == {"stage": "comparing"}
    before = response.text.split("event: comparison", 1)[0]
    assert "documents this" not in before  # claim text only in the final event


def test_sse_error_event(fx: ComparisonFixture) -> None:
    response = _client(fx, FakeGenerationProvider(unavailable="runtime_unreachable")).post(
        "/api/v1/compare", json=_body(fx), headers={**HOST, "accept": "text/event-stream"}
    )
    events = _events(response.text)
    assert [e[1] for e in events] == ["error", "done"]
    assert events[0][2]["error"]["code"] == "GENERATION_UNAVAILABLE"


@pytest.mark.parametrize(
    ("overrides", "status", "code"),
    [
        ({"history": []}, 422, "REQUEST_INVALID"),
        ({"model": "gpt-4"}, 422, "REQUEST_INVALID"),
        ({"right_snapshot_id": "same"}, 422, "REQUEST_INVALID"),
        ({"left_snapshot_id": "not an id"}, 422, "REQUEST_INVALID"),
        ({"question": "x" * 4001}, 422, "REQUEST_INVALID"),
        ({"response_language": "de"}, 422, "UNSUPPORTED_LANGUAGE"),
        ({"right_snapshot_id": "20990101T000000Z-00000000"}, 404, "SNAPSHOT_NOT_FOUND"),
    ],
)
def test_errors(fx: ComparisonFixture, overrides: dict[str, Any], status: int, code: str) -> None:
    if overrides.get("right_snapshot_id") == "same":
        overrides = {"right_snapshot_id": fx.left_id}
    generator = _generator()
    response = _client(fx, generator).post(
        "/api/v1/compare", json=_body(fx, **overrides), headers=HOST
    )
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert generator.calls == []


def test_generation_unavailable_503(fx: ComparisonFixture) -> None:
    response = _client(fx, FakeGenerationProvider(digest="9" * 64)).post(
        "/api/v1/compare", json=_body(fx), headers=HOST
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "GENERATION_UNAVAILABLE"


def test_deadline_504(fx: ComparisonFixture) -> None:
    generator = _generator()
    generator.delay = 2
    response = _client(fx, generator, comparison={"deadline_seconds": 1}).post(
        "/api/v1/compare", json=_body(fx), headers=HOST
    )
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "DEADLINE_EXCEEDED"


def test_cross_site_and_no_bodies_in_logs(
    fx: ComparisonFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    client = _client(fx, _generator())
    blocked = client.post(
        "/api/v1/compare", json=_body(fx), headers={**HOST, "origin": "https://evil.example"}
    )
    assert blocked.status_code == 403
    assert (
        client.get(
            f"/api/v1/snapshots/diff?left={fx.left_id}&right={fx.right_id}",
            headers={**HOST, "sec-fetch-site": "cross-site"},
        ).status_code
        == 403
    )
    client.post(
        "/api/v1/compare", json=_body(fx, question="secretive reviewers question"), headers=HOST
    )
    err = capsys.readouterr().err
    assert "secretive" not in err and "documents this" not in err


def test_snapshot_diff_endpoint(fx: ComparisonFixture) -> None:
    generator = FakeGenerationProvider(unavailable="runtime_unreachable")
    client = _client(fx, generator)
    response = client.get(
        f"/api/v1/snapshots/diff?left={fx.left_id}&right={fx.right_id}", headers=HOST
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert {r["source_id"]: r["relation"] for r in body["sources"]} == {
        "platform": "right_only",
        "proc": "different",
    }
    assert body["release_label"] is None and generator.calls == []


@pytest.mark.parametrize(
    ("query", "status", "code"),
    [
        ("left={l}&right={l}", 422, "REQUEST_INVALID"),
        ("left=bad&right={r}", 422, "REQUEST_INVALID"),
        ("left={l}", 422, "REQUEST_INVALID"),
        ("left={l}&right={r}&extra=1", 422, "QUERY_INVALID"),
        ("left={l}&right=20990101T000000Z-00000000", 404, "SNAPSHOT_NOT_FOUND"),
    ],
)
def test_snapshot_diff_errors(fx: ComparisonFixture, query: str, status: int, code: str) -> None:
    client = _client(fx, FakeGenerationProvider())
    url = "/api/v1/snapshots/diff?" + query.format(l=fx.left_id, r=fx.right_id)
    response = client.get(url, headers=HOST)
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


def test_busy_while_chat_holds_the_slot(fx: ComparisonFixture) -> None:
    async def scenario() -> None:
        generator = FakeGenerationProvider(outputs=[answer_citing_all], delay=0.5)
        service = fx.service(generator, limits={"queued_generations": 0})
        answers = service._answers  # noqa: SLF001
        chat = asyncio.create_task(
            answers.answer(ChatRequest(question=QUESTION), request_id="chat")
        )
        await asyncio.sleep(0.2)
        from score_docs_assistant.domain.comparison import ComparisonRequest
        from score_docs_assistant.domain.errors import GenerationError

        with pytest.raises(GenerationError) as info:
            await service.compare(
                ComparisonRequest(
                    question=QUESTION, left_snapshot_id=fx.left_id, right_snapshot_id=fx.right_id
                ),
                request_id="cmp",
            )
        assert info.value.code == "CHAT_BUSY" and info.value.http_status == 429
        await chat

    asyncio.run(scenario())


@pytest.mark.parametrize("accept", ["application/json", "text/event-stream"])
def test_disconnect_releases_slot_and_pins(fx: ComparisonFixture, accept: str) -> None:
    from score_docs_assistant.storage.pins import is_pinned

    async def scenario() -> None:
        generator = FakeGenerationProvider(outputs=[answer_citing_all], delay=30)
        service = fx.service(generator)
        app = create_fastapi_app(
            config=fx.config(),
            readiness_service=None,  # type: ignore[arg-type]
            search_service=service._search,  # noqa: SLF001
            answer_service=service._answers,  # noqa: SLF001
        )
        started = time.monotonic()
        await _asgi_call(app, _body(fx), accept, disconnect_after=0.5, path="/api/v1/compare")
        await asyncio.sleep(0.1)
        assert time.monotonic() - started < 3
        assert generator.cancelled == 1 and not service._answers.queue.active  # noqa: SLF001
        assert not is_pinned(fx.data, fx.left_id) and not is_pinned(fx.data, fx.right_id)

    asyncio.run(scenario())


def test_readiness_and_capabilities_report_compare(fx: ComparisonFixture) -> None:
    client = _client(fx, FakeGenerationProvider())
    ready = client.get("/health/ready", headers=HOST).json()
    assert ready["capabilities"]["compare"] == {"available": True, "reasons": []}
    capabilities = client.get("/api/v1/capabilities", headers=HOST).json()
    assert capabilities["modes"]["compare"]["available"] is True
    assert capabilities["limits"]["comparison_deadline_seconds"] == 240
