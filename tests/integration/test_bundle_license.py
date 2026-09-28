"""License-review gate on export (FR-018, US3 AS4). Mocked provider."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.storage import bundles
from score_docs_assistant.storage.catalog import Catalog
from tests.helpers.build import app_config
from tests.helpers.lifecycle import snapshots
from tests.helpers.snapshot_env import make_env


def test_refused_without_acknowledgement_then_recorded(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    [snapshot_id] = snapshots(env, 1)
    out = tmp_path / "b.score-bundle.tar.gz"
    with pytest.raises(SnapshotError) as exc_info:
        bundles.export_bundle(
            config=app_config(env.data), snapshot_id=snapshot_id, output=out, acknowledgement=None
        )
    assert exc_info.value.code == "LICENSE_REVIEW_REQUIRED"
    assert "alpha:docs/sharealike.rst" in exc_info.value.message
    assert not out.exists()

    bundles.export_bundle(
        config=app_config(env.data), snapshot_id=snapshot_id, output=out, acknowledgement="ok'd"
    )
    with tarfile.open(out, "r:gz") as tar:
        first = tar.getmembers()[0]
        assert first.name == "bundle-manifest.json"
        handle = tar.extractfile(first)
        assert handle is not None
        manifest = json.loads(handle.read())
    assert manifest["license_acknowledgement"] == {
        "reason": "ok'd",
        "files": ["alpha:docs/sharealike.rst"],
    }


def test_refuses_failed_snapshot_and_existing_output(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    [snapshot_id] = snapshots(env, 1)
    existing = tmp_path / "exists.tar.gz"
    existing.write_text("keep me")
    with pytest.raises(SnapshotError, match="output_exists"):
        bundles.export_bundle(
            config=app_config(env.data),
            snapshot_id=snapshot_id,
            output=existing,
            acknowledgement="x",
        )
    assert existing.read_text() == "keep me"
    catalog = Catalog.open(env.data, create=False)
    assert catalog is not None
    with catalog, catalog.transaction() as conn:
        conn.execute("UPDATE snapshots SET state = 'failed' WHERE snapshot_id = ?", (snapshot_id,))
    with pytest.raises(SnapshotError) as exc_info:
        bundles.export_bundle(
            config=app_config(env.data),
            snapshot_id=snapshot_id,
            output=tmp_path / "new.tar.gz",
            acknowledgement="x",
        )
    assert exc_info.value.code == "SNAPSHOT_NOT_FOUND"
