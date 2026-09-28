"""Pinned, read-only snapshot access (FR-014; master spec §5.1 `SnapshotStore`).

`pin()` takes the shared pin lock first and only then re-checks that the snapshot still exists,
so retention can never delete it underneath the reader (research R8). Every read goes through
the handle, which serves exactly one snapshot's manifest, corpus and vectors.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.snapshots import CorpusSnapshot, SnapshotManifest
from score_docs_assistant.retrieval.query import valid_snapshot_id
from score_docs_assistant.storage.catalog import Catalog
from score_docs_assistant.storage.corpus_db import open_corpus_readonly
from score_docs_assistant.storage.manifest import (
    CORPUS_NAME,
    VECTORS_NAME,
    read_embedding_manifest,
    read_snapshot_manifest,
)
from score_docs_assistant.storage.pins import Pin
from score_docs_assistant.storage.vectors import Matrix, open_vectors

_READABLE_STATES = frozenset({"validated", "active", "retired"})


class FileSnapshotHandle:
    def __init__(self, pin: Pin, directory: Path, manifest: SnapshotManifest) -> None:
        self._pin = pin
        self._directory = directory
        self._manifest = manifest
        self._corpus: sqlite3.Connection | None = None
        self._vectors: Matrix | None = None

    @property
    def snapshot_id(self) -> str:
        return self._manifest.snapshot_id

    @property
    def manifest(self) -> SnapshotManifest:
        return self._manifest

    @property
    def directory(self) -> Path:
        return self._directory

    def corpus(self) -> sqlite3.Connection:
        if self._corpus is None:
            self._corpus = open_corpus_readonly(
                self._directory / CORPUS_NAME, check_same_thread=False
            )
        return self._corpus

    def vectors(self) -> Matrix | None:
        """Read-only memmap of the vectors, or None for a lexical-only snapshot."""
        if self._manifest.semantic != "present":
            return None
        if self._vectors is None:
            emb = read_embedding_manifest(self._directory)
            self._vectors = open_vectors(self._directory / VECTORS_NAME, emb.rows, emb.dimension)
        return self._vectors

    def close(self) -> None:
        if self._corpus is not None:
            self._corpus.close()
            self._corpus = None
        self._vectors = None
        self._pin.close()

    def __enter__(self) -> FileSnapshotHandle:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class FileSnapshotStore:
    def __init__(self, data_dir: Path) -> None:
        self._data = data_dir

    def _catalog(self) -> Catalog:
        catalog = Catalog.open(self._data, create=False)
        if catalog is None:
            raise SnapshotError("SNAPSHOT_NOT_FOUND", "no catalog yet; run `index build` first")
        return catalog

    def list(self, include_deleted: bool = False) -> Sequence[CorpusSnapshot]:
        catalog = Catalog.open(self._data, create=False)
        if catalog is None:
            return []
        with catalog:
            return catalog.snapshots(include_deleted=include_deleted)

    def pin(self, snapshot_id: str) -> FileSnapshotHandle:
        # IDs may come from requests (F004); validate before any path is built from them.
        if not valid_snapshot_id(snapshot_id):
            raise SnapshotError("SNAPSHOT_NOT_FOUND", "invalid snapshot ID")
        pin = Pin(self._data, snapshot_id)
        try:
            with self._catalog() as catalog:
                row = catalog.get(snapshot_id)
            directory = self._data / "snapshots" / snapshot_id
            if row is None or row.state not in _READABLE_STATES or not directory.is_dir():
                state = "missing" if row is None else row.state
                raise SnapshotError("SNAPSHOT_NOT_FOUND", f"snapshot {snapshot_id} is {state}")
            manifest = read_snapshot_manifest(directory)
        except BaseException:
            pin.close()
            raise
        return FileSnapshotHandle(pin, directory, manifest)

    def pin_active(self) -> FileSnapshotHandle:
        # One retry: an activation plus retention may remove the snapshot between resolving
        # the pointer and taking the pin.
        for attempt in (1, 2):
            with self._catalog() as catalog:
                active = catalog.active_id()
            if active is None:
                raise SnapshotError("SNAPSHOT_NOT_FOUND", "no active snapshot")
            try:
                return self.pin(active)
            except SnapshotError:
                if attempt == 2:
                    raise
        raise AssertionError("unreachable")
