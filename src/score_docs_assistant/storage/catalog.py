"""`data/catalog.sqlite`: snapshot states, active pointer, activation history, build jobs.

Contract: specs/003-snapshot-index/contracts/catalog.md. Every mutation is one
`BEGIN IMMEDIATE` transaction. An existing catalog that cannot be opened, fails `quick_check`, or
has a newer `user_version` is never recreated or repaired automatically.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.snapshots import (
    CATALOG_SCHEMA_VERSION,
    ActivationRecord,
    BuildJob,
    CorpusSnapshot,
)
from score_docs_assistant.storage.sqlite_util import open_hardened

CATALOG_NAME = "catalog.sqlite"

_SCHEMA = (
    """CREATE TABLE snapshots (
  snapshot_id TEXT PRIMARY KEY,
  state TEXT NOT NULL CHECK (state IN
    ('building','validated','active','retired','failed','deleted')),
  created_at TEXT NOT NULL, validated_at TEXT, activated_at TEXT, retired_at TEXT,
  deleted_at TEXT, manifest_sha256 TEXT, schema_version INTEGER,
  semantic TEXT CHECK (semantic IN ('present','absent')),
  chunks INTEGER, job_id TEXT, failure TEXT)""",
    "CREATE UNIQUE INDEX one_active ON snapshots (state) WHERE state = 'active'",
    """CREATE TABLE active_pointer (id INTEGER PRIMARY KEY CHECK (id = 1),
  snapshot_id TEXT REFERENCES snapshots, updated_at TEXT NOT NULL)""",
    """CREATE TABLE activation_history (seq INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id TEXT NOT NULL, previous_id TEXT,
  kind TEXT NOT NULL CHECK (kind IN ('activate','rollback')), at TEXT NOT NULL)""",
    """CREATE TABLE build_jobs (job_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('build','import')),
  state TEXT NOT NULL CHECK (state IN ('running','succeeded','failed')),
  pid INTEGER NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, snapshot_id TEXT,
  stage TEXT, failure TEXT)""",
)

_SNAPSHOT_COLUMNS = (
    "snapshot_id, state, created_at, validated_at, activated_at, retired_at, deleted_at, "
    "manifest_sha256, schema_version, semantic, chunks, job_id, failure"
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _row_to_snapshot(row: sqlite3.Row) -> CorpusSnapshot:
    return CorpusSnapshot.model_validate(dict(row))


class Catalog:
    """Thin transactional wrapper. Construct with `Catalog.open(data_dir, create=...)`."""

    def __init__(self, conn: sqlite3.Connection, path: Path) -> None:
        self._conn = conn
        self.path = path

    # --- lifecycle -----------------------------------------------------------------------------

    @classmethod
    def open(cls, data_dir: Path, *, create: bool) -> Catalog | None:
        """Open the catalog; `None` when it does not exist and `create` is false."""
        path = data_dir / CATALOG_NAME
        existed = path.exists()
        if not existed and not create:
            return None
        if not existed:
            data_dir.mkdir(parents=True, exist_ok=True)
        try:
            conn = open_hardened(path, readonly=False)
            conn.row_factory = sqlite3.Row
            conn.isolation_level = None  # explicit BEGIN IMMEDIATE below
            if existed:
                cls._check_existing(conn, path)
            else:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("BEGIN IMMEDIATE")
                for statement in _SCHEMA:
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {CATALOG_SCHEMA_VERSION}")
                conn.execute("COMMIT")
        except sqlite3.DatabaseError as exc:
            raise SnapshotError(
                "CATALOG_UNREADABLE",
                f"{path}: {exc}. The catalog is not repaired automatically; move it aside and "
                "re-register snapshots (see quickstart).",
            ) from exc
        return cls(conn, path)

    @staticmethod
    def _check_existing(conn: sqlite3.Connection, path: Path) -> None:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version > CATALOG_SCHEMA_VERSION:
            conn.close()
            raise SnapshotError(
                "SCHEMA_UNSUPPORTED",
                f"{path}: catalog schema {version} is newer than supported "
                f"{CATALOG_SCHEMA_VERSION}",
            )
        result = conn.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok" or version != CATALOG_SCHEMA_VERSION:
            conn.close()
            raise SnapshotError(
                "CATALOG_UNREADABLE",
                f"{path}: integrity check failed ({result}, schema {version}); not repaired "
                "automatically",
            )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Catalog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    # --- queries -------------------------------------------------------------------------------

    def get(self, snapshot_id: str) -> CorpusSnapshot | None:
        row = self._conn.execute(
            f"SELECT {_SNAPSHOT_COLUMNS} FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        return None if row is None else _row_to_snapshot(row)

    def snapshots(self, include_deleted: bool = False) -> list[CorpusSnapshot]:
        where = "" if include_deleted else "WHERE state != 'deleted'"
        rows = self._conn.execute(
            f"SELECT {_SNAPSHOT_COLUMNS} FROM snapshots {where} ORDER BY created_at DESC, "
            "snapshot_id DESC"
        ).fetchall()
        return [_row_to_snapshot(r) for r in rows]

    def active_id(self) -> str | None:
        row = self._conn.execute("SELECT snapshot_id FROM active_pointer WHERE id = 1").fetchone()
        return None if row is None else row[0]

    def latest_activation(self) -> ActivationRecord | None:
        row = self._conn.execute(
            "SELECT seq, snapshot_id, previous_id, kind, at FROM activation_history "
            "ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return None if row is None else ActivationRecord.model_validate(dict(row))

    def history(self) -> list[ActivationRecord]:
        rows = self._conn.execute(
            "SELECT seq, snapshot_id, previous_id, kind, at FROM activation_history ORDER BY seq"
        ).fetchall()
        return [ActivationRecord.model_validate(dict(r)) for r in rows]

    def jobs(self) -> list[BuildJob]:
        rows = self._conn.execute(
            "SELECT job_id, kind, state, pid, started_at, finished_at, snapshot_id, stage, "
            "failure FROM build_jobs ORDER BY started_at"
        ).fetchall()
        return [BuildJob.model_validate(dict(r)) for r in rows]

    # --- build transactions --------------------------------------------------------------------

    def start_job(self, job_id: str, kind: str, snapshot_id: str, pid: int) -> None:
        at = now_iso()
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO build_jobs (job_id, kind, state, pid, started_at, snapshot_id) "
                "VALUES (?, ?, 'running', ?, ?, ?)",
                (job_id, kind, pid, at, snapshot_id),
            )
            if kind == "build":
                conn.execute(
                    "INSERT INTO snapshots (snapshot_id, state, created_at, job_id) "
                    "VALUES (?, 'building', ?, ?)",
                    (snapshot_id, at, job_id),
                )

    def set_stage(self, job_id: str, stage: str) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE build_jobs SET stage = ? WHERE job_id = ?", (stage, job_id))

    def publish(
        self,
        *,
        snapshot_id: str,
        job_id: str,
        manifest_sha256: str,
        schema_version: int,
        semantic: str,
        chunks: int,
        created_at: str | None = None,
    ) -> None:
        """Build: `building → validated`. Import: insert (or revive a deleted row) as
        `validated`. Either way the job is marked succeeded in the same transaction."""
        at = now_iso()
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT state FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
            values = (manifest_sha256, schema_version, semantic, chunks, at, job_id)
            if existing is None:
                conn.execute(
                    "INSERT INTO snapshots (manifest_sha256, schema_version, semantic, chunks, "
                    "validated_at, job_id, snapshot_id, state, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'validated', ?)",
                    (*values, snapshot_id, created_at or at),
                )
            elif existing[0] in ("building", "deleted"):
                conn.execute(
                    "UPDATE snapshots SET manifest_sha256 = ?, schema_version = ?, semantic = ?, "
                    "chunks = ?, validated_at = ?, job_id = ?, state = 'validated', "
                    "deleted_at = NULL, retired_at = NULL, failure = NULL WHERE snapshot_id = ?",
                    (*values, snapshot_id),
                )
            else:
                raise SnapshotError(
                    "BUILD_FAILED", f"{snapshot_id} is {existing[0]}; cannot publish again"
                )
            conn.execute(
                "UPDATE build_jobs SET state = 'succeeded', finished_at = ? WHERE job_id = ?",
                (at, job_id),
            )

    def fail(self, *, job_id: str, snapshot_id: str | None, reason: str) -> None:
        at = now_iso()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE build_jobs SET state = 'failed', finished_at = ?, failure = ? "
                "WHERE job_id = ?",
                (at, reason, job_id),
            )
            if snapshot_id is not None:
                conn.execute(
                    "UPDATE snapshots SET state = 'failed', failure = ? "
                    "WHERE snapshot_id = ? AND state = 'building'",
                    (reason, snapshot_id),
                )

    def recover_interrupted(self) -> list[str]:
        """Mark every job still `running` (and its `building` snapshot) failed. Only call while
        holding the ingest lock: then no other process can own a running job."""
        at = now_iso()
        with self.transaction() as conn:
            rows = conn.execute(
                "SELECT job_id, snapshot_id FROM build_jobs WHERE state = 'running'"
            ).fetchall()
            for job_id, snapshot_id in rows:
                conn.execute(
                    "UPDATE build_jobs SET state = 'failed', finished_at = ?, "
                    "failure = 'interrupted' WHERE job_id = ?",
                    (at, job_id),
                )
                conn.execute(
                    "UPDATE snapshots SET state = 'failed', failure = 'interrupted' "
                    "WHERE snapshot_id = ? AND state = 'building'",
                    (snapshot_id,),
                )
            stale = conn.execute(
                "SELECT snapshot_id FROM snapshots WHERE state = 'building'"
            ).fetchall()
            for (snapshot_id,) in stale:
                conn.execute(
                    "UPDATE snapshots SET state = 'failed', failure = 'interrupted' "
                    "WHERE snapshot_id = ?",
                    (snapshot_id,),
                )
        return [r[1] for r in rows if r[1]] + [s[0] for s in stale]

    # --- lifecycle transactions ----------------------------------------------------------------

    def switch_active(self, target: str, kind: str) -> str | None:
        """One transaction: current active → retired, target → active, pointer, history row.
        Returns the previously active ID."""
        at = now_iso()
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT state FROM snapshots WHERE snapshot_id = ?", (target,)
            ).fetchone()
            if row is None or row[0] not in ("validated", "retired"):
                state = "missing" if row is None else row[0]
                raise SnapshotError("NOT_ACTIVATABLE", f"{target} is {state}")
            pointer = conn.execute("SELECT snapshot_id FROM active_pointer WHERE id = 1").fetchone()
            previous = None if pointer is None else pointer[0]
            if previous is not None:
                conn.execute(
                    "UPDATE snapshots SET state = 'retired', retired_at = ? "
                    "WHERE snapshot_id = ? AND state = 'active'",
                    (at, previous),
                )
            conn.execute(
                "UPDATE snapshots SET state = 'active', activated_at = ?, retired_at = NULL "
                "WHERE snapshot_id = ?",
                (at, target),
            )
            conn.execute(
                "INSERT INTO active_pointer (id, snapshot_id, updated_at) VALUES (1, ?, ?) "
                "ON CONFLICT (id) DO UPDATE SET snapshot_id = excluded.snapshot_id, "
                "updated_at = excluded.updated_at",
                (target, at),
            )
            conn.execute(
                "INSERT INTO activation_history (snapshot_id, previous_id, kind, at) "
                "VALUES (?, ?, ?, ?)",
                (target, previous, kind, at),
            )
        return previous

    def mark_deleted(self, snapshot_id: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE snapshots SET state = 'deleted', deleted_at = ? "
                "WHERE snapshot_id = ? AND state IN ('retired', 'validated', 'failed')",
                (now_iso(), snapshot_id),
            )
