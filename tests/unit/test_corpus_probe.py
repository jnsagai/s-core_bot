"""FileCorpusProbe states (FR-021, research R11). F001 only distinguished absent/incompatible and
never opened the catalog; F003 defines the catalog format, so the probe now reads it."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from score_docs_assistant.storage.corpus_probe import CorpusState, FileCorpusProbe
from tests.helpers.lifecycle import activate, snapshot_dir, snapshots
from tests.helpers.snapshot_env import make_env


def test_absent_when_no_catalog(tmp_path: Path) -> None:
    assert FileCorpusProbe(tmp_path).probe() == CorpusState.ABSENT
    assert not (tmp_path / "catalog.sqlite").exists()


def test_absent_when_nothing_active(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    snapshots(env, 1)
    assert FileCorpusProbe(env.data).probe() == CorpusState.ABSENT


def test_compatible_when_active_snapshot(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    [a] = snapshots(env, 1)
    activate(env, a)
    assert FileCorpusProbe(env.data).probe() == CorpusState.COMPATIBLE


def test_incompatible_when_catalog_is_garbage(tmp_path: Path) -> None:
    (tmp_path / "catalog.sqlite").write_bytes(b"not a real sqlite file" * 50)
    assert FileCorpusProbe(tmp_path).probe() == CorpusState.INCOMPATIBLE


def test_incompatible_when_catalog_schema_newer(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    [a] = snapshots(env, 1)
    activate(env, a)
    conn = sqlite3.connect(env.data / "catalog.sqlite")
    conn.execute("PRAGMA user_version = 9")
    conn.close()
    assert FileCorpusProbe(env.data).probe() == CorpusState.INCOMPATIBLE


def test_incompatible_when_active_manifest_missing_or_newer(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    [a] = snapshots(env, 1)
    activate(env, a)
    manifest = snapshot_dir(env, a) / "manifest.json"
    os.chmod(manifest, 0o644)
    text = manifest.read_text()
    manifest.write_text(text.replace('"schema_version": 1', '"schema_version": 5', 1))
    assert FileCorpusProbe(env.data).probe() == CorpusState.INCOMPATIBLE
    manifest.unlink()
    assert FileCorpusProbe(env.data).probe() == CorpusState.INCOMPATIBLE
