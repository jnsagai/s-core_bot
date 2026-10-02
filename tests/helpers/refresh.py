"""Fixture upstream (file:// git + mocked export) and a `RefreshService` for F011 tests.

No network: git is reached over `file://`, exports through an httpx `MockTransport`, embeddings
through the fake provider. Every text carries a `SYNTHETIC — not S-CORE guidance` marker.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from score_docs_assistant.cli.refresh import build_gate
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.refresh.models import RefreshRun
from score_docs_assistant.refresh.service import RefreshService
from score_docs_assistant.sources.git_client import GitClient
from score_docs_assistant.storage.catalog import Catalog
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.git_repos import FixtureRepo, default_files, git, make_plain_repo
from tests.helpers.registries import export_source, git_source, make_registry
from tests.helpers.snapshot_env import PROFILES, write_model_lock

FILE_GIT = GitClient(allowed_protocols=frozenset({"file"}))
EXPORT_URL = "https://eclipse-score.github.io/fixture/needs.json"


def reqs_rst(count: int, prefix: str = "feat_req__fx") -> str:
    body = "".join(
        f".. feat_req:: Requirement {i}\n   :id: {prefix}__{i:03d}\n   :status: valid\n\n"
        f"   Requirement {i} describes how the synthetic scheduler handles slot {i}.\n\n"
        for i in range(count)
    )
    return ".. SYNTHETIC — not S-CORE guidance\n\nRequirements\n============\n\n" + body


def upstream_files(extra: dict[str, str] | None = None) -> dict[str, str | bytes]:
    files: dict[str, str | bytes] = {**default_files(), "docs/reqs.rst": reqs_rst(12)}
    for index in range(6):
        files[f"docs/topic_{index}.rst"] = (
            f"Topic {index}\n========\n\nSYNTHETIC — topic {index} explains the watchdog.\n"
        )
    files.update(extra or {})
    return files


def commit(repo: FixtureRepo, files: dict[str, str], remove: list[str] | None = None) -> str:
    for rel, text in files.items():
        target = repo.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    for rel in remove or []:
        (repo.path / rel).unlink()
    git(repo.path, "add", "-A")
    git(repo.path, "commit", "-q", "-m", "update")
    return git(repo.path, "rev-parse", "HEAD")


@dataclass
class FakeExport:
    """A needs export served through MockTransport, honouring If-None-Match."""

    body: bytes = b'{"current_version": "1", "versions": {"1": {"needs": {}}}}'
    etag: str | None = '"e1"'
    requests: list[httpx.Request] = field(default_factory=list)
    fail: bool = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            return httpx.Response(503)
        headers = {"etag": self.etag} if self.etag else {}
        if self.etag and request.headers.get("if-none-match") == self.etag:
            return httpx.Response(304, headers=headers)
        return httpx.Response(200, headers=headers, content=self.body)

    def change(self, body: bytes, etag: str) -> None:
        self.body, self.etag = body, etag

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


@dataclass
class Upstream:
    root: Path
    repo: FixtureRepo
    export: FakeExport | None
    data: Path
    provider: FakeEmbeddingProvider

    @property
    def sources(self) -> list[dict[str, Any]]:
        sources = [git_source("fx", self.repo.url)]
        if self.export is not None:
            sources.append(
                export_source("fx-needs", EXPORT_URL, associated_source="fx", docs_root="docs")
            )
        return sources

    def config(self, **refresh: Any) -> AppConfig:
        return AppConfig(data_dir=self.data, refresh=refresh)  # type: ignore[arg-type]

    def service(
        self, *, lexical_only: bool = False, provider_error: bool = False, **refresh: Any
    ) -> RefreshService:
        def provider() -> FakeEmbeddingProvider:
            if provider_error:
                raise SnapshotError("EMBEDDING_UNAVAILABLE", "fake runtime unreachable")
            return self.provider

        return RefreshService(
            self.config(**refresh),
            make_registry(self.sources),
            profiles_dir=PROFILES,
            git=FILE_GIT,
            http_client=self.export.client() if self.export else None,
            provider_factory=provider,
            gate_factory=build_gate,
            lexical_only=lexical_only,
        )

    def refresh(self, **kwargs: Any) -> RefreshRun:
        return self.service(**kwargs).run()

    def active(self) -> str | None:
        catalog = Catalog.open(self.data, create=False)
        if catalog is None:
            return None
        with catalog:
            return catalog.active_id()

    def state_of(self, snapshot_id: str) -> str:
        catalog = Catalog.open(self.data, create=False)
        assert catalog is not None
        with catalog:
            row = catalog.get(snapshot_id)
        assert row is not None
        return row.state


def make_upstream(tmp_path: Path, *, export: bool = True) -> Upstream:
    repo = make_plain_repo(tmp_path / "upstream", upstream_files())
    data = tmp_path / "data"
    data.mkdir()
    provider = FakeEmbeddingProvider()
    write_model_lock(data, provider.digest)
    return Upstream(
        root=tmp_path,
        repo=repo,
        export=FakeExport() if export else None,
        data=data,
        provider=provider,
    )


def needs_body(ids: list[str]) -> bytes:
    needs = {
        i: {"id": i, "type": "feat_req", "title": i, "status": "valid", "docname": "reqs"}
        for i in ids
    }
    return json.dumps({"current_version": "1", "versions": {"1": {"needs": needs}}}).encode()


def files_under(root: Path) -> dict[str, int]:
    """Relative path → mtime_ns for every file (to prove a run created or changed nothing)."""
    return {
        str(p.relative_to(root)): p.stat().st_mtime_ns
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }
