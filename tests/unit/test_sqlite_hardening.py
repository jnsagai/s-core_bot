"""Untrusted-database hardening on every SQLite connection (research R4, checklist CHK007)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from score_docs_assistant.storage.sqlite_util import open_hardened

SRC = Path(__file__).parent.parent.parent / "src"


def _make(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (a)")
    conn.commit()
    conn.close()


def test_writable_connection_is_hardened(tmp_path: Path) -> None:
    conn = open_hardened(tmp_path / "x.sqlite", readonly=False)
    assert conn.execute("PRAGMA trusted_schema").fetchone()[0] == 0
    assert conn.execute("PRAGMA cell_size_check").fetchone()[0] == 1
    assert conn.getconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE)
    conn.close()


def test_readonly_connection_cannot_write(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    _make(path)
    conn = open_hardened(path, readonly=True, immutable=True)
    assert conn.execute("PRAGMA trusted_schema").fetchone()[0] == 0
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO t VALUES (1)")
    conn.close()


def test_readonly_missing_file_is_not_created(tmp_path: Path) -> None:
    with pytest.raises(sqlite3.OperationalError):
        open_hardened(tmp_path / "missing.sqlite", readonly=True)
    assert not (tmp_path / "missing.sqlite").exists()


def test_extension_loading_never_enabled_in_source() -> None:
    offenders = [
        p for p in SRC.rglob("*.py") if "enable_load_extension" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []
