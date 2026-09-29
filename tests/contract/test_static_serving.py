"""Static frontend serving (specs/006-local-web-ui/contracts/ui-contract.md §2, FR-010a)."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from score_docs_assistant.api.app import create_app
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.models import ModelProfile, ProfileModel
from score_docs_assistant.readiness import ReadinessService
from score_docs_assistant.storage.corpus_probe import FileCorpusProbe


class _FakeRuntime:
    def version(self) -> object:
        raise NotImplementedError

    def list_models(self) -> list:  # type: ignore[type-arg]
        return []


def _profile() -> ModelProfile:
    return ModelProfile(
        name="local-small",
        models=[
            ProfileModel(role="generation", tag="qwen3:4b-instruct", size_source="t"),
            ProfileModel(role="embedding", tag="nomic-embed-text", size_source="t"),
        ],
    )


def _client(tmp_path: Path, *, frontend_dist_dir: Path) -> TestClient:
    config = AppConfig(data_dir=tmp_path)
    readiness_service = ReadinessService(
        config=config,
        runtime=_FakeRuntime(),
        corpus_probe=FileCorpusProbe(tmp_path),
        profile=_profile(),
        cache_seconds=0,
    )
    app = create_app(
        config=config,
        readiness_service=readiness_service,
        frontend_dist_dir=frontend_dist_dir,
    )
    return TestClient(app, base_url="http://127.0.0.1:8080")


@pytest.fixture
def built_dist(tmp_path: Path) -> Path:
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<html><body>app shell</body></html>")
    (assets_dir / "index-abc123.js").write_text("console.log('hi');")
    return dist_dir


def test_index_served_with_csp_and_no_store(built_dist: Path, tmp_path: Path) -> None:
    client = _client(tmp_path, frontend_dist_dir=built_dist)
    response = client.get("/", headers={"host": "127.0.0.1:8080"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "default-src 'self'" in csp


def test_existing_asset_served(built_dist: Path, tmp_path: Path) -> None:
    client = _client(tmp_path, frontend_dist_dir=built_dist)
    response = client.get("/assets/index-abc123.js", headers={"host": "127.0.0.1:8080"})
    assert response.status_code == 200


def test_unknown_asset_is_404_never_index(built_dist: Path, tmp_path: Path) -> None:
    client = _client(tmp_path, frontend_dist_dir=built_dist)
    response = client.get("/assets/does-not-exist.js", headers={"host": "127.0.0.1:8080"})
    assert response.status_code == 404


def test_missing_dist_dir_returns_honest_503(tmp_path: Path) -> None:
    client = _client(tmp_path, frontend_dist_dir=tmp_path / "does-not-exist")
    response = client.get("/", headers={"host": "127.0.0.1:8080"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "FRONTEND_NOT_BUILT"


def test_api_and_health_routes_take_precedence_over_static_mount(
    built_dist: Path, tmp_path: Path
) -> None:
    client = _client(tmp_path, frontend_dist_dir=built_dist)
    response = client.get("/health/live", headers={"host": "127.0.0.1:8080"})
    assert response.status_code == 200
    assert response.json() != {"error": {"code": "FRONTEND_NOT_BUILT"}}
