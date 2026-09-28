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
