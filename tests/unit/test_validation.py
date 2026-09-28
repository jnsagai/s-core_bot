"""SnapshotValidator: every integrity check fails on its defect; semantic status (FR-016, SC-005).
Uses the fake embedding provider (mocked)."""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.domain.snapshots import ChunkerConfig, ValidationReport
from score_docs_assistant.storage.validation import SnapshotValidator
from tests.helpers.build import build
from tests.helpers.fake_embedding import FAKE_DIGEST, FakeEmbeddingProvider
from tests.helpers.snapshot_env import make_env, write_model_lock


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    env = make_env(tmp_path_factory.mktemp("validate"))
    result = build(env)
    return env.data, env.data / "snapshots" / result.snapshot_id


def _copy(built: tuple[Path, Path], tmp_path: Path) -> tuple[Path, Path]:
    data, snapshot = built
    target = tmp_path / "data" / "snapshots" / snapshot.name
    shutil.copytree(snapshot, target)
    for path in target.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    shutil.copy(data / "model-lock.json", tmp_path / "data" / "model-lock.json")
    return tmp_path / "data", target


def _validate(
    data: Path, snapshot: Path, runtime: FakeEmbeddingProvider | None = None
) -> ValidationReport:
    return SnapshotValidator(
        data_dir=data,
        embedding_model="nomic-embed-text",
        chunker_config=ChunkerConfig(),
        runtime=runtime,
    ).validate(snapshot)


def _failed(report: ValidationReport) -> list[str]:
    return [c.id for c in report.integrity if c.status == "fail"]


def test_valid_snapshot_passes(built: tuple[Path, Path]) -> None:
    runtime = FakeEmbeddingProvider()
    report = _validate(*built, runtime=runtime)
    assert report.integrity_ok, report.integrity
    assert report.semantic == "enabled"
    assert runtime.calls == []  # identity only, never embeds


def _append(path: Path) -> None:
    with path.open("ab") as handle:
        handle.write(b"x")


def _sql(statement: str) -> Callable[[Path], None]:
    def mutate(snapshot: Path) -> None:
        conn = sqlite3.connect(snapshot / "corpus.sqlite")
        conn.execute(statement)
        conn.commit()
        conn.close()

    return mutate


def _vectors(transform: Callable[[np.ndarray], np.ndarray]) -> Callable[[Path], None]:
    def mutate(snapshot: Path) -> None:
        manifest = json.loads((snapshot / "embedding-manifest.json").read_text())
        path = snapshot / "embeddings.f32"
        matrix = np.fromfile(path, dtype="<f4").reshape(manifest["rows"], manifest["dimension"])
        transform(matrix).astype("<f4").tofile(path)

    return mutate


def _set_row_nan(m: np.ndarray) -> np.ndarray:
    m[0, 0] = np.nan
    return m


def _scale_row(m: np.ndarray) -> np.ndarray:
    m[1] = m[1] * 2
    return m


DEFECTS: dict[str, tuple[Callable[[Path], None], str]] = {
    "tampered file": (lambda s: _append(s / "reports" / "coverage.json"), "file:reports/"),
    "unlisted file": (lambda s: (s / "extra.txt").write_text("x"), "file:extra.txt"),
    "missing file": (lambda s: (s / "reports" / "coverage.json").unlink(), "file:reports/"),
    "extra trigger": (
        _sql("CREATE TRIGGER t AFTER INSERT ON meta BEGIN SELECT 1; END"),
        "corpus.schema",
    ),
    "extra view": (_sql("CREATE VIEW v AS SELECT 1"), "corpus.schema"),
    "fts drift": (_sql("UPDATE chunks SET text = 'altered' WHERE rowid = 1"), "corpus.fts"),
    "count mismatch": (_sql("DELETE FROM relations"), "corpus.counts"),
    "truncated vectors": (
        lambda s: (s / "embeddings.f32").write_bytes((s / "embeddings.f32").read_bytes()[:-4]),
        "vectors.shape",
    ),
    "nan row": (_vectors(_set_row_nan), "vectors.values"),
    "off-norm row": (_vectors(_scale_row), "vectors.values"),
    "row map": (
        _sql("UPDATE chunks SET chunk_id = 'zzz' WHERE rowid = 1"),
        "vectors.row_map",
    ),
}


def _rehash(snapshot: Path) -> None:
    """Re-list checksums so a content defect is not masked by the file-hash check."""
    from score_docs_assistant.storage.manifest import hash_files

    manifest = json.loads((snapshot / "manifest.json").read_text())
    manifest["files"] = [e.model_dump() for e in hash_files(snapshot)]
    emb_path = snapshot / "embedding-manifest.json"
    emb = json.loads(emb_path.read_text())
    from score_docs_assistant.storage.manifest import sha256_file

    emb["sha256"] = sha256_file(snapshot / "embeddings.f32")
    emb_path.write_text(json.dumps(emb))
    manifest["files"] = [e.model_dump() for e in hash_files(snapshot)]
    (snapshot / "manifest.json").write_text(json.dumps(manifest))


@pytest.mark.parametrize("defect", sorted(DEFECTS))
def test_each_defect_fails_its_check(built: tuple[Path, Path], tmp_path: Path, defect: str) -> None:
    data, snapshot = _copy(built, tmp_path)
    mutate, check_prefix = DEFECTS[defect]
    mutate(snapshot)
    if not check_prefix.startswith("file:"):
        _rehash(snapshot)
    report = _validate(data, snapshot)
    assert not report.integrity_ok
    assert any(c.startswith(check_prefix) for c in _failed(report)), _failed(report)


def test_newer_corpus_schema_refused(built: tuple[Path, Path], tmp_path: Path) -> None:
    data, snapshot = _copy(built, tmp_path)
    _sql("PRAGMA user_version = 7")(snapshot)
    _rehash(snapshot)
    with pytest.raises(SnapshotError) as exc_info:
        _validate(data, snapshot)
    assert exc_info.value.code == "SCHEMA_UNSUPPORTED"


def test_manifest_hash_mismatch_detected(built: tuple[Path, Path]) -> None:
    data, snapshot = built
    report = SnapshotValidator(
        data_dir=data, embedding_model="nomic-embed-text", chunker_config=ChunkerConfig()
    ).validate(snapshot, expected_manifest_sha256="0" * 64)
    assert "manifest.sha256" in _failed(report)


@pytest.mark.parametrize(
    ("runtime", "lock_digest", "config", "expected"),
    [
        (FakeEmbeddingProvider(digest="1" * 64), FAKE_DIGEST, ChunkerConfig(), "disabled"),
        (FakeEmbeddingProvider(dimension=8), FAKE_DIGEST, ChunkerConfig(), "disabled"),
        (None, "2" * 64, ChunkerConfig(), "disabled"),
        (None, FAKE_DIGEST, ChunkerConfig(document_prefix="x: "), "disabled"),
        (FakeEmbeddingProvider(mode="unreachable"), FAKE_DIGEST, ChunkerConfig(), "unverified"),
        (None, FAKE_DIGEST, ChunkerConfig(), "unverified"),
    ],
)
def test_semantic_status(
    built: tuple[Path, Path],
    tmp_path: Path,
    runtime: FakeEmbeddingProvider | None,
    lock_digest: str,
    config: ChunkerConfig,
    expected: str,
) -> None:
    data, snapshot = _copy(built, tmp_path)
    write_model_lock(data, lock_digest)
    report = SnapshotValidator(
        data_dir=data, embedding_model="nomic-embed-text", chunker_config=config, runtime=runtime
    ).validate(snapshot)
    assert report.integrity_ok
    assert report.semantic == expected
    if expected == "disabled":
        assert any("index build" in g for g in report.guidance)
    if runtime is not None:
        assert runtime.calls == []


def test_missing_lock_entry_disables_with_pull_guidance(
    built: tuple[Path, Path], tmp_path: Path
) -> None:
    data, snapshot = _copy(built, tmp_path)
    (data / "model-lock.json").unlink()
    report = _validate(data, snapshot)
    assert report.semantic == "disabled"
    assert any("models pull" in g for g in report.guidance)
