"""`/health/live`, `/health/ready`, `/api/v1/capabilities`, and the route inventory
(contracts/http-api.md, FR-009, FR-020, FR-021)."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from score_docs_assistant.api.app import create_app
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.models import InstalledModel, ModelProfile, ProfileModel
from score_docs_assistant.readiness import ReadinessService
from score_docs_assistant.storage.corpus_probe import FileCorpusProbe


class _FakeRuntime:
    def __init__(self, models: list[InstalledModel]) -> None:
        self._models = models

    def version(self) -> object:
        raise NotImplementedError

    def list_models(self) -> list[InstalledModel]:
        return self._models


def _profile() -> ModelProfile:
    return ModelProfile(
        name="local-small",
        models=[
            ProfileModel(role="generation", tag="qwen3:4b-instruct", size_source="t"),
            ProfileModel(role="embedding", tag="nomic-embed-text", size_source="t"),
        ],
    )


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    config = AppConfig(data_dir=tmp_path)
    readiness_service = ReadinessService(
        config=config,
        runtime=_FakeRuntime([]),
        corpus_probe=FileCorpusProbe(tmp_path),
        profile=_profile(),
        cache_seconds=0,
    )
    app = create_app(config=config, readiness_service=readiness_service)
    return TestClient(app, base_url="http://127.0.0.1:8080")


def _common_assertions(response) -> None:  # type: ignore[no-untyped-def]
    assert response.headers["cache-control"] == "no-store"
    assert "x-request-id" in response.headers
    assert "server" not in response.headers


def test_liveness_body_exact(client: TestClient) -> None:
    response = client.get("/health/live", headers={"host": "127.0.0.1:8080"})
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    _common_assertions(response)


def test_readiness_503_with_reasons_and_no_leaks(client: TestClient) -> None:
    response = client.get("/health/ready", headers={"host": "127.0.0.1:8080"})
    assert response.status_code == 503
    payload = response.json()
    assert payload["ready"] is False
    assert "corpus_missing" in payload["capabilities"]["search"]["reasons"]
    dumped = str(payload)
    assert "127.0.0.1" not in dumped
    assert "qwen3" not in dumped
    assert "0.1.0" not in dumped
    _common_assertions(response)


def test_capabilities_200_shape(client: TestClient) -> None:
    response = client.get("/api/v1/capabilities", headers={"host": "127.0.0.1:8080"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["profile"] == "local"
    assert payload["runs_locally"] is True
    assert payload["models"] == {"generation": "qwen3:4b-instruct", "embedding": "nomic-embed-text"}
    assert set(payload["modes"]) == {"search", "chat", "compare"}
    _common_assertions(response)


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_routes_disabled(client: TestClient, path: str) -> None:
    response = client.get(path, headers={"host": "127.0.0.1:8080"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_unknown_route_is_404(client: TestClient) -> None:
    response = client.get("/nope", headers={"host": "127.0.0.1:8080"})
    assert response.status_code == 404


def test_wrong_method_is_405(client: TestClient) -> None:
    response = client.post("/health/live", headers={"host": "127.0.0.1:8080"})
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_compatible_corpus_keeps_search_and_chat_not_implemented(tmp_path: Path) -> None:
    """FR-021: a compatible corpus must not make search (F004) or chat (F005) look available."""
    from tests.helpers.lifecycle import activate, snapshots
    from tests.helpers.snapshot_env import make_env

    env = make_env(tmp_path)
    [a] = snapshots(env, 1)
    activate(env, a)
    config = AppConfig(data_dir=env.data)
    service = ReadinessService(
        config=config,
        runtime=_FakeRuntime(
            [InstalledModel(tag="qwen3:4b-instruct", digest="sha256:x", size_bytes=1)]
        ),
        corpus_probe=FileCorpusProbe(env.data),
        profile=_profile(),
        cache_seconds=0,
    )
    app = create_app(config=config, readiness_service=service)
    response = TestClient(app, base_url="http://127.0.0.1:8080").get(
        "/health/ready", headers={"host": "127.0.0.1:8080"}
    )
    payload = response.json()
    assert payload["capabilities"]["search"]["reasons"] == ["not_implemented"]
    assert "not_implemented" in payload["capabilities"]["chat"]["reasons"]
    assert "corpus_missing" not in str(payload)
    assert payload["ready"] is False
