"""Catalog schema and transactions (FR-011, FR-013, FR-017, checklist CHK025)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.storage.catalog import Catalog


def _published(cat: Catalog, sid: str, job: str) -> None:
    cat.start_job(job, "build", sid, 1)
    cat.publish(
        snapshot_id=sid,
        job_id=job,
        manifest_sha256="m",
        schema_version=1,
        semantic="present",
        chunks=3,
    )


def test_not_created_by_readers(tmp_path: Path) -> None:
    assert Catalog.open(tmp_path, create=False) is None
    assert not (tmp_path / "catalog.sqlite").exists()


def test_build_lifecycle_rows(tmp_path: Path) -> None:
    with Catalog.open(tmp_path, create=True) as cat:  # type: ignore[union-attr]
        cat.start_job("j1", "build", "s1", 123)
        s1 = cat.get("s1")
        assert s1 is not None and s1.state == "building"
        cat.set_stage("j1", "chunking")
        cat.publish(
            snapshot_id="s1",
            job_id="j1",
            manifest_sha256="m",
            schema_version=1,
            semantic="absent",
            chunks=0,
        )
        s1 = cat.get("s1")
        assert s1 is not None and s1.state == "validated" and s1.semantic == "absent"
        [job] = cat.jobs()
        assert job.state == "succeeded" and job.stage == "chunking"
        cat.start_job("j2", "build", "s2", 1)
        cat.fail(job_id="j2", snapshot_id="s2", reason="boom")
        s2 = cat.get("s2")
        assert s2 is not None and s2.state == "failed" and s2.failure == "boom"


def test_recover_interrupted(tmp_path: Path) -> None:
    with Catalog.open(tmp_path, create=True) as cat:  # type: ignore[union-attr]
        cat.start_job("j1", "build", "s1", 1)
        assert cat.recover_interrupted() == ["s1"]
        s1 = cat.get("s1")
        assert s1 is not None and s1.state == "failed" and s1.failure == "interrupted"
        assert cat.jobs()[0].failure == "interrupted"


def test_switch_active_history_and_single_active(tmp_path: Path) -> None:
    with Catalog.open(tmp_path, create=True) as cat:  # type: ignore[union-attr]
        _published(cat, "a", "ja")
        _published(cat, "b", "jb")
        assert cat.switch_active("a", "activate") is None
        assert cat.switch_active("b", "activate") == "a"
        a, b = cat.get("a"), cat.get("b")
        assert a is not None and a.state == "retired"
        assert b is not None and b.state == "active"
        assert cat.active_id() == "b"
        latest = cat.latest_activation()
        assert latest is not None and (latest.snapshot_id, latest.previous_id) == ("b", "a")
        with pytest.raises(sqlite3.IntegrityError), cat.transaction() as conn:
            conn.execute("UPDATE snapshots SET state = 'active' WHERE snapshot_id = 'a'")


@pytest.mark.parametrize("state", ["building", "failed", "deleted"])
def test_not_activatable_states(tmp_path: Path, state: str) -> None:
    with Catalog.open(tmp_path, create=True) as cat:  # type: ignore[union-attr]
        _published(cat, "a", "ja")
        with cat.transaction() as conn:
            conn.execute("UPDATE snapshots SET state = ? WHERE snapshot_id = 'a'", (state,))
        with pytest.raises(SnapshotError) as exc_info:
            cat.switch_active("a", "activate")
        assert exc_info.value.code == "NOT_ACTIVATABLE"
        assert cat.active_id() is None


def test_newer_schema_refused(tmp_path: Path) -> None:
    Catalog.open(tmp_path, create=True).close()  # type: ignore[union-attr]
    conn = sqlite3.connect(tmp_path / "catalog.sqlite")
    conn.execute("PRAGMA user_version = 2")
    conn.close()
    with pytest.raises(SnapshotError) as exc_info:
        Catalog.open(tmp_path, create=True)
    assert exc_info.value.code == "SCHEMA_UNSUPPORTED"


def test_corrupt_catalog_not_recreated(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite"
    path.write_bytes(b"this is not a database" * 100)
    with pytest.raises(SnapshotError) as exc_info:
        Catalog.open(tmp_path, create=True)
    assert exc_info.value.code == "CATALOG_UNREADABLE"
    assert path.read_bytes().startswith(b"this is not a database")
