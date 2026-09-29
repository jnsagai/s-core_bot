"""Snapshot metadata comparison and coverage reasons (FR-009, FR-010, research R4, R5a, R6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from score_docs_assistant.comparison.coverage import missing_reason, reason_text, source_reason
from score_docs_assistant.comparison.metadata import IDENTICAL_REVISIONS, snapshot_diff
from score_docs_assistant.domain.snapshots import SnapshotManifest
from score_docs_assistant.storage.manifest import read_snapshot_manifest
from tests.helpers.comparison_fixtures import (
    LEFT_REV,
    PLATFORM_REV,
    RIGHT_REV,
    ComparisonFixture,
    make_comparison_fixture,
)


@pytest.fixture(scope="module")
def fixture(tmp_path_factory: pytest.TempPathFactory) -> ComparisonFixture:
    return make_comparison_fixture(tmp_path_factory.mktemp("cmp"))


def manifest(fixture: ComparisonFixture, snapshot_id: str) -> SnapshotManifest:
    return read_snapshot_manifest(fixture.data / "snapshots" / snapshot_id)


def test_relations_and_warnings(fixture: ComparisonFixture) -> None:
    left, right = manifest(fixture, fixture.left_id), manifest(fixture, fixture.right_id)
    diff = snapshot_diff(left, right)
    rows = {r.source_id: r for r in diff.sources}
    assert rows["proc"].relation == "different"
    assert (rows["proc"].left_revision, rows["proc"].right_revision) == (LEFT_REV, RIGHT_REV)
    assert rows["proc"].left_revision_status == rows["proc"].right_revision_status == "pinned"
    assert rows["platform"].relation == "right_only"
    assert (
        rows["platform"].left_revision is None and rows["platform"].right_revision == PLATFORM_REV
    )
    assert any(w.startswith("source_only_on_one_side: platform") for w in diff.warnings)
    assert IDENTICAL_REVISIONS not in diff.warnings
    assert diff.release_label is None
    assert (diff.left_snapshot_id, diff.right_snapshot_id) == (fixture.left_id, fixture.right_id)


def test_identical_revisions_warning(fixture: ComparisonFixture) -> None:
    right = manifest(fixture, fixture.right_id)
    other = right.model_copy(update={"snapshot_id": "20990101T000000Z-cccccccc"})
    diff = snapshot_diff(right, other)
    assert diff.warnings[0] == IDENTICAL_REVISIONS
    assert {r.relation for r in diff.sources} == {"same"}
    assert diff.processing == []


def test_left_only_unverified_failed_and_processing(fixture: ComparisonFixture) -> None:
    left, right = manifest(fixture, fixture.left_id), manifest(fixture, fixture.right_id)
    proc = left.sources[0]
    extra = proc.model_copy(
        update={"source_id": "proc-needs", "kind": "needs-export", "revision_status": "unverified"}
    )
    failed = proc.model_copy(update={"source_id": "broken", "status": "failed", "revision": None})
    changed = left.model_copy(
        update={"sources": [proc, extra, failed], "chunker_version": "chunker-v0"}
    )
    diff = snapshot_diff(changed, right)
    rows = {r.source_id: r for r in diff.sources}
    assert rows["proc-needs"].relation == "left_only"
    assert rows["broken"].left_status == "failed"
    text = "\n".join(diff.warnings)
    assert "unverified_revision: proc-needs in the left snapshot" in text
    assert "source_not_ok: broken is failed in the left snapshot" in text
    assert [p.field for p in diff.processing] == ["chunker_version"]


def test_source_reasons(fixture: ComparisonFixture) -> None:
    left = manifest(fixture, fixture.left_id)
    assert source_reason(left, "platform") == "source_absent"
    assert source_reason(left, "proc") is None
    failed = left.model_copy(
        update={"sources": [left.sources[0].model_copy(update={"status": "failed"})]}
    )
    assert source_reason(failed, "proc") == "source_failed"
    summary = left.coverage.sources[0].model_copy(update={"partial": 1})
    partial = left.model_copy(
        update={"coverage": left.coverage.model_copy(update={"sources": [summary]})}
    )
    assert source_reason(partial, "proc") == "source_partial"
    assert missing_reason(left, ["proc", "platform"], "not_retrieved") == "source_absent"
    assert missing_reason(left, ["proc"], "not_retrieved") == "not_retrieved"
    assert reason_text("source_absent", "left") == "the source is not in the left snapshot"


def test_manifest_path_helper_matches_store(fixture: ComparisonFixture) -> None:
    assert Path(fixture.data / "snapshots" / fixture.left_id / "manifest.json").is_file()
