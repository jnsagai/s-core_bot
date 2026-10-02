"""`refresh` end to end against a fixture upstream (F011 US1: FR-001–FR-005, FR-010, SC-002)."""

from __future__ import annotations

from pathlib import Path

from score_docs_assistant.cli.search_support import build_service
from score_docs_assistant.domain.retrieval import SearchRequest
from score_docs_assistant.refresh.models import RefreshState
from score_docs_assistant.refresh.state import read_state
from score_docs_assistant.sources.sync import SyncService
from tests.helpers.refresh import (
    FILE_GIT,
    commit,
    files_under,
    make_upstream,
    needs_body,
)
from tests.helpers.registries import make_registry


def test_first_run_activates(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    run = up.refresh()
    assert run.outcome == "activated" and run.exit_code == 0
    assert up.active() == run.candidate == run.active_after
    assert run.active_before is None and run.synced and run.lock_changed
    assert {g.id for g in run.gate} == {
        "integrity",
        "exact_ids",
        "coverage_drop",
        "semantic",
        "required_sources",
    }
    assert set(run.timings) >= {"check", "sync", "build", "gate", "activate"}


def test_upstream_change_becomes_searchable(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    first = up.refresh()
    head = commit(
        up.repo,
        {"docs/new_topic.rst": "Quasar\n======\n\nSYNTHETIC — the quasar coordinator text.\n"},
    )
    run = up.refresh()
    assert run.outcome == "activated"
    assert run.active_before == first.candidate and up.active() == run.candidate
    [change] = run.revision_changes
    assert change.source_id == "fx" and change.after == head
    response = build_service(up.config(), embeddings=False).search(
        SearchRequest(query="quasar coordinator"), force_lexical=True
    )
    assert response.snapshot_id == run.candidate
    assert any(r.path.endswith("new_topic.rst") for r in response.results)


def test_unchanged_rerun_creates_nothing(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    up.refresh()
    up.refresh()  # stores export validators seen during the first sync's check
    before = files_under(up.data)
    run = up.refresh()
    assert run.outcome == "up-to-date" and run.exit_code == 0
    assert not run.synced and run.candidate is None
    after = files_under(up.data)
    changed = {p for p in set(before) | set(after) if before.get(p) != after.get(p)}
    # Only the replaced state file and lock files' open/close may differ; no new files appear.
    assert changed <= {"refresh-state.json"}, changed
    state = read_state(up.data)
    assert isinstance(state, RefreshState) and state.last_run is not None
    assert state.last_run.outcome == "up-to-date" and state.last_success_at is not None


def test_export_change_without_git_change_triggers_build(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    up.refresh()
    up.refresh()
    assert up.export is not None
    up.export.change(needs_body(["feat_req__fx__000"]), '"e2"')
    run = up.refresh()
    assert run.synced and run.lock_changed
    assert [c.source_id for c in run.revision_changes] == ["fx-needs"]
    assert run.outcome == "activated"


def test_manual_sync_without_build_is_picked_up(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    first = up.refresh()
    commit(up.repo, {"docs/manual.rst": "Manual\n======\n\nSYNTHETIC — manual sync text.\n"})
    registry = make_registry(up.sources)
    assert up.export is not None
    SyncService(registry, up.data, git=FILE_GIT, http_client=up.export.client()).run()
    run = up.refresh()
    # Upstream now equals the lock, but the active snapshot was built from the older lock.
    assert run.outcome == "activated" and run.candidate != first.candidate


def test_export_304_and_git_unchanged_skip_sync(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    up.refresh()
    up.refresh()
    assert up.export is not None
    up.export.requests.clear()
    run = up.refresh()
    assert run.outcome == "up-to-date" and not run.synced
    [request] = up.export.requests
    assert request.headers["if-none-match"] == '"e1"'


def test_registry_change_forces_sync(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    up.refresh()
    up.refresh()
    service = up.service()
    service._registry._sha256 = "f" * 64  # simulate an edited config/sources.yaml
    run = service.run()
    assert run.synced


def test_keyword_only_active_snapshot_is_mirrored(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    first = up.refresh(lexical_only=True)
    assert first.outcome == "activated"
    commit(up.repo, {"docs/kw.rst": "Keyword\n=======\n\nSYNTHETIC — keyword text.\n"})
    up.provider.calls.clear()
    run = up.refresh()
    assert run.outcome == "activated"
    assert up.provider.calls == []  # mirrored: no embeddings for a keyword-only active snapshot
    assert [g for g in run.gate if g.id == "semantic"][0].detail == "semantic absent"
