"""Release assembly (F009 FR-011)."""

from __future__ import annotations

import json
from pathlib import Path

from score_docs_assistant.qualification.release import ITEMS, assemble


def _setup(tmp_path: Path, complete: bool) -> tuple[Path, Path, Path]:
    root, reports = tmp_path / "repo", tmp_path / "reports"
    for item in ITEMS:
        base = reports if item.in_reports else root
        name = item.source.replace("*", "20260929T000000Z")
        if not complete and item.kind == "sbom":
            continue
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{item.kind}\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    return root, reports, manifest


def test_complete_release_manifest(tmp_path: Path) -> None:
    root, reports, manifest = _setup(tmp_path, complete=True)
    out = assemble(root, reports, manifest, tmp_path / "releases")
    data = json.loads((out / "release-manifest.json").read_text())
    assert data["complete"] and not data["missing"]
    assert len(data["items"]) == len(ITEMS) + 1
    assert all(len(i["sha256"]) == 64 for i in data["items"])
    assert {e["what"] for e in data["excluded"]} == {"model weights", "corpus bundles"}
    assert (out / "release-report" / "release-report.md").is_file()


def test_missing_items_are_listed(tmp_path: Path) -> None:
    root, reports, _ = _setup(tmp_path, complete=False)
    out = assemble(root, reports, None, tmp_path / "releases")
    data = json.loads((out / "release-manifest.json").read_text())
    assert not data["complete"] and "sbom-*.cdx.json" in data["missing"]
    assert "active snapshot manifest" in data["missing"]


def test_operator_documents_present() -> None:
    repo = Path(__file__).parent.parent.parent
    for name in (
        "install",
        "offline-preparation",
        "backup-restore",
        "upgrade-rollback",
        "troubleshooting",
        "logs",
    ):
        assert (repo / "docs" / "runbooks" / f"{name}.md").is_file(), name
    matrix = (repo / "docs" / "quality" / "hardware-matrix.md").read_text()
    assert "qualified" in matrix and "not run" in matrix and "not validated" in matrix
    assert (repo / "docs" / "KNOWN_LIMITATIONS.md").is_file()
