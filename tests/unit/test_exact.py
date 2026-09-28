"""Exact and alias lookup (FR-001–FR-004, research R1). Mocked provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.search import SearchFixture, make_search_fixture


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> SearchFixture:
    return make_search_fixture(tmp_path_factory.mktemp("exact"))


def test_verbatim_match_has_full_record(fx: SearchFixture) -> None:
    response = fx.service().lookup("feat_req__alpha__short")
    assert response.status == "ok" and response.snapshot_id == fx.snapshot_id
    first = response.entities[0]
    assert (first.key, first.match) == ("alpha:feat_req__alpha__short", "exact")
    assert first.type == "feat_req" and first.title == "Short requirement"
    assert first.status == "valid"
    assert first.source_id == "alpha" and first.revision == "a" * 40
    assert first.revision_status == "pinned"
    assert first.path == "docs/reqs.rst" and first.line_start is not None
    assert first.excerpt and "scheduler handshake" in first.excerpt
    assert first.chunk_id and first.options["satisfies"].startswith("feat_req__alpha__long")


def test_git_record_before_export_copy(fx: SearchFixture) -> None:
    keys = [
        (e.key, e.revision_status) for e in fx.service().lookup("feat_req__alpha__short").entities
    ]
    assert keys == [
        ("alpha:feat_req__alpha__short", "pinned"),
        ("alpha-needs:feat_req__alpha__short", "unverified"),
    ]
    export = fx.service().lookup("feat_req__alpha__short").entities[1]
    assert export.excerpt is None and export.chunk_id is None


def test_export_only_id_is_unverified(fx: SearchFixture) -> None:
    [only] = fx.service().lookup("feat_req__export_only").entities
    assert only.revision_status == "unverified" and only.match == "exact"


def test_dotted_id_verbatim_and_alias(fx: SearchFixture) -> None:
    [exact] = fx.service().lookup("MLE.3.BP1").entities
    assert exact.match == "exact" and exact.need_id == "MLE.3.BP1"
    [aliased] = fx.service().lookup("mle-3-bp1").entities
    assert aliased.match == "alias" and aliased.need_id == "MLE.3.BP1"


def test_duplicates_across_sources_all_returned(fx: SearchFixture) -> None:
    keys = [e.key for e in fx.service().lookup("std_req__dup__one").entities]
    assert keys == ["alpha:std_req__dup__one", "beta:std_req__dup__one"]


def test_namespaced_query(fx: SearchFixture) -> None:
    keys = [e.key for e in fx.service().lookup("beta:std_req__dup__one").entities]
    assert keys == ["beta:std_req__dup__one"]
    assert fx.service().lookup("zzz:std_req__dup__one").status == "no_match"
    keys = [e.key for e in fx.service().lookup("std_req__dup__one", source_id="beta").entities]
    assert keys == ["beta:std_req__dup__one"]


@pytest.mark.parametrize("query", ["feat_req__alpha__shor", "feat_req__nope", "short"])
def test_no_fuzzy_matches(fx: SearchFixture, query: str) -> None:
    response = fx.service().lookup(query)
    assert response.status == "no_match" and response.entities == []


def test_lookup_on_explicit_snapshot(fx: SearchFixture, tmp_path: Path) -> None:
    response = fx.service().lookup("MLE.3.BP1", snapshot_id=fx.snapshot_id)
    assert response.snapshot_id == fx.snapshot_id
