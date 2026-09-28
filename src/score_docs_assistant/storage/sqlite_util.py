"""Hardened SQLite connections (specs/003-snapshot-index/research.md R4).

Corpus files may arrive in bundles, so every connection applies SQLite's untrusted-database
settings. Extension loading is never enabled anywhere in this package.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote


def open_hardened(
    path: Path, *, readonly: bool, immutable: bool = False, check_same_thread: bool = True
) -> sqlite3.Connection:
    if readonly:
        uri = f"file:{quote(str(path.resolve()))}?mode=ro"
        if immutable:
            uri += "&immutable=1"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=check_same_thread)
    else:
        conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    try:
        conn.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
        conn.execute("PRAGMA trusted_schema = OFF")
        conn.execute("PRAGMA cell_size_check = ON")
        # Opening is lazy; force the file open so a missing read-only file fails here.
        conn.execute("PRAGMA schema_version").fetchone()
    except BaseException:
        conn.close()
        raise
    return conn
