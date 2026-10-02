"""A long-lived `SearchService` (as in `serve`) follows refresh activations (F011 FR-012)."""

from __future__ import annotations

from pathlib import Path

from score_docs_assistant.domain.retrieval import SearchRequest
from score_docs_assistant.retrieval.service import SearchService
from tests.helpers.refresh import commit, make_upstream


def test_next_request_uses_new_snapshot_and_pinned_request_keeps_old(tmp_path: Path) -> None:
    up = make_upstream(tmp_path)
    first = up.refresh()
    service = SearchService(config=up.config(), provider=None)  # one instance, never restarted
    before = service.search(SearchRequest(query="watchdog"), force_lexical=True)
    assert before.snapshot_id == first.candidate

    with service.pinned(None) as in_flight:  # a request already running during activation
        commit(up.repo, {"docs/pulsar.rst": "Pulsar\n======\n\nSYNTHETIC — pulsar text.\n"})
        second = up.refresh()
        assert second.outcome == "activated"
        assert in_flight.snapshot_id == first.candidate
        assert (in_flight.directory / "manifest.json").is_file()

    after = service.search(SearchRequest(query="pulsar"), force_lexical=True)
    assert after.snapshot_id == second.candidate
    assert all(r.snapshot_id == second.candidate for r in after.results)
