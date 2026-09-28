"""Exports through sync + inspect (FR-018–FR-020, SC-006)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from score_docs_assistant.sources.lock import read_lock
from tests.helpers.git_repos import make_plain_repo
from tests.helpers.pipeline import normalize, sync
from tests.helpers.registries import export_source, git_source

URL = "https://eclipse-score.github.io/score/main/needs.json"


def _export_bytes() -> bytes:
    needs = {
        "feat_req__a": {
            "id": "feat_req__a",
            "type": "feat_req",
            "title": "A",
            "docname": "reqs",
            "tags": ["t1"],
            "satisfies": ["feat_req__b"],
        },
        "feat_req__b": {"id": "feat_req__b", "type": "feat_req", "title": "B", "docname": "other"},
        "feat_req__only_export": {
            "id": "feat_req__only_export",
            "type": "feat_req",
            "title": "E",
            "docname": "reqs",
            "satisfies": ["feat_req__c"],
        },
    }
    return json.dumps({"current_version": "0.1", "versions": {"0.1": {"needs": needs}}}).encode()


def _http(body: bytes | None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body) if body is not None else httpx.Response(503)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _repo(tmp_path: Path) -> str:
    return make_plain_repo(
        tmp_path / "repo",
        {
            "docs/reqs.rst": (
                ".. feat_req:: A\n   :id: feat_req__a\n\n"
                ".. feat_req:: B\n   :id: feat_req__b\n\n"
                ".. feat_req:: C\n   :id: feat_req__c\n"
            ),
            "LICENSE": "x\n",
        },
    ).url


def test_export_synced_unverified_and_consistency(tmp_path: Path) -> None:
    data = tmp_path / "data"
    sources = [
        git_source("git-src", _repo(tmp_path)),
        export_source("exp", URL, associated_source="git-src", docs_root="docs"),
    ]
    assert sync(data, sources, http=_http(_export_bytes())) == 0
    entry = next(s for s in read_lock(data / "source-lock.json").sources if s.source_id == "exp")
    assert entry.revision_status == "unverified" and entry.revision and len(entry.revision) == 64
    outcome = normalize(data)
    exported = [e for e in outcome.entities if e.source_id == "exp"]
    assert {e.key for e in exported} == {
        "exp:feat_req__a",
        "exp:feat_req__b",
        "exp:feat_req__only_export",
    }
    assert all(e.revision_status == "unverified" for e in exported)
    cov = next(c for c in outcome.report.sources if c.source_id == "exp")
    stat = cov.export_consistency
    assert stat is not None
    assert (stat.matched, stat.id_only_matched, stat.missing_in_source, stat.missing_in_export) == (
        1,
        1,
        1,
        1,
    )
    links = {r.target_id: r for e in exported for r in e.links}
    # Export links resolve only inside the export: feat_req__b exists there, feat_req__c does not
    # (it exists only in the git source, a different namespace).
    assert links["feat_req__b"].resolved_keys == ["exp:feat_req__b"]
    assert links["feat_req__c"].resolution == "unresolved"


def test_optional_export_failure_is_a_coverage_limitation(tmp_path: Path) -> None:
    data = tmp_path / "data"
    sources = [git_source("git-src", _repo(tmp_path)), export_source("exp", URL)]
    assert sync(data, sources, http=_http(None)) == 0
    outcome = normalize(data)
    assert outcome.exit_code == 0
    cov = next(c for c in outcome.report.sources if c.source_id == "exp")
    assert cov.status == "failed" and "HTTP_503" in (cov.failure or "")
