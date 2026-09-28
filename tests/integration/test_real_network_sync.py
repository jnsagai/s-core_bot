"""Opt-in: real `sources sync` of one upstream repository from GitHub (FR-003).

Skipped (reported "not run") unless SCORE_ASSISTANT_REAL_NETWORK=1; only this marked test may
open non-loopback connections (tests/conftest.py).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from score_docs_assistant.sources.lock import read_lock
from score_docs_assistant.sources.registry import SourceRegistry
from score_docs_assistant.sources.sync import SyncService

REGISTRY = Path(__file__).parent.parent.parent / "config" / "sources.yaml"


@pytest.mark.real_network
def test_real_sync_of_process_description(tmp_path: Path) -> None:
    raw = yaml.safe_load(REGISTRY.read_text())
    raw["sources"] = [s for s in raw["sources"] if s["source_id"] == "score-process"]
    registry = SourceRegistry.model_validate(raw)
    outcome = SyncService(registry, tmp_path / "data").run()
    assert outcome.exit_code == 0
    (entry,) = read_lock(tmp_path / "data" / "source-lock.json").sources
    assert entry.revision is not None and re.fullmatch(r"[0-9a-f]{40}", entry.revision)
    assert len(entry.files) > 100
    assert [f.path for f in entry.notice_files] == ["LICENSE", "NOTICE"]
