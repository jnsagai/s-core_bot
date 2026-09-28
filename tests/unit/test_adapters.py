"""`SourceAdapter` implementations are what `SyncService` uses (plan: Structure Decision;
constitution VI — responsibilities separated by explicit interfaces)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

import score_docs_assistant.sources.adapters as adapters
from score_docs_assistant.domain.ingestion import LockedSource
from score_docs_assistant.sources.git_client import GitClient
from score_docs_assistant.sources.sync import SyncService
from tests.helpers.git_repos import make_plain_repo
from tests.helpers.registries import export_source, git_source, make_registry


def test_sync_acquires_through_adapters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    real_git, real_export = adapters.GitSourceAdapter.acquire, adapters.ExportSourceAdapter.acquire

    def spy_git(self: adapters.GitSourceAdapter, staging_root: Path) -> LockedSource:
        calls.append(f"git:{self.source.source_id}")
        return real_git(self, staging_root)

    def spy_export(self: adapters.ExportSourceAdapter, staging_root: Path) -> LockedSource:
        calls.append(f"export:{self.source.source_id}")
        return real_export(self, staging_root)

    monkeypatch.setattr(adapters.GitSourceAdapter, "acquire", spy_git)
    monkeypatch.setattr(adapters.ExportSourceAdapter, "acquire", spy_export)
    repo = make_plain_repo(tmp_path / "repo")
    body = b'{"current_version": "0.1", "versions": {"0.1": {"needs": {}}}}'
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body)))
    registry = make_registry(
        [
            git_source("docs", repo.url),
            export_source("exp", "https://eclipse-score.github.io/score/main/needs.json"),
        ]
    )
    service = SyncService(
        registry,
        tmp_path / "data",
        git=GitClient(allowed_protocols=frozenset({"file"})),
        http_client=http,
    )
    assert service.run().exit_code == 0
    assert calls == ["git:docs", "export:exp"]
    assert (
        adapters.GitSourceAdapter.kind == "git"
        and adapters.ExportSourceAdapter.kind == "needs-export"
    )
