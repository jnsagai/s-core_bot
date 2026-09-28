"""FileCorpusProbe only checks existence; it must never open the catalog file (FR-024)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from score_docs_assistant.storage.corpus_probe import CorpusState, FileCorpusProbe


def test_absent_when_no_catalog(tmp_path: Path) -> None:
    probe = FileCorpusProbe(tmp_path)
    assert probe.probe() == CorpusState.ABSENT


def test_incompatible_when_catalog_present_and_never_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_path / "catalog.sqlite"
    catalog.write_bytes(b"not a real sqlite file")

    def _fail_open(*args: object, **kwargs: object) -> None:
        raise AssertionError("FileCorpusProbe must not open the catalog file in F001")

    monkeypatch.setattr(sqlite3, "connect", _fail_open)
    real_open = open

    def _guarded_open(file: object, *args: object, **kwargs: object) -> object:
        if str(file) == str(catalog):
            raise AssertionError("FileCorpusProbe must not open the catalog file in F001")
        return real_open(file, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("builtins.open", _guarded_open)

    probe = FileCorpusProbe(tmp_path)
    assert probe.probe() == CorpusState.INCOMPATIBLE
