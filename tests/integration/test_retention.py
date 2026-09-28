"""Retention of snapshots and sources (FR-015, research R12, checklist CHK023). Mocked provider."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.storage.catalog import Catalog
from tests.helpers.lifecycle import (
    activate,
    build_and_activate,
    snapshot_dir,
    snapshots,
    state,
)
from tests.helpers.snapshot_env import SourceSpec, default_sources, make_env


def test_keeps_active_and_previous_deletes_older(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    ids = build_and_activate(env, 4)
    assert [state(env, s) for s in ids] == ["deleted", "deleted", "retired", "active"]
    assert not snapshot_dir(env, ids[0]).exists()
    assert not (env.data / "pins" / f"{ids[0]}.pin").exists()


def test_rollback_target_kept_even_when_newer_validated_exist(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    z, a = snapshots(env, 2)
    activate(env, z)
    activate(env, a)
    b, c = snapshots(env, 2)  # newer, validated, never activated
    activate(env, c)
    assert state(env, a) == "retired"  # rollback target of c: kept
    assert snapshot_dir(env, a).is_dir()
    assert state(env, b) == "deleted" and state(env, z) == "deleted"


def test_unreferenced_sources_and_caches_pruned(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    [a] = build_and_activate(env, 1)
    (env.data / "cache" / "git" / "alpha.git").mkdir(parents=True)
    (env.data / "cache" / "git" / "zeta.git").mkdir(parents=True)
    changed = default_sources()
    changed[1] = SourceSpec("beta", {"docs/shared.rst": "Beta\n====\n\nChanged.\n"}, "e" * 40)
    env.write(changed)
    build_and_activate(env, 2)  # a deleted → beta@bbbb… referenced by nothing (lock now at eeee…)
    assert state(env, a) == "deleted"
    assert not (env.data / "sources" / "beta" / ("b" * 40)).exists()
    assert (env.data / "sources" / "beta" / ("e" * 40)).is_dir()
    assert (env.data / "sources" / "alpha" / ("a" * 40)).is_dir()
    assert (env.data / "cache" / "git" / "alpha.git").is_dir()
    assert not (env.data / "cache" / "git" / "zeta.git").exists()


def test_crash_mid_deletion_is_completed_later(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    a, _b = build_and_activate(env, 2)
    # Simulate a retention crash that removed part of a's directory before marking it deleted.
    shutil.rmtree(snapshot_dir(env, a) / "reports")
    assert state(env, a) == "retired"
    catalog = Catalog.open(env.data, create=False)
    assert catalog is not None
    with catalog:
        latest = catalog.latest_activation()
        assert latest is not None and latest.previous_id == a
    with pytest.raises(SnapshotError) as exc_info:
        activate(env, a)
    assert exc_info.value.code == "CHECKSUM_MISMATCH"
    build_and_activate(env, 2)
    assert state(env, a) == "deleted" and not snapshot_dir(env, a).exists()
