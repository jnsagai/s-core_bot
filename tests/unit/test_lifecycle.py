"""Activation and rollback (FR-012, FR-013, US2 AS1/AS4). Mocked provider."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.storage.catalog import Catalog
from tests.helpers.lifecycle import activate, active, rollback, snapshot_dir, snapshots, state
from tests.helpers.snapshot_env import make_env


def test_activate_then_switch(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    a, b = snapshots(env, 2)
    activate(env, a)
    assert (active(env), state(env, a)) == (a, "active")
    activate(env, b)
    assert (active(env), state(env, a), state(env, b)) == (b, "retired", "active")
    with Catalog.open(env.data, create=False) as catalog:  # type: ignore[union-attr]
        history = [(h.snapshot_id, h.previous_id, h.kind) for h in catalog.history()]
    assert history == [(a, None, "activate"), (b, a, "activate")]


def test_activate_active_is_noop(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    [a] = snapshots(env, 1)
    activate(env, a)
    assert activate(env, a) == []
    with Catalog.open(env.data, create=False) as catalog:  # type: ignore[union-attr]
        assert len(catalog.history()) == 1


def test_failed_snapshot_not_activatable(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    [a] = snapshots(env, 1)
    catalog = Catalog.open(env.data, create=False)
    assert catalog is not None
    with catalog, catalog.transaction() as conn:
        conn.execute("UPDATE snapshots SET state = 'failed' WHERE snapshot_id = ?", (a,))
    with pytest.raises(SnapshotError) as exc_info:
        activate(env, a)
    assert exc_info.value.code == "NOT_ACTIVATABLE"


def test_unknown_snapshot(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    snapshots(env, 1)
    with pytest.raises(SnapshotError) as exc_info:
        activate(env, "nope")
    assert exc_info.value.code == "SNAPSHOT_NOT_FOUND"


@pytest.mark.parametrize("target", ["reports/coverage.json", "manifest.json"])
def test_tampered_target_refused_and_active_unchanged(tmp_path: Path, target: str) -> None:
    env = make_env(tmp_path)
    a, b = snapshots(env, 2)
    activate(env, a)
    path = snapshot_dir(env, b) / target
    os.chmod(path, 0o644)
    with path.open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(SnapshotError) as exc_info:
        activate(env, b)
    assert exc_info.value.code == "CHECKSUM_MISMATCH"
    assert (active(env), state(env, b)) == (a, "validated")


def test_rollback_twice_returns(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    a, b = snapshots(env, 2)
    activate(env, a)
    activate(env, b)
    rollback(env)
    assert (active(env), state(env, b)) == (a, "retired")
    rollback(env)
    assert (active(env), state(env, a)) == (b, "retired")


def test_rollback_without_history(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    [a] = snapshots(env, 1)
    with pytest.raises(SnapshotError) as exc_info:
        rollback(env)
    assert exc_info.value.code == "NO_ROLLBACK_TARGET"
    activate(env, a)
    with pytest.raises(SnapshotError) as exc_info:
        rollback(env)
    assert exc_info.value.code == "NO_ROLLBACK_TARGET"


def test_lexical_over_semantic_warns(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    [semantic] = snapshots(env, 1)
    [lexical] = snapshots(env, 1, lexical_only=True)
    activate(env, semantic)
    warnings = activate(env, lexical)
    assert any("semantic search will be unavailable" in w for w in warnings)


def test_semantic_mismatch_is_warning_not_refusal(tmp_path: Path) -> None:
    from tests.helpers.fake_embedding import FakeEmbeddingProvider

    env = make_env(tmp_path)
    [a] = snapshots(env, 1)
    warnings = activate(env, a, runtime=FakeEmbeddingProvider(digest="d" * 64))
    assert active(env) == a
    assert any("semantic disabled" in w for w in warnings)
    warnings = activate(
        env, snapshots(env, 1)[0], runtime=FakeEmbeddingProvider(mode="unreachable")
    )
    assert any("semantic unverified" in w for w in warnings)
