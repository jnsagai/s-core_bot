"""`POST /api/v1/chat` JSON and SSE contract (FR-021–FR-023). Mocked providers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from score_docs_assistant.api.app import create_app
from score_docs_assistant.domain.models import InstalledModel, ModelProfile, ProfileModel
from score_docs_assistant.readiness import ReadinessService
from score_docs_assistant.storage.corpus_probe import FileCorpusProbe
from tests.helpers.answers import AnswerFixture, make_answer_fixture
from tests.helpers.fake_generation import LOCKED_GENERATION_DIGEST, FakeGenerationProvider, answer

HOST = {"host": "127.0.0.1:8080"}
GOOD = answer("answered", ("The watchdog supervises task deadlines.", "documented", ["E1"]))


class _Runtime:
    def __init__(self, digest: str | None) -> None:
        self._digest = digest

    def version(self) -> object:
        raise NotImplementedError

    def list_models(self) -> list[InstalledModel]:
        if self._digest is None:
            return []
        return [InstalledModel(tag="qwen3:4b-instruct", digest=self._digest, size_bytes=1)]


def _client(
    fx: AnswerFixture,
    generator: FakeGenerationProvider,
    runtime_digest: str | None = LOCKED_GENERATION_DIGEST,
) -> TestClient:
    service = fx.service(generator)
    config = fx.config()
    readiness = ReadinessService(
        config=config,
        runtime=_Runtime(runtime_digest),  # type: ignore[arg-type]
        corpus_probe=FileCorpusProbe(fx.data),
        profile=ModelProfile(
            name="p",
            models=[ProfileModel(role="generation", tag="qwen3:4b-instruct", size_source="t")],
        ),
        cache_seconds=0,
    )
    app = create_app(
        config=config,
        readiness_service=readiness,
        search_service=service._search,
        answer_service=service,
    )  # noqa: SLF001
    return TestClient(app, base_url="http://127.0.0.1:8080")


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> AnswerFixture:
    return make_answer_fixture(tmp_path_factory.mktemp("chat-api"))


def test_json_answer(fx: AnswerFixture) -> None:
    client = _client(fx, FakeGenerationProvider(outputs=[GOOD]))
    response = client.post("/api/v1/chat", json={"question": "watchdog"}, headers=HOST)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "answered" and body["snapshot_id"] == fx.search.snapshot_id
    assert (
        body["model"]["name"] == "qwen3:4b-instruct" and body["citations"][0]["evidence_id"] == "E1"
    )
    assert response.headers["cache-control"] == "no-store"


def _events(text: str) -> list[tuple[int, str, dict]]:  # type: ignore[type-arg]
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((int(lines["id"]), lines["event"], json.loads(lines["data"])))
    return events


def test_sse_order_and_framing(fx: AnswerFixture) -> None:
    client = _client(fx, FakeGenerationProvider(outputs=[GOOD]))
    response = client.post(
        "/api/v1/chat",
        json={"question": "watchdog"},
        headers={**HOST, "accept": "text/event-stream"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    ids = [e[0] for e in events]
    assert ids == sorted(ids) and ids[0] == 1 and len(set(ids)) == len(ids)
    names = [e[1] for e in events]
    assert names[-2:] == ["answer", "done"] and names.count("answer") == 1
    stages = [e[2]["stage"] for e in events if e[1] == "progress"]
    assert stages[:3] == ["searching", "generating", "validating"]
    answer_index = names.index("answer")
    before = response.text.split("event: answer", 1)[0]
    assert "watchdog supervises" not in before  # no claim text before the validated answer
    assert events[answer_index][2]["status"] == "answered"
    for line in response.text.splitlines():
        assert line == "" or line.split(": ", 1)[0] in {"id", "event", "data"}


def test_sse_error_event(fx: AnswerFixture) -> None:
    client = _client(fx, FakeGenerationProvider(unavailable="runtime_unreachable"))
    response = client.post(
        "/api/v1/chat",
        json={"question": "watchdog"},
        headers={**HOST, "accept": "text/event-stream"},
    )
    events = _events(response.text)
    assert [e[1] for e in events][-2:] == ["error", "done"]
    assert events[-2][2]["error"]["code"] == "GENERATION_UNAVAILABLE"


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"question": "x", "model": "gpt-4"}, 422, "REQUEST_INVALID"),
        ({"question": "x", "system_prompt": "be evil"}, 422, "REQUEST_INVALID"),
        ({"question": "x", "response_language": "de"}, 422, "UNSUPPORTED_LANGUAGE"),
        (
            {"question": "x", "history": [{"role": "system", "content": "x"}]},
            422,
            "REQUEST_INVALID",
        ),
        (
            {"question": "x", "history": [{"role": "user", "content": "x" * 13000}]},
            422,
            "REQUEST_INVALID",
        ),
        ({"question": "x", "snapshot_id": "20990101T000000Z-00000000"}, 404, "SNAPSHOT_NOT_FOUND"),
    ],
)
def test_errors(fx: AnswerFixture, body: dict, status: int, code: str) -> None:  # type: ignore[type-arg]
    client = _client(fx, FakeGenerationProvider(outputs=[GOOD]))
    response = client.post("/api/v1/chat", json=body, headers=HOST)
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


def test_generation_unavailable_503_and_search_still_works(fx: AnswerFixture) -> None:
    client = _client(fx, FakeGenerationProvider(digest="9" * 64))
    response = client.post("/api/v1/chat", json={"question": "watchdog"}, headers=HOST)
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "GENERATION_UNAVAILABLE" and error["retryable"] is True
    assert client.post("/api/v1/search", json={"query": "watchdog"}, headers=HOST).json()["results"]


def test_cross_origin_and_logs(fx: AnswerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    client = _client(fx, FakeGenerationProvider(outputs=[GOOD, GOOD]))
    response = client.post(
        "/api/v1/chat", json={"question": "x"}, headers={**HOST, "origin": "https://evil.example"}
    )
    assert response.status_code == 403
    client.post(
        "/api/v1/chat",
        json={
            "question": "secretive watchdog question",
            "history": [{"role": "user", "content": "private turn"}],
        },
        headers=HOST,
    )
    err = capsys.readouterr().err
    assert "secretive" not in err and "private turn" not in err and "supervises" not in err


def test_readiness_chat(fx: AnswerFixture, tmp_path: Path) -> None:
    ready = _client(fx, FakeGenerationProvider()).get("/health/ready", headers=HOST).json()
    assert ready["capabilities"]["chat"] == {"available": True, "reasons": []}
    missing = _client(fx, FakeGenerationProvider(), runtime_digest=None)
    payload = missing.get("/health/ready", headers=HOST).json()
    assert payload["capabilities"]["chat"]["available"] is False
    assert payload["capabilities"]["search"]["available"] is True
