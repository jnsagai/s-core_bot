"""Corpus probe for readiness and `doctor` (FR-021, specs/003-snapshot-index/research.md R11).

`compatible` means: a readable catalog with a supported schema, an active snapshot, and that
snapshot's manifest present with a supported schema. The probe does not hash files (it runs on
every readiness refresh); full verification happens at activation and in `index validate`.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Protocol

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.storage.catalog import CATALOG_NAME, Catalog
from score_docs_assistant.storage.manifest import read_snapshot_manifest


class CorpusState(StrEnum):
    ABSENT = "absent"
    INCOMPATIBLE = "incompatible"
    COMPATIBLE = "compatible"


class CorpusProbe(Protocol):
    def probe(self) -> CorpusState: ...


class FileCorpusProbe:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def probe(self) -> CorpusState:
        if not (self._data_dir / CATALOG_NAME).exists():
            return CorpusState.ABSENT
        try:
            catalog = Catalog.open(self._data_dir, create=False)
            if catalog is None:
                return CorpusState.ABSENT
            with catalog:
                active = catalog.active_id()
                row = catalog.get(active) if active else None
            if row is None or row.state != "active":
                return CorpusState.ABSENT
            read_snapshot_manifest(self._data_dir / "snapshots" / row.snapshot_id)
        except SnapshotError:
            return CorpusState.INCOMPATIBLE
        return CorpusState.COMPATIBLE
