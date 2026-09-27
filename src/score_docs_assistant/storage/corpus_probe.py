"""Corpus catalog probe. F001 only checks for the catalog file's existence — it MUST NOT open it
(data-model.md CorpusState; `compatible` is added once F003 defines the catalog format)."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Protocol


class CorpusState(StrEnum):
    ABSENT = "absent"
    INCOMPATIBLE = "incompatible"


class CorpusProbe(Protocol):
    def probe(self) -> CorpusState: ...


class FileCorpusProbe:
    def __init__(self, data_dir: Path) -> None:
        self._catalog_path = data_dir / "catalog.sqlite"

    def probe(self) -> CorpusState:
        if not self._catalog_path.exists():
            return CorpusState.ABSENT
        return CorpusState.INCOMPATIBLE
