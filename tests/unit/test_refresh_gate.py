"""PromotionGate checks (F011 FR-006) on a real fixture snapshot with crafted baselines."""

from __future__ import annotations

from pathlib import Path

import pytest

from score_docs_assistant.domain.snapshots import SnapshotManifest
from score_docs_assistant.refresh.gate import PromotionGate
from score_docs_assistant.retrieval.evaluation import ExactIdFailure, ExactIdReport
from score_docs_assistant.sources.lock import read_lock
from score_docs_assistant.storage.manifest import read_snapshot_manifest
from tests.helpers.build import app_config, build
from tests.helpers.snapshot_env import SnapshotEnv, make_env


def _report(sid: str, failures: int = 0) -> ExactIdReport:
    return ExactIdReport(
        snapshot_id=sid,
        ids_checked=10,
        correct_first=10 - failures,
        failures=[
            ExactIdFailure(need_id=f"id_{i}", expected="k", got=None) for i in range(failures)
        ],
        ambiguous_by_design=[],
    )


@pytest.fixture
def built(tmp_path: Path) -> tuple[SnapshotEnv, str, SnapshotManifest]:
    env = make_env(tmp_path)
    sid = build(env).snapshot_id
    return env, sid, read_snapshot_manifest(env.data / "snapshots" / sid)


def _gate(env: SnapshotEnv, failures: int = 0, **refresh: object) -> PromotionGate:
    config = app_config(env.data).model_copy(
        update={"refresh": app_config(env.data).refresh.model_copy(update=refresh)}
    )
    return PromotionGate(config, exact_ids=lambda sid: _report(sid, failures))


def _by_id(checks: list) -> dict[str, str]:  # type: ignore[type-arg]
    return {c.id: c.status for c in checks}


def _scaled(manifest: SnapshotManifest, factor: float) -> SnapshotManifest:
    counts = manifest.counts.model_copy(
        update={
            "documents": int(manifest.counts.documents * factor),
            "chunks": int(manifest.counts.chunks * factor),
            "entities": int(manifest.counts.entities * factor),
        }
    )
    return manifest.model_copy(update={"counts": counts})


def test_all_pass_without_active(built: tuple[SnapshotEnv, str, SnapshotManifest]) -> None:
    env, sid, _ = built
    checks = _gate(env).evaluate(sid, None, read_lock(env.lock_path))
    assert set(_by_id(checks).values()) == {"pass"}
    assert [c.id for c in checks] == [
        "integrity",
        "exact_ids",
        "coverage_drop",
        "semantic",
        "required_sources",
    ]


def test_coverage_drop_beyond_limit_fails(built: tuple[SnapshotEnv, str, SnapshotManifest]) -> None:
    env, sid, manifest = built
    active = _scaled(manifest, 2.0)  # candidate has half of the active counts: 50 % drop
    checks = _by_id(_gate(env).evaluate(sid, active, read_lock(env.lock_path)))
    assert checks["coverage_drop"] == "fail"
    relaxed = _by_id(_gate(env, max_count_drop=0.6).evaluate(sid, active, read_lock(env.lock_path)))
    assert relaxed["coverage_drop"] == "pass"


def test_growth_always_passes(built: tuple[SnapshotEnv, str, SnapshotManifest]) -> None:
    env, sid, manifest = built
    checks = _by_id(_gate(env).evaluate(sid, _scaled(manifest, 0.5), read_lock(env.lock_path)))
    assert checks["coverage_drop"] == "pass"


def test_exact_id_failures_fail(built: tuple[SnapshotEnv, str, SnapshotManifest]) -> None:
    env, sid, _ = built
    [exact] = [
        c
        for c in _gate(env, failures=2).evaluate(sid, None, read_lock(env.lock_path))
        if c.id == "exact_ids"
    ]
    assert exact.status == "fail" and "8/10" in exact.detail and "id_0" in exact.detail


def test_semantic_loss_fails(built: tuple[SnapshotEnv, str, SnapshotManifest]) -> None:
    env, _, manifest = built
    lexical = build(env, lexical_only=True).snapshot_id
    checks = _by_id(_gate(env).evaluate(lexical, manifest, read_lock(env.lock_path)))
    assert checks["semantic"] == "fail"
    # A keyword-only active snapshot accepts a keyword-only candidate.
    lexical_active = manifest.model_copy(update={"semantic": "absent"})
    assert (
        _by_id(_gate(env).evaluate(lexical, lexical_active, read_lock(env.lock_path)))["semantic"]
        == "pass"
    )


def test_tampered_candidate_fails_integrity(
    built: tuple[SnapshotEnv, str, SnapshotManifest],
) -> None:
    env, sid, _ = built
    corpus = env.data / "snapshots" / sid / "corpus.sqlite"
    corpus.chmod(0o644)
    corpus.write_bytes(b"tampered")
    checks = _by_id(_gate(env).evaluate(sid, None, read_lock(env.lock_path)))
    assert checks["integrity"] == "fail"


def test_required_source_missing_fails(built: tuple[SnapshotEnv, str, SnapshotManifest]) -> None:
    env, sid, _ = built
    lock = read_lock(env.lock_path)
    extra = lock.sources[0].model_copy(update={"source_id": "gamma", "required": True})
    lock = lock.model_copy(update={"sources": [*lock.sources, extra]})
    checks = _by_id(_gate(env).evaluate(sid, None, lock))
    assert checks["required_sources"] == "fail"
