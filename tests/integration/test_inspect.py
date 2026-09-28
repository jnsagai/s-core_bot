"""Normalization over a lock: invariants, tamper detection, determinism (FR-016, FR-017, FR-023,
SC-002, SC-004)."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

import pytest

from score_docs_assistant.ingestion.report import write_outputs
from tests.helpers.git_repos import default_files, make_plain_repo
from tests.helpers.pipeline import PROFILES, normalize, sync
from tests.helpers.registries import git_source

FILES = {
    **default_files(),
    "docs/reqs.rst": (
        "Reqs\n====\n\n.. feat_req:: A\n   :id: feat_req__a\n   :satisfies: feat_req__b\n\n"
        ".. feat_req:: B\n   :id: feat_req__b\n   :satisfies: nowhere__x, bad[\n"
    ),
    "docs/latin1.rst": "caf\xe9\n".encode("latin-1"),
    "docs/empty.rst": "",
    "docs/cc.rst": "..\n   SPDX-License-Identifier: CC-BY-SA-4.0\n\nText.\n",
}


@pytest.fixture
def data(tmp_path: Path) -> Path:
    repo = make_plain_repo(tmp_path / "repo", FILES)
    data_dir = tmp_path / "data"
    assert sync(data_dir, [git_source("docs", repo.url)]) == 0
    return data_dir


def test_report_invariants_and_classification(data: Path) -> None:
    outcome = normalize(data)
    assert outcome.exit_code == 0
    (cov,) = outcome.report.sources
    assert cov.selected == cov.included + cov.partial + len(cov.failed)
    assert cov.selected == len(FILES) - 3  # LICENSE, NOTICE (notices), src/main.py (excluded)
    assert [(f.path, f.reason) for f in cov.failed] == [("docs/latin1.rst", "ENCODING_ERROR")]
    assert cov.entities == 2
    assert (cov.links.resolved, cov.links.unresolved, cov.links.malformed) == (1, 1, 1)
    assert cov.links.unresolved_items[0].target_id == "nowhere__x"
    # A file that cannot be decoded cannot be checked for its own SPDX header, so its license
    # is unknown (not guessed from the repository) and therefore requires review (FR-021).
    assert cov.requires_review == ["docs/cc.rst", "docs/latin1.rst"]
    assert cov.diagnostics_by_code["EMPTY_DOCUMENT"] == 1
    assert cov.licenses["CC-BY-SA-4.0"] == 1
    assert cov.excluded_by_selector == 1
    # FR-023: partially parsed files are listed with their warning codes, not only counted.
    assert [(f.path, f.codes) for f in cov.partial_files] == [("docs/reqs.rst", ["MALFORMED_LINK"])]


def test_tampered_file_fails_source(data: Path) -> None:
    lock_entry = next((data / "sources" / "docs").iterdir())
    target = lock_entry / "docs" / "index.rst"
    target.chmod(stat.S_IWUSR | stat.S_IRUSR)
    target.write_text("tampered\n")
    outcome = normalize(data)
    assert outcome.exit_code == 1
    (cov,) = outcome.report.sources
    assert cov.status == "failed" and "HASH_MISMATCH" in (cov.failure or "")
    assert outcome.documents == []
    # One error diagnostic per changed file (contracts/normalized-output.md).
    assert cov.diagnostics_by_code == {"HASH_MISMATCH": 1}
    assert [(f.path, f.reason) for f in cov.failed] == [("docs/index.rst", "HASH_MISMATCH")]


def test_missing_revision_directory_fails_source(data: Path) -> None:
    root = next((data / "sources" / "docs").iterdir())
    for dirpath, _, files in os.walk(root):
        os.chmod(dirpath, 0o755)
        for name in files:
            os.chmod(Path(dirpath) / name, 0o644)
    shutil.rmtree(root)
    assert normalize(data).exit_code == 1


def test_double_run_byte_identical(data: Path, tmp_path: Path) -> None:
    write_outputs(normalize(data), tmp_path / "one")
    write_outputs(normalize(data), tmp_path / "two")
    for name in ("documents.jsonl", "entities.jsonl"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()


def test_profile_change_changes_processing_hash(data: Path, tmp_path: Path) -> None:
    changed = tmp_path / "profiles"
    shutil.copytree(PROFILES, changed)
    profile = changed / "s-core.yaml"
    profile.write_text(profile.read_text().replace("link_options: [", "link_options: [verifies, "))
    base, other = normalize(data), normalize(data, changed)
    assert base.report.processing_hash != other.report.processing_hash
    assert {d.document_key for d in base.documents}.isdisjoint(
        {d.document_key for d in other.documents}
    )
