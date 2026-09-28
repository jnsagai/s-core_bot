"""Snapshot isolation for search (FR-013, SC-002, AT-03, AT-12). Mocked provider."""

from __future__ import annotations

from pathlib import Path

from score_docs_assistant.domain.retrieval import SearchRequest
from tests.helpers.build import build
from tests.helpers.lifecycle import activate
from tests.helpers.search import make_search_fixture, search_sources
from tests.helpers.snapshot_env import SourceSpec


def _other_sources() -> list[SourceSpec]:
    sources = search_sources()
    sources[0] = SourceSpec(
        "alpha",
        {
            "docs/other.rst": (
                ".. SPDX-License-Identifier: Apache-2.0\n\n.. SYNTHETIC — not S-CORE guidance\n\n"
                "Other\n=====\n\nThe watchdog in snapshot B mentions a zebra crossing.\n"
            )
        },
        revision="c" * 40,
    )
    return sources


def test_other_snapshot_content_never_returned(tmp_path: Path) -> None:
    fx = make_search_fixture(tmp_path)
    fx.env.write(_other_sources())
    b = build(fx.env, fx.provider).snapshot_id
    response = fx.service().search(
        SearchRequest(query="watchdog zebra", snapshot_id=fx.snapshot_id)
    )
    assert response.snapshot_id == fx.snapshot_id
    assert all(
        "zebra" not in r.excerpt and r.snapshot_id == fx.snapshot_id for r in response.results
    )
    in_b = fx.service().search(SearchRequest(query="zebra", snapshot_id=b))
    assert in_b.results and all(r.snapshot_id == b for r in in_b.results)
    assert fx.service().lookup("MLE.3.BP1", snapshot_id=b).status == "no_match"


def test_activation_during_request_keeps_original_snapshot(tmp_path: Path) -> None:
    fx = make_search_fixture(tmp_path)
    fx.env.write(_other_sources())
    b = build(fx.env, fx.provider).snapshot_id
    service = fx.service()
    service.after_pin = lambda _sid: activate(fx.env, b, runtime=fx.provider)
    response = service.search(SearchRequest(query="watchdog zebra"))  # resolves A, then B activated
    assert response.snapshot_id == fx.snapshot_id
    assert all("zebra" not in r.excerpt for r in response.results)
    service.after_pin = None
    assert service.search(SearchRequest(query="zebra")).snapshot_id == b
