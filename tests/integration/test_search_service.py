"""SearchService snapshot binding and behaviour (FR-013 and US1/US2). Mocked provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from score_docs_assistant.domain.errors import SearchError
from score_docs_assistant.storage.catalog import Catalog
from tests.helpers.build import build
from tests.helpers.search import SearchFixture, make_search_fixture, search_sources
from tests.helpers.snapshot_env import make_env


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> SearchFixture:
    return make_search_fixture(tmp_path_factory.mktemp("service"))


def _set_state(fx: SearchFixture, snapshot_id: str, state: str) -> None:
    catalog = Catalog.open(fx.data, create=False)
    assert catalog is not None
    with catalog, catalog.transaction() as conn:
        conn.execute("UPDATE snapshots SET state = ? WHERE snapshot_id = ?", (state, snapshot_id))


def test_lookup_binds_active_snapshot(fx: SearchFixture) -> None:
    assert fx.service().lookup("MLE.3.BP1").snapshot_id == fx.snapshot_id


def test_lookup_no_active_snapshot(tmp_path: Path) -> None:
    env = make_env(tmp_path, search_sources())
    build(env)
    from score_docs_assistant.config.schema import AppConfig
    from score_docs_assistant.retrieval.service import SearchService

    service = SearchService(config=AppConfig(data_dir=env.data), provider=None)
    with pytest.raises(SearchError) as exc_info:
        service.lookup("MLE.3.BP1")
    assert exc_info.value.code == "NO_ACTIVE_SNAPSHOT"


@pytest.mark.parametrize("state", ["failed", "deleted", "building"])
def test_lookup_unqueryable_states(tmp_path: Path, state: str) -> None:
    local = make_search_fixture(tmp_path)
    extra = build(local.env, local.provider).snapshot_id
    _set_state(local, extra, state)
    with pytest.raises(SearchError) as exc_info:
        local.service().lookup("MLE.3.BP1", snapshot_id=extra)
    assert exc_info.value.code == "SNAPSHOT_NOT_FOUND"


def test_lookup_validated_and_retired_are_queryable(tmp_path: Path) -> None:
    local = make_search_fixture(tmp_path)
    validated = build(local.env, local.provider).snapshot_id
    assert local.service().lookup("MLE.3.BP1", snapshot_id=validated).status == "ok"
    _set_state(local, validated, "retired")
    assert local.service().lookup("MLE.3.BP1", snapshot_id=validated).status == "ok"


def test_lookup_input_validation(fx: SearchFixture) -> None:
    with pytest.raises(SearchError) as exc_info:
        fx.service().lookup("   ")
    assert exc_info.value.code == "QUERY_INVALID"
    with pytest.raises(SearchError) as exc_info:
        fx.service().lookup("x" * 300)
    assert exc_info.value.code == "QUERY_INVALID"
    with pytest.raises(SearchError) as exc_info:
        fx.service().lookup("MLE.3.BP1", source_id="nope")
    assert exc_info.value.code == "FILTER_INVALID"
    with pytest.raises(SearchError) as exc_info:
        fx.service().lookup("MLE.3.BP1", snapshot_id="../../etc")
    assert exc_info.value.code == "SNAPSHOT_NOT_FOUND"


# --- search (FR-006–FR-015) -------------------------------------------------------------------

from score_docs_assistant.domain.retrieval import SearchRequest  # noqa: E402
from tests.helpers.fake_embedding import FakeEmbeddingProvider  # noqa: E402


def _search(fx: SearchFixture, query: str, provider=None, **kw):  # type: ignore[no-untyped-def]
    force = kw.pop("force_lexical", False)
    service = fx.service(provider) if provider is not None else fx.service()
    return service.search(SearchRequest(query=query, **kw), force_lexical=force)


def test_search_hybrid_default(fx: SearchFixture) -> None:
    response = _search(fx, "watchdog deadlines")
    assert response.mode == "hybrid" and response.degraded is None
    assert response.semantic_status == "enabled"
    assert response.snapshot_id == fx.snapshot_id
    assert 0 < len(response.results) <= 8
    assert any("semantic" in r.matched_by for r in response.results)
    assert [r.rank for r in response.results] == list(range(1, len(response.results) + 1))


def test_search_id_in_question_ranks_first(fx: SearchFixture) -> None:
    response = _search(fx, "What does feat_req__alpha__long say about persistence?")
    first = response.results[0]
    assert first.entity_keys == ["alpha:feat_req__alpha__long"]
    assert first.matched_by[0] == "exact" and first.ranking_value is None
    assert [m.key for m in response.exact_matches] == [
        "alpha:feat_req__alpha__long",
        "alpha-needs:feat_req__alpha__long",
    ]


def test_search_semantic_ranking_can_be_dictated(fx: SearchFixture) -> None:
    """With a query vector equal to one chunk's vector, that chunk is the semantic top hit."""
    import numpy as np

    snapshot = fx.data / "snapshots" / fx.snapshot_id
    manifest = __import__("json").loads((snapshot / "embedding-manifest.json").read_text())
    matrix = np.fromfile(snapshot / "embeddings.f32", dtype="<f4").reshape(
        manifest["rows"], manifest["dimension"]
    )
    provider = FakeEmbeddingProvider(query_vectors={"zzqx": matrix[2].tolist()})
    response = _search(fx, "zzqx", provider)
    assert response.results[0].chunk_id == manifest["row_chunk_ids"][2]
    assert response.results[0].matched_by == ["semantic"]


@pytest.mark.parametrize(
    ("provider", "reason", "guidance"),
    [
        (FakeEmbeddingProvider(mode="unreachable"), "embedding_runtime_unavailable", False),
        (FakeEmbeddingProvider(digest="9" * 64), "embedding_identity_mismatch", True),
        (FakeEmbeddingProvider(query_mode="unreachable"), "embedding_runtime_unavailable", False),
        (FakeEmbeddingProvider(query_mode="too_long"), "query_too_long_for_embedding", False),
    ],
)
def test_search_degrades_to_lexical(
    fx: SearchFixture, provider: FakeEmbeddingProvider, reason: str, guidance: bool
) -> None:
    response = _search(fx, "watchdog", provider)
    assert response.mode == "lexical"
    assert response.degraded is not None and response.degraded.reason == reason
    assert bool(response.degraded.guidance) is guidance
    assert response.results and all("semantic" not in r.matched_by for r in response.results)
    assert any("keyword results only" in w for w in response.warnings)


def test_search_long_query_skips_semantic(fx: SearchFixture) -> None:
    response = _search(fx, "abcdefghij " * 360)  # < 4 000 characters, > 1 800 estimated tokens
    assert response.degraded is not None
    assert response.degraded.reason == "query_too_long_for_embedding"


def test_search_forced_lexical(fx: SearchFixture) -> None:
    provider = FakeEmbeddingProvider()
    response = _search(fx, "watchdog", provider, force_lexical=True)
    assert response.mode == "lexical" and response.degraded is not None
    assert response.degraded.reason == "lexical_requested" and not response.warnings
    assert provider.query_calls == []


def test_search_without_any_provider(fx: SearchFixture) -> None:
    from score_docs_assistant.retrieval.service import SearchService

    service = SearchService(config=fx.config(), provider=None)
    response = service.search(SearchRequest(query="watchdog"))
    assert response.mode == "lexical" and response.results


def test_search_lexical_only_snapshot(tmp_path: Path) -> None:
    local = make_search_fixture(tmp_path, lexical_only=True)
    response = local.service().search(SearchRequest(query="watchdog"))
    assert response.degraded is not None and response.degraded.reason == "snapshot_lexical_only"
    assert response.semantic_status == "absent"


def test_search_deterministic(fx: SearchFixture) -> None:
    first = _search(fx, "watchdog telemetry quorum")
    second = _search(fx, "watchdog telemetry quorum")
    assert [r.chunk_id for r in first.results] == [r.chunk_id for r in second.results]
    assert [r.ranking_value for r in first.results] == [r.ranking_value for r in second.results]


def test_search_dedup_cap_and_distinct_sources(fx: SearchFixture) -> None:
    response = _search(fx, "quorum voting telemetry watchdog", limit=20)
    docs: dict[str, int] = {}
    for r in response.results:
        docs[r.path] = docs.get(r.path, 0) + 1
    assert max(docs.values()) <= 3
    quorum = [r for r in response.results if "quorum voting appears twice" in r.excerpt]
    assert len(quorum) <= 1
    # guide.rst hit the per-document cap above; query the shared sentence on its own.
    shared = _search(fx, "identical synthetic sentence telemetry", limit=20)
    telemetry = {r.source_id for r in shared.results if "telemetry" in r.excerpt}
    assert telemetry == {"alpha", "beta"}


def test_search_filters(fx: SearchFixture) -> None:
    response = _search(fx, "watchdog", sources=["beta"])
    assert response.results and {r.source_id for r in response.results} == {"beta"}
    response = _search(fx, "bazel docs", kinds=["code"])
    assert response.results and {r.kind for r in response.results} == {"code"}
    response = _search(fx, "feat_req__alpha__long", kinds=["prose"])
    assert all(r.kind == "prose" for r in response.results)
    with pytest.raises(SearchError) as exc_info:
        _search(fx, "watchdog", sources=["nope"])
    assert exc_info.value.code == "FILTER_INVALID" and "alpha" in exc_info.value.message


def test_search_input_validation(fx: SearchFixture) -> None:
    for kwargs, code in (
        ({"query": "   "}, "QUERY_INVALID"),
        ({"query": "x" * 4001}, "QUERY_INVALID"),
        ({"query": "x", "limit": 21}, "QUERY_INVALID"),
    ):
        with pytest.raises(SearchError) as exc_info:
            fx.service().search(SearchRequest(**kwargs))
        assert exc_info.value.code == code


def test_search_no_results_and_excerpt_bounds(fx: SearchFixture) -> None:
    empty = _search(fx, "xyzzyplugh", FakeEmbeddingProvider(mode="unreachable"))
    assert empty.status == "no_results" and empty.results == []
    response = fx.service(excerpt_characters=200).search(SearchRequest(query="watchdog"))
    for r in response.results:
        assert len(r.excerpt) <= 200
        assert not r.excerpt.startswith(("search_document:", "Title:"))


def test_citation_and_sources_and_snapshots(fx: SearchFixture) -> None:
    service = fx.service()
    result = _search(fx, "MLE.3.BP1").results[0]
    citation = service.citation(fx.snapshot_id, result.chunk_id)
    assert citation.text.startswith("Machine learning base practice")
    with pytest.raises(SearchError) as exc_info:
        service.citation(fx.snapshot_id, "0" * 64)
    assert exc_info.value.code == "CHUNK_NOT_FOUND"
    sources = service.sources()
    assert {s.source_id for s in sources.sources} == {"alpha", "alpha-needs", "beta"}
    listed = service.snapshots()
    assert listed.active == fx.snapshot_id
    assert [s.snapshot_id for s in listed.snapshots if s.active] == [fx.snapshot_id]
