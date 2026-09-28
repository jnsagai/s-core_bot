"""Relationships exactly as stored (FR-005). Mocked provider."""

from __future__ import annotations

import pytest

from score_docs_assistant.domain.errors import SearchError
from tests.helpers.search import SearchFixture, make_search_fixture


@pytest.fixture(scope="module")
def fx(tmp_path_factory: pytest.TempPathFactory) -> SearchFixture:
    return make_search_fixture(tmp_path_factory.mktemp("rel"))


def test_outgoing_links_as_stored(fx: SearchFixture) -> None:
    response = fx.service().relationships("alpha:feat_req__alpha__short", direction="out")
    assert response.outgoing_total == 2
    by_target = {r.target_id: r for r in response.items}
    assert by_target["feat_req__alpha__long"].resolution == "resolved"
    assert by_target["feat_req__alpha__long"].resolved_keys == ["alpha:feat_req__alpha__long"]
    assert by_target["feat_req__missing"].resolution == "unresolved"
    assert all(r.via == "satisfies" and r.direction == "out" for r in response.items)


def test_incoming_links(fx: SearchFixture) -> None:
    response = fx.service().relationships("alpha:feat_req__alpha__long", direction="in")
    assert response.incoming_total == 1
    [item] = response.items
    assert (item.direction, item.from_key) == ("in", "alpha:feat_req__alpha__short")
    export = fx.service().relationships("alpha-needs:feat_req__alpha__long", direction="in")
    assert [i.from_key for i in export.items] == ["alpha-needs:feat_req__alpha__short"]


def test_both_directions_and_paging(fx: SearchFixture) -> None:
    both = fx.service().relationships("alpha:feat_req__alpha__short")
    assert (both.outgoing_total, both.incoming_total) == (2, 0)
    page = fx.service().relationships("alpha:feat_req__alpha__short", limit=1, offset=1)
    assert len(page.items) == 1 and page.items[0] == both.items[1]
    with pytest.raises(SearchError):
        fx.service().relationships("alpha:feat_req__alpha__short", limit=201)


def test_unknown_key(fx: SearchFixture) -> None:
    with pytest.raises(SearchError) as exc_info:
        fx.service().relationships("alpha:nope")
    assert exc_info.value.code == "ENTITY_NOT_FOUND"
