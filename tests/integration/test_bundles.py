"""Bundle export → import, hostile bundles, collisions (FR-019, FR-020, SC-006). Mocked provider."""

from __future__ import annotations

import sqlite3
import tarfile
from collections.abc import Callable
from pathlib import Path

import pytest

from score_docs_assistant.domain.errors import SnapshotError
from score_docs_assistant.storage import bundles
from score_docs_assistant.storage.catalog import Catalog
from tests.helpers.build import app_config
from tests.helpers.bundles import Member, extra, read_members, with_manifest, write_members
from tests.helpers.lifecycle import snapshots
from tests.helpers.snapshot_env import make_env

ACK = "reviewed for test redistribution"


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, Path]:
    tmp = tmp_path_factory.mktemp("bundle-src")
    env = make_env(tmp)
    [snapshot_id] = snapshots(env, 1)
    path = tmp / "a.score-bundle.tar.gz"
    bundles.export_bundle(
        config=app_config(env.data), snapshot_id=snapshot_id, output=path, acknowledgement=ACK
    )
    return path, snapshot_id, env.data


def _identities(data: Path, snapshot_id: str) -> tuple[object, ...]:
    corpus = data / "snapshots" / snapshot_id / "corpus.sqlite"
    conn = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    chunks = conn.execute("SELECT chunk_id FROM chunks ORDER BY rowid").fetchall()
    entities = conn.execute("SELECT key FROM entities ORDER BY key").fetchall()
    files = {
        p.relative_to(data / "snapshots" / snapshot_id).as_posix(): p.read_bytes()
        for p in (data / "snapshots" / snapshot_id).rglob("*")
        if p.is_file()
    }
    return chunks, entities, files


def _fresh(tmp_path: Path) -> Path:
    data = tmp_path / "fresh" / "data"
    data.mkdir(parents=True)
    return data


def test_round_trip_on_fresh_data_dir(exported: tuple[Path, str, Path], tmp_path: Path) -> None:
    path, snapshot_id, source_data = exported
    data = _fresh(tmp_path)
    result = bundles.import_bundle(config=app_config(data), path=path)
    assert result.snapshot_id == snapshot_id and not result.already_present
    assert _identities(data, snapshot_id) == _identities(source_data, snapshot_id)
    with Catalog.open(data, create=False) as catalog:  # type: ignore[union-attr]
        row = catalog.get(snapshot_id)
        assert row is not None and row.state == "validated"
        assert catalog.active_id() is None
    again = bundles.import_bundle(config=app_config(data), path=path)
    assert again.already_present


def _hostile_cases() -> dict[str, Callable[[list[Member]], list[Member]]]:
    def tamper(members: list[Member]) -> list[Member]:
        out = list(members)
        info, data = out[2]
        out[2] = (info, (data or b"") + b"x")
        return out

    def flip(members: list[Member]) -> list[Member]:
        out = list(members)
        info, data = out[-1]
        raw = bytearray(data or b"")
        raw[len(raw) // 2] ^= 0xFF
        out[-1] = (info, bytes(raw))
        return out

    def replace_member(members: list[Member], member: Member) -> list[Member]:
        return [*members[:-1], member]

    return {
        "tampered": tamper,
        "tampered same size": flip,
        "dotdot": lambda m: [*m, extra("snapshot/../evil.txt")],
        "absolute": lambda m: [*m, extra("/tmp/evil.txt")],
        "outside prefix": lambda m: [*m, extra("other/evil.txt")],
        "symlink": lambda m: [*m, extra("snapshot/link", kind=tarfile.SYMTYPE, link="/etc/passwd")],
        "hardlink": lambda m: [
            *m,
            extra("snapshot/hl", kind=tarfile.LNKTYPE, link="snapshot/manifest.json"),
        ],
        "device": lambda m: [*m, extra("snapshot/dev", kind=tarfile.CHRTYPE)],
        "fifo": lambda m: [*m, extra("snapshot/fifo", kind=tarfile.FIFOTYPE)],
        "directory": lambda m: [*m, extra("snapshot/dir", kind=tarfile.DIRTYPE)],
        "duplicate": lambda m: [*m, m[-1]],
        "unlisted": lambda m: [*m, extra("snapshot/unlisted.txt")],
        "missing member": lambda m: m[:-1],
        "manifest not first": lambda m: [*m[1:], m[0]],
        "manifest too big": lambda m: [(m[0][0], b" " * (1024 * 1024 + 1)), *m[1:]],
        "newer schema": lambda m: with_manifest(m, lambda d: d.update(schema_version=9)),
        "declared total": lambda m: with_manifest(m, lambda d: d.update(total_size=1)),
        "backslash": lambda m: replace_member(m, extra("snapshot\\evil")),
    }


@pytest.mark.parametrize("case", sorted(_hostile_cases()))
def test_hostile_bundle_rejected(
    exported: tuple[Path, str, Path], tmp_path: Path, case: str
) -> None:
    path, snapshot_id, _ = exported
    hostile = write_members(tmp_path / "hostile.tar.gz", _hostile_cases()[case](read_members(path)))
    data = _fresh(tmp_path)
    with pytest.raises(SnapshotError) as exc_info:
        bundles.import_bundle(config=app_config(data), path=hostile)
    assert exc_info.value.code == "BUNDLE_REJECTED", exc_info.value
    catalog = Catalog.open(data, create=False)
    if catalog is not None:
        with catalog:
            assert catalog.get(snapshot_id) is None
    assert not (data / "snapshots").exists() or not any((data / "snapshots").iterdir())
    staging = data / "staging"
    assert not staging.exists() or not any(staging.iterdir())
    assert not (tmp_path / "evil.txt").exists() and not Path("/tmp/evil.txt").exists()


def test_caps_enforced(exported: tuple[Path, str, Path], tmp_path: Path) -> None:
    path, _, _ = exported
    data = _fresh(tmp_path)
    config = app_config(data).model_copy(
        update={"bundles": app_config(data).bundles.model_copy(update={"max_entries": 3})}
    )
    with pytest.raises(SnapshotError, match="too_many_entries"):
        bundles.import_bundle(config=config, path=path)
    config = app_config(data).model_copy(
        update={"bundles": app_config(data).bundles.model_copy(update={"max_total_bytes": 1000})}
    )
    with pytest.raises(SnapshotError, match="too_large"):
        bundles.import_bundle(config=config, path=path)


def test_disk_check_before_extraction(exported: tuple[Path, str, Path], tmp_path: Path) -> None:
    path, _, _ = exported
    data = _fresh(tmp_path)
    with pytest.raises(SnapshotError, match="disk_insufficient"):
        bundles.import_bundle(config=app_config(data), path=path, free_bytes=lambda _p: 10)
    assert not (data / "staging").exists()


def test_id_conflict_and_revive(exported: tuple[Path, str, Path], tmp_path: Path) -> None:
    path, snapshot_id, _ = exported
    data = _fresh(tmp_path)
    bundles.import_bundle(config=app_config(data), path=path)
    catalog = Catalog.open(data, create=False)
    assert catalog is not None
    with catalog, catalog.transaction() as conn:
        conn.execute(
            "UPDATE snapshots SET manifest_sha256 = 'other' WHERE snapshot_id = ?", (snapshot_id,)
        )
    with pytest.raises(SnapshotError, match="id_conflict"):
        bundles.import_bundle(config=app_config(data), path=path)
    catalog = Catalog.open(data, create=False)
    assert catalog is not None
    with catalog, catalog.transaction() as conn:
        conn.execute("UPDATE snapshots SET state = 'deleted' WHERE snapshot_id = ?", (snapshot_id,))
    import shutil

    shutil.rmtree(data / "snapshots" / snapshot_id)
    result = bundles.import_bundle(config=app_config(data), path=path)
    assert not result.already_present
    with Catalog.open(data, create=False) as catalog:  # type: ignore[union-attr]
        row = catalog.get(snapshot_id)
        assert row is not None and row.state == "validated"


def test_inspect_writes_nothing(exported: tuple[Path, str, Path], tmp_path: Path) -> None:
    path, snapshot_id, _ = exported
    data = _fresh(tmp_path)
    result = bundles.inspect_bundle(config=app_config(data), path=path)
    assert result.manifest.snapshot_id == snapshot_id
    assert result.snapshot_manifest["counts"]
    assert list(data.iterdir()) == []
