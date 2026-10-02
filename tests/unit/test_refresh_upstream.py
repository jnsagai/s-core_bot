"""UpstreamChecker decisions per source (F011 FR-002, research R1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from score_docs_assistant.domain.ingestion import LockedSource, SourceLock
from score_docs_assistant.refresh.models import ExportValidator
from score_docs_assistant.refresh.upstream import UpstreamChecker, UpstreamCheckError
from score_docs_assistant.sources.git_client import GitError
from tests.helpers.registries import export_source, git_source, make_registry

GIT_URL = "https://github.com/example/docs.git"
EXPORT_URL = "https://eclipse-score.github.io/docs/needs.json"
NOW = datetime(2026, 10, 2, tzinfo=UTC)


class FakeGit:
    def __init__(self, head: str | Exception) -> None:
        self.head = head
        self.calls: list[tuple[str, str]] = []

    def resolve_ref(self, url: str, ref: str) -> str:
        self.calls.append((url, ref))
        if isinstance(self.head, Exception):
            raise self.head
        return self.head


def _lock(**revisions: str | None) -> SourceLock:
    sources = []
    for source_id, revision in revisions.items():
        git = not source_id.endswith("needs")
        sources.append(
            LockedSource(
                source_id=source_id,
                kind="git" if git else "needs-export",
                status="ok" if revision else "failed",
                failure=None if revision else "x",
                required=git,
                repository=GIT_URL if git else None,
                url=None if git else EXPORT_URL,
                ref="main" if git else None,
                authority="fixture",
                repository_license="Apache-2.0",
                revision=revision,
                revision_status="pinned" if git else "unverified",
                fetched_at=NOW,
            )
        )
    return SourceLock(
        schema_version=1,
        generated_at=NOW,
        registry_sha256="",
        redistribution_allowed_licenses=["Apache-2.0"],
        sources=sources,
    )


def _checker(git: FakeGit, handler: Any = None, **kwargs: Any) -> UpstreamChecker:
    sources = [git_source("docs", GIT_URL), export_source("docs-needs", EXPORT_URL)]
    client = httpx.Client(transport=httpx.MockTransport(handler)) if handler else None
    return UpstreamChecker(make_registry(sources), git=git, http_client=client, **kwargs)  # type: ignore[arg-type]


def _status(result: Any) -> dict[str, str]:
    return {c.source_id: c.status for c in result.checks}


STORED = {"docs-needs": ExportValidator(url=EXPORT_URL, etag='"e1"')}


def test_all_unchanged() -> None:
    result = _checker(
        FakeGit("a" * 40), lambda r: httpx.Response(304, headers={"etag": '"e1"'})
    ).check(_lock(docs="a" * 40, **{"docs-needs": "h1"}), STORED)
    assert _status(result) == {"docs": "unchanged", "docs-needs": "unchanged"}
    assert result.all_unchanged


def test_git_moved() -> None:
    result = _checker(FakeGit("b" * 40), lambda r: httpx.Response(304)).check(
        _lock(docs="a" * 40, **{"docs-needs": "h1"}), STORED
    )
    check = result.checks[0]
    assert (check.status, check.locked, check.upstream) == ("changed", "a" * 40, "b" * 40)
    assert not result.all_unchanged


def test_export_modified_records_new_validator() -> None:
    result = _checker(
        FakeGit("a" * 40), lambda r: httpx.Response(200, headers={"etag": '"e2"'})
    ).check(_lock(docs="a" * 40, **{"docs-needs": "h1"}), STORED)
    assert _status(result)["docs-needs"] == "changed"
    assert result.validators["docs-needs"].etag == '"e2"'


def test_no_stored_validator_is_unknown() -> None:
    result = _checker(
        FakeGit("a" * 40), lambda r: httpx.Response(200, headers={"etag": '"e1"'})
    ).check(_lock(docs="a" * 40, **{"docs-needs": "h1"}), {})
    assert _status(result)["docs-needs"] == "unknown"
    assert result.validators["docs-needs"].etag == '"e1"'


def test_validator_for_other_url_is_ignored() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(304)

    stored = {
        "docs-needs": ExportValidator(url="https://eclipse-score.github.io/old.json", etag='"e1"')
    }
    result = _checker(FakeGit("a" * 40), handler).check(
        _lock(docs="a" * 40, **{"docs-needs": "h1"}), stored
    )
    assert "if-none-match" not in seen[0].headers
    assert _status(result)["docs-needs"] == "unknown"


def test_failed_export_in_lock_counts_as_changed() -> None:
    result = _checker(FakeGit("a" * 40), lambda r: httpx.Response(304)).check(
        _lock(docs="a" * 40, **{"docs-needs": None}), STORED
    )
    assert _status(result)["docs-needs"] == "changed"


def test_exports_check_disabled() -> None:
    result = _checker(FakeGit("a" * 40), check_exports=False).check(
        _lock(docs="a" * 40, **{"docs-needs": "h1"}), STORED
    )
    assert _status(result)["docs-needs"] == "unknown"


def test_no_lock_means_registry_changed() -> None:
    result = _checker(FakeGit("a" * 40), lambda r: httpx.Response(304)).check(None, STORED)
    assert result.registry_changed and not result.all_unchanged


def test_required_git_error_raises() -> None:
    with pytest.raises(UpstreamCheckError):
        _checker(FakeGit(GitError("GIT_LS_REMOTE_FAILED", "offline"))).check(
            _lock(docs="a" * 40), {}
        )


def test_optional_export_error_is_unknown() -> None:
    result = _checker(FakeGit("a" * 40), lambda r: httpx.Response(503)).check(
        _lock(docs="a" * 40, **{"docs-needs": "h1"}), STORED
    )
    check = result.checks[1]
    assert check.status == "unknown" and "HTTP_503" in check.detail
