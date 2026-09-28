"""Evidence HTTP API contract (FR-011, FR-015, FR-016, FR-018, SC-007). Mocked provider."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from score_docs_assistant.api.app import create_app
from score_docs_assistant.domain.models import ModelProfile, ProfileModel
from score_docs_assistant.readiness import ReadinessService
from score_docs_assistant.storage.corpus_probe import FileCorpusProbe
from tests.helpers.search import SearchFixture, make_search_fixture

HOST = {"host": "127.0.0.1:8080"}


class _Runtime:
    def version(self) -> object:
        raise NotImplementedError

    def list_models(self) -> list[object]:
        return []


def _client(fx: SearchFixture, **retrieval: object) -> tuple[TestClient, object]:
    config = fx.config(**retrieval)
    service = fx.service(**retrieval)
    readiness = ReadinessService(
        config=config,
        runtime=_Runtime(),  # type: ignore[arg-type]
        corpus_probe=FileCorpusProbe(fx.data),
        profile=ModelProfile(
            name="p", models=[ProfileModel(role="generation", tag="g", size_source="t")]
        ),
        cache_seconds=0,
        semantic_probe=service.active_semantic_available,
    )
    app = create_app(config=config, readiness_service=readiness, search_service=service)
    return TestClient(app, base_url="http://127.0.0.1:8080"), service


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> SearchFixture:
    return make_search_fixture(tmp_path_factory.mktemp("api"))


@pytest.fixture(scope="module")
def client(fx: SearchFixture) -> TestClient:
    return _client(fx)[0]


def _post(client: TestClient, body: object, **headers: str):  # type: ignore[no-untyped-def]
    return client.post("/api/v1/search", json=body, headers={**HOST, **headers})


def test_search_happy_path(client: TestClient, fx: SearchFixture) -> None:
    response = _post(client, {"query": "watchdog deadlines", "limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot_id"] == fx.snapshot_id and body["mode"] == "hybrid"
    assert 0 < len(body["results"]) <= 5
    assert response.headers["cache-control"] == "no-store"


def test_other_routes(client: TestClient, fx: SearchFixture) -> None:
    lookup = client.get("/api/v1/entities", params={"id": "MLE.3.BP1"}, headers=HOST).json()
    assert lookup["entities"][0]["key"] == "alpha:MLE.3.BP1"
    rel = client.get(
        "/api/v1/relationships", params={"key": "alpha:feat_req__alpha__short"}, headers=HOST
    ).json()
    assert rel["outgoing_total"] == 2
    snaps = client.get("/api/v1/snapshots", headers=HOST).json()
    assert snaps["active"] == fx.snapshot_id
    sources = client.get("/api/v1/sources", headers=HOST).json()
    assert {s["source_id"] for s in sources["sources"]} == {"alpha", "alpha-needs", "beta"}
    chunk = lookup["entities"][0]["chunk_id"]
    citation = client.get(f"/api/v1/citations/{fx.snapshot_id}/{chunk}", headers=HOST)
    assert citation.status_code == 200 and citation.json()["text"].startswith("Machine learning")


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"query": "x", "model": "gpt"}, 422, "REQUEST_INVALID"),
        ({"query": "x", "url": "http://evil"}, 422, "REQUEST_INVALID"),
        ({"query": ""}, 422, "REQUEST_INVALID"),
        ({"query": "   "}, 422, "QUERY_INVALID"),
        ({"query": "x" * 4001}, 422, "QUERY_INVALID"),
        ({"query": "x", "limit": 21}, 422, "QUERY_INVALID"),
        ({"query": "x", "sources": ["nope"]}, 422, "FILTER_INVALID"),
        ({"query": "x", "kinds": ["image"]}, 422, "REQUEST_INVALID"),
        ({"query": "x", "snapshot_id": "../../etc"}, 422, "QUERY_INVALID"),
        ({"query": "x", "snapshot_id": "20990101T000000Z-00000000"}, 404, "SNAPSHOT_NOT_FOUND"),
    ],
)
def test_search_errors(client: TestClient, body: object, status: int, code: str) -> None:
    response = _post(client, body)
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code and error["request_id"]
    assert error["retryable"] is False


def test_malformed_json_is_400(client: TestClient) -> None:
    response = client.post(
        "/api/v1/search",
        content=b"{not json",
        headers={**HOST, "content-type": "application/json"},
    )
    assert response.status_code == 400 and response.json()["error"]["code"] == "MALFORMED_REQUEST"


def test_unknown_ids_404(client: TestClient, fx: SearchFixture) -> None:
    assert (
        client.get(f"/api/v1/citations/{fx.snapshot_id}/{'0' * 64}", headers=HOST).status_code
        == 404
    )
    assert client.get(f"/api/v1/citations/{fx.snapshot_id}/nothex", headers=HOST).status_code == 404
    assert client.get(f"/api/v1/citations/..%2F..%2Fx/{'0' * 64}", headers=HOST).status_code == 404
    response = client.get("/api/v1/relationships", params={"key": "alpha:none"}, headers=HOST)
    assert response.status_code == 404 and response.json()["error"]["code"] == "ENTITY_NOT_FOUND"


def test_no_active_snapshot_409(tmp_path: Path) -> None:
    fx = make_search_fixture(tmp_path)
    from score_docs_assistant.storage.catalog import Catalog

    catalog = Catalog.open(fx.data, create=False)
    assert catalog is not None
    with catalog, catalog.transaction() as conn:
        conn.execute("DELETE FROM active_pointer")
        conn.execute("UPDATE snapshots SET state = 'validated'")
    client, _ = _client(fx)
    response = _post(client, {"query": "watchdog"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "NO_ACTIVE_SNAPSHOT"


def test_busy_429(fx: SearchFixture) -> None:
    client, service = _client(fx, max_concurrent_searches=1)
    entered, release = threading.Event(), threading.Event()

    def block(_snapshot_id: str) -> None:
        entered.set()
        release.wait(10)

    service.after_pin = block  # type: ignore[attr-defined]
    worker = threading.Thread(target=lambda: _post(client, {"query": "watchdog"}))
    worker.start()
    assert entered.wait(10)
    response = _post(client, {"query": "watchdog"})
    release.set()
    worker.join(10)
    assert response.status_code == 429
    assert response.json()["error"] == {
        "code": "SEARCH_BUSY",
        "message": response.json()["error"]["message"],
        "request_id": response.json()["error"]["request_id"],
        "retryable": True,
    }


def test_cross_origin_rejected(client: TestClient) -> None:
    response = _post(client, {"query": "x"}, origin="https://evil.example")
    assert response.status_code == 403
    response = _post(client, {"query": "x"}, **{"sec-fetch-site": "cross-site"})
    assert response.status_code == 403


def test_access_log_has_no_query_text(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    _post(client, {"query": "secretive watchdog phrase"})
    assert "secretive" not in capsys.readouterr().err


def test_no_probability_like_fields_in_schemas() -> None:
    import re

    from score_docs_assistant.domain import retrieval

    names: set[str] = set()
    for obj in vars(retrieval).values():
        fields = getattr(obj, "model_fields", None)
        if isinstance(fields, dict):
            names |= set(fields)
    assert not {n for n in names if re.search("score|confidence|probab", n)}
    description = retrieval.EvidenceResult.model_fields["ranking_value"].description or ""
    assert "not a probability" in description


def test_readiness_reports_search_available(client: TestClient) -> None:
    payload = client.get("/health/ready", headers=HOST).json()
    assert payload["capabilities"]["search"] == {"available": True, "reasons": []}
    assert "not_implemented" in payload["capabilities"]["chat"]["reasons"]
