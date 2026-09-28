"""Cross-process pins and pinned reads across activation (FR-014, SC-008, research R8)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.storage.catalog import Catalog
from score_docs_assistant.storage.snapshot_store import FileSnapshotStore
from tests.helpers.lifecycle import (
    MESSAGES,
    activate,
    build_and_activate,
    snapshot_dir,
    snapshots,
    state,
)
from tests.helpers.procs import hold_pin, kill9
from tests.helpers.snapshot_env import SourceSpec, default_sources, make_env


def test_pinned_snapshot_survives_retention_until_holder_killed(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    [a] = build_and_activate(env, 1)
    proc = hold_pin(env.data, a, tmp_path)
    try:
        build_and_activate(env, 1)
        MESSAGES.clear()
        build_and_activate(env, 1)  # keeps the active one + its rollback target; a is pinned
        assert snapshot_dir(env, a).is_dir() and state(env, a) == "retired"
        assert any(f"kept {a} (pinned" in m for m in MESSAGES)
    finally:
        kill9(proc)
    build_and_activate(env, 1)  # retention again; the killed reader's pin no longer blocks
    assert not snapshot_dir(env, a).exists() and state(env, a) == "deleted"


def test_pinned_handle_reads_original_snapshot_after_activation(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    [a] = snapshots(env, 1)
    activate(env, a)
    store = FileSnapshotStore(env.data)
    with store.pin_active() as handle:
        assert handle.snapshot_id == a
        before_chunks = handle.corpus().execute("SELECT count(*) FROM chunks").fetchone()[0]
        vectors_before = np.array(handle.vectors())

        changed = default_sources()
        changed[1] = SourceSpec(
            "beta", {"docs/shared.rst": "Beta\n====\n\nNew text only.\n"}, "d" * 40
        )
        env.write(changed)
        [b] = snapshots(env, 1)
        activate(env, b)

        assert handle.snapshot_id == a and handle.manifest.snapshot_id == a
        assert handle.corpus().execute("SELECT count(*) FROM chunks").fetchone()[0] == before_chunks
        hits = (
            handle.corpus()
            .execute("SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'std_req__beta__one'")
            .fetchone()[0]
        )
        assert hits >= 1
        np.testing.assert_array_equal(np.array(handle.vectors()), vectors_before)
    with store.pin_active() as handle:
        assert handle.snapshot_id == b


def test_pin_deleted_snapshot_not_found(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    [a] = snapshots(env, 1)
    catalog = Catalog.open(env.data, create=False)
    assert catalog is not None
    with catalog, catalog.transaction() as conn:
        conn.execute("UPDATE snapshots SET state = 'deleted' WHERE snapshot_id = ?", (a,))
    with pytest.raises(SnapshotError) as exc_info:
        FileSnapshotStore(env.data).pin(a)
    assert exc_info.value.code == "SNAPSHOT_NOT_FOUND"


def test_pin_active_retries_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = make_env(tmp_path)
    [a] = build_and_activate(env, 1)
    [b] = snapshots(env, 1)
    store = FileSnapshotStore(env.data)
    original = store.pin
    calls: list[str] = []

    def flaky(snapshot_id: str):  # type: ignore[no-untyped-def]
        calls.append(snapshot_id)
        if len(calls) == 1:
            activate(env, b)  # the pointer moves between resolve and pin
            raise SnapshotError("SNAPSHOT_NOT_FOUND", "gone")
        return original(snapshot_id)

    monkeypatch.setattr(store, "pin", flaky)
    with store.pin_active() as handle:
        assert handle.snapshot_id == b
    assert calls == [a, b]
