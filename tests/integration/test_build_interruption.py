"""Interrupting a build at every stage never touches the active snapshot (FR-011, SC-004).

Two mechanisms per stage: an injected exception (in process) and a real SIGKILL of a child
process that is building (the stage hook kills its own process on entering the stage).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from score_docs_assistant.domain.snapshots import BUILD_STAGES
from score_docs_assistant.storage.catalog import Catalog
from tests.helpers.build import build
from tests.helpers.fake_embedding import FakeEmbeddingProvider
from tests.helpers.snapshot_env import make_env

REPO_ROOT = Path(__file__).parent.parent.parent

_CHILD = """
import os, signal, sys
from pathlib import Path
from tests.helpers.build import build
from tests.helpers.snapshot_env import SnapshotEnv

target = sys.argv[2]
def hook(stage):
    if stage == target:
        os.kill(os.getpid(), signal.SIGKILL)
env = SnapshotEnv(data=Path(sys.argv[1]), lock_path=Path(sys.argv[1]) / "source-lock.json")
build(env, stage_hook=hook)
"""


def _activate(data: Path, snapshot_id: str) -> None:
    with Catalog.open(data, create=False) as catalog:  # type: ignore[union-attr]
        catalog.switch_active(snapshot_id, "activate")


def _fingerprint(data: Path, active: str) -> tuple[object, ...]:
    snapshot = data / "snapshots" / active
    files = {
        p.relative_to(snapshot).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(snapshot.rglob("*"))
        if p.is_file()
    }
    with Catalog.open(data, create=False) as catalog:  # type: ignore[union-attr]
        row = catalog.get(active)
        return (
            files,
            catalog.active_id(),
            [h.model_dump() for h in catalog.history()],
            row.state if row else None,
        )


class _Boom(Exception):
    pass


@pytest.mark.parametrize("stage", BUILD_STAGES)
def test_injected_failure_at_stage(tmp_path: Path, stage: str) -> None:
    env = make_env(tmp_path)
    active = build(env).snapshot_id
    _activate(env.data, active)
    before = _fingerprint(env.data, active)

    def hook(current: str) -> None:
        if current == stage:
            raise _Boom(stage)

    with pytest.raises(_Boom):
        build(env, stage_hook=hook)
    assert _fingerprint(env.data, active) == before
    assert not any((env.data / "staging").iterdir())
    with Catalog.open(env.data, create=False) as catalog:  # type: ignore[union-attr]
        failed = [s for s in catalog.snapshots() if s.state == "failed"]
        assert len(failed) == 1


@pytest.mark.parametrize("stage", BUILD_STAGES)
def test_sigkill_at_stage_then_recovery(tmp_path: Path, stage: str) -> None:
    env = make_env(tmp_path)
    active = build(env).snapshot_id
    _activate(env.data, active)
    before = _fingerprint(env.data, active)

    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, str(env.data), stage],
        env={**os.environ, "PYTHONPATH": f"{REPO_ROOT}:{REPO_ROOT / 'src'}"},
        cwd=REPO_ROOT,
        timeout=120,
        check=False,
    )
    assert proc.returncode == -9, proc
    assert _fingerprint(env.data, active) == before

    recovered = build(env, FakeEmbeddingProvider())
    assert _fingerprint(env.data, active) == before
    staging = env.data / "staging"
    assert not [p for p in staging.iterdir() if p.name.startswith("build-")]
    with Catalog.open(env.data, create=False) as catalog:  # type: ignore[union-attr]
        states = {s.snapshot_id: (s.state, s.failure) for s in catalog.snapshots()}
        interrupted = [sid for sid, (state, why) in states.items() if why == "interrupted"]
        assert len(interrupted) == 1 and states[interrupted[0]][0] == "failed"
        assert not (env.data / "snapshots" / interrupted[0]).exists()
        assert states[recovered.snapshot_id][0] == "validated"
        assert catalog.jobs()[1].failure == "interrupted"


def test_crash_between_move_and_publish_commit(tmp_path: Path, monkeypatch) -> None:
    """The publish window: directory already moved into snapshots/, catalog still `building`."""
    from score_docs_assistant.storage.catalog import Catalog as CatalogClass

    env = make_env(tmp_path)

    def crash(*args: object, **kwargs: object) -> None:
        raise SystemExit("simulated crash after os.replace")

    monkeypatch.setattr(CatalogClass, "publish", crash)
    monkeypatch.setattr(CatalogClass, "fail", lambda *a, **k: None)  # the process "died"
    with pytest.raises(SystemExit):
        build(env)
    monkeypatch.undo()
    orphans = list((env.data / "snapshots").iterdir())
    assert len(orphans) == 1
    build(env)
    with Catalog.open(env.data, create=False) as catalog:  # type: ignore[union-attr]
        row = catalog.get(orphans[0].name)
        assert row is not None and row.state == "failed"
    assert not orphans[0].exists()
